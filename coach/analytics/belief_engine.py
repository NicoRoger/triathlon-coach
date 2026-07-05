"""Fase 4.4 — Bayesian Belief Engine.

Le beliefs sono probabilità dinamiche con evidence decay e lifecycle.
Contradictory evidence riduce confidence; NON cancella.

Lifecycle 4 stati:
    hypothesis    : n<4                            (solo esplorativa)
    weak_belief   : n>=4 AND conf>0.55             (citata con caveat)
    validated     : n>=8 AND conf>0.7              (applicabile in proposte)
    strong        : longitudinal stability >6 mesi (default beliefs)

API:
    create_belief(key, text, ...)
    reinforce_belief(key, outcome_id, ...)        — evidence positiva
    contradict_belief(key, outcome_id, reason)    — evidence negativa (decay conf)
    list_beliefs(min_status='weak_belief')
    decay_old_beliefs()                            — cron settimanale

Persistence in tabella `beliefs` + audit in `beliefs_history`.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# Status lifecycle thresholds
HYPOTHESIS_MAX_N = 3                  # n<4 = hypothesis
WEAK_BELIEF_MIN_N = 4
WEAK_BELIEF_MIN_CONFIDENCE = 0.55
VALIDATED_MIN_N = 8
VALIDATED_MIN_CONFIDENCE = 0.7
STRONG_BELIEF_MIN_AGE_DAYS = 180       # stabile >6 mesi
STRONG_BELIEF_MIN_CONFIDENCE = 0.75

# Bayesian update parameters
REINFORCE_BOOST = 0.08                  # conf gain per evidenza positiva
CONTRADICT_PENALTY = 0.15               # conf loss per evidenza contraria (asimmetrico, contraddizioni pesano di più)
DEFAULT_HALF_LIFE_DAYS = 120

# Status legend usato in output human-readable
STATUS_EMOJI = {
    "hypothesis": "💡",
    "weak_belief": "🌱",
    "validated_belief": "✅",
    "strong_belief": "🏆",
    "retired": "🗑️",
}


# ============================================================================
# Core
# ============================================================================

@dataclass
class Belief:
    """Rappresentazione in-memory di una belief."""
    id: Optional[str]
    belief_key: str
    belief_text: str
    confidence: float
    evidence_n: int
    status: str
    category: Optional[str] = None
    prescription: Optional[str] = None
    expected_outcome: Optional[str] = None
    supporting_outcomes: list[str] = field(default_factory=list)
    contradicting_outcomes: list[str] = field(default_factory=list)
    evidence_decay_half_life_days: int = DEFAULT_HALF_LIFE_DAYS
    first_observed_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    last_reinforced_at: Optional[datetime] = None
    flagged: bool = False
    flag_reason: Optional[str] = None
    source: Optional[str] = None

    @property
    def is_actionable(self) -> bool:
        """Solo validated/strong beliefs sono actionable in proposte."""
        return self.status in ("validated_belief", "strong_belief") and not self.flagged

    def effective_confidence(self, today: Optional[datetime] = None) -> float:
        """Confidence con decay temporale applicato (read-only, non persiste).

        decay = 0.5 ^ (days_since_reinforced / half_life)
        """
        if self.last_reinforced_at is None:
            return self.confidence
        today = today or datetime.now(timezone.utc)
        last = self.last_reinforced_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days = (today - last).days
        if days <= 0:
            return self.confidence
        decay = 0.5 ** (days / max(self.evidence_decay_half_life_days, 1))
        return round(self.confidence * decay, 3)


# ============================================================================
# CRUD + Bayesian operations
# ============================================================================

def _compute_status(n: int, confidence: float,
                    first_observed_at: Optional[datetime] = None,
                    today: Optional[datetime] = None) -> str:
    """Determina status in base a n + confidence + età."""
    if n <= HYPOTHESIS_MAX_N:
        return "hypothesis"
    if n >= VALIDATED_MIN_N and confidence >= VALIDATED_MIN_CONFIDENCE:
        # Strong se età stabile + confidence alta
        if first_observed_at and confidence >= STRONG_BELIEF_MIN_CONFIDENCE:
            today = today or datetime.now(timezone.utc)
            first = first_observed_at
            if first.tzinfo is None:
                first = first.replace(tzinfo=timezone.utc)
            if (today - first).days >= STRONG_BELIEF_MIN_AGE_DAYS:
                return "strong_belief"
        return "validated_belief"
    if n >= WEAK_BELIEF_MIN_N and confidence >= WEAK_BELIEF_MIN_CONFIDENCE:
        return "weak_belief"
    return "hypothesis"


def _log_history(sb, belief_id: str, change_type: str,
                 confidence_before: Optional[float],
                 confidence_after: Optional[float],
                 evidence_n_before: Optional[int],
                 evidence_n_after: Optional[int],
                 status_before: Optional[str],
                 status_after: Optional[str],
                 reason: Optional[str] = None,
                 related_outcome_id: Optional[str] = None) -> None:
    sb.table("beliefs_history").insert({
        "belief_id": belief_id,
        "change_type": change_type,
        "confidence_before": confidence_before,
        "confidence_after": confidence_after,
        "evidence_n_before": evidence_n_before,
        "evidence_n_after": evidence_n_after,
        "status_before": status_before,
        "status_after": status_after,
        "reason": reason,
        "related_outcome_id": related_outcome_id,
    }).execute()


def create_belief(
    belief_key: str,
    belief_text: str,
    initial_confidence: float = 0.4,
    category: Optional[str] = None,
    prescription: Optional[str] = None,
    expected_outcome: Optional[str] = None,
    source: Optional[str] = None,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    metadata: Optional[dict] = None,
) -> str:
    """Crea o ritorna ID di belief esistente con stesso key."""
    # Import qui per evitare circular
    from coach.analytics.belief_guardrails import check_belief_admissible

    sb = get_supabase()
    existing = sb.table("beliefs").select("*").eq("belief_key", belief_key).limit(1).execute()
    if existing.data:
        logger.info("Belief %s already exists, returning id %s", belief_key, existing.data[0]["id"])
        return existing.data[0]["id"]

    admissible, flag_reason = check_belief_admissible(
        belief_text=belief_text, initial_confidence=initial_confidence,
        evidence_n=1, prescription=prescription,
    )

    status = _compute_status(1, initial_confidence)
    row = {
        "belief_key": belief_key,
        "belief_text": belief_text,
        "confidence": initial_confidence,
        "evidence_n": 1,
        "status": status,
        "category": category,
        "prescription": prescription,
        "expected_outcome": expected_outcome,
        "evidence_decay_half_life_days": half_life_days,
        "source": source,
        "flagged": not admissible,
        "flag_reason": flag_reason if not admissible else None,
        "metadata": metadata,
        "last_reinforced_at": datetime.now(timezone.utc).isoformat(),
    }
    row = {k: v for k, v in row.items() if v is not None}
    res = sb.table("beliefs").insert(row).execute()
    bid = res.data[0]["id"]
    _log_history(sb, bid, "created", None, initial_confidence, None, 1,
                 None, status, reason=source)
    logger.info("Belief created: %s (status=%s, conf=%s, admissible=%s)",
                belief_key, status, initial_confidence, admissible)
    return bid


def reinforce_belief(belief_key: str, related_outcome_id: Optional[str] = None,
                     reason: Optional[str] = None) -> Optional[Belief]:
    """Aggiunge evidenza positiva: n+=1, confidence += boost (cap 0.95)."""
    sb = get_supabase()
    res = sb.table("beliefs").select("*").eq("belief_key", belief_key).limit(1).execute()
    if not res.data:
        logger.warning("Belief %s not found for reinforcement", belief_key)
        return None
    b = res.data[0]

    # Una belief confutata a mano (flagged) NON va ri-rinforzata in automatico:
    # la confutazione con un fatto noto deve "tenere" finché un umano non la
    # sblocca. Prima il reinforce post-sessione la gonfiava di nuovo.
    if b.get("flagged"):
        logger.info("Belief %s flagged (confutata) — skip reinforce automatico", belief_key)
        return _row_to_belief(b)

    # Una belief retired NON va resuscitata da un reinforce automatico:
    # è stata ritirata per evidenza contraria accumulata / decay.
    if b.get("status") == "retired":
        logger.info("Belief %s retired — skip reinforce automatico", belief_key)
        return _row_to_belief(b)

    conf_before = float(b["confidence"])
    n_before = int(b["evidence_n"])
    status_before = b["status"]

    n_after = n_before + 1
    # Diminishing returns: boost cala con n grande
    boost = REINFORCE_BOOST / max(1.0, math.log10(max(n_after, 2)))
    conf_after = min(0.95, conf_before + boost)
    status_after = _compute_status(
        n_after, conf_after,
        first_observed_at=_parse_ts(b.get("first_observed_at")),
    )

    supporting = list(b.get("supporting_outcomes") or [])
    if related_outcome_id and related_outcome_id not in supporting:
        supporting.append(related_outcome_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {
        "confidence": conf_after,
        "evidence_n": n_after,
        "status": status_after,
        "supporting_outcomes": supporting,
        "last_reinforced_at": now_iso,
        "last_updated_at": now_iso,
    }
    sb.table("beliefs").update(updates).eq("id", b["id"]).execute()

    change_type = "promoted" if status_after != status_before and \
        _rank(status_after) > _rank(status_before) else "reinforced"
    _log_history(sb, b["id"], change_type, conf_before, conf_after,
                 n_before, n_after, status_before, status_after,
                 reason=reason, related_outcome_id=related_outcome_id)
    logger.info("Belief %s reinforced: n %d→%d conf %.2f→%.2f status %s→%s",
                belief_key, n_before, n_after, conf_before, conf_after,
                status_before, status_after)
    # Ritorna lo stato POST-update, non la row letta pre-update.
    return _row_to_belief({**b, **updates})


def contradict_belief(belief_key: str, related_outcome_id: Optional[str] = None,
                      reason: Optional[str] = None) -> Optional[Belief]:
    """Aggiunge evidenza contraria: confidence -= penalty (floor 0.05).

    Non cancella belief mai. Se confidence < 0.1 e n > 5 → demote a 'retired'.
    """
    sb = get_supabase()
    res = sb.table("beliefs").select("*").eq("belief_key", belief_key).limit(1).execute()
    if not res.data:
        logger.warning("Belief %s not found for contradiction", belief_key)
        return None
    b = res.data[0]
    conf_before = float(b["confidence"])
    n_before = int(b["evidence_n"])
    status_before = b["status"]

    # Contradictions weigh more than reinforcements (asymmetric Bayesian)
    n_after = n_before + 1  # contradictions count toward n (più dati = stato più informato)
    conf_after = max(0.05, conf_before - CONTRADICT_PENALTY)
    status_after = _compute_status(
        n_after, conf_after,
        first_observed_at=_parse_ts(b.get("first_observed_at")),
    )
    # Retired se conf molto bassa con n grande (evidenza chiara di contro)
    if conf_after < 0.15 and n_after >= 5:
        status_after = "retired"

    contradicting = list(b.get("contradicting_outcomes") or [])
    if related_outcome_id and related_outcome_id not in contradicting:
        contradicting.append(related_outcome_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {
        "confidence": conf_after,
        "evidence_n": n_after,
        "status": status_after,
        "contradicting_outcomes": contradicting,
        "last_contradicted_at": now_iso,
        "last_updated_at": now_iso,
    }
    sb.table("beliefs").update(updates).eq("id", b["id"]).execute()

    change_type = "demoted" if _rank(status_after) < _rank(status_before) else "contradicted"
    _log_history(sb, b["id"], change_type, conf_before, conf_after,
                 n_before, n_after, status_before, status_after,
                 reason=reason, related_outcome_id=related_outcome_id)
    logger.info("Belief %s contradicted: n %d→%d conf %.2f→%.2f status %s→%s",
                belief_key, n_before, n_after, conf_before, conf_after,
                status_before, status_after)
    # Ritorna lo stato POST-update, non la row letta pre-update.
    return _row_to_belief({**b, **updates})


def list_beliefs(min_status: str = "weak_belief",
                 category: Optional[str] = None,
                 include_flagged: bool = False) -> list[Belief]:
    """Lista belief filtrate per status minimo + categoria."""
    sb = get_supabase()
    query = sb.table("beliefs").select("*").not_.eq("status", "retired")
    if category:
        query = query.eq("category", category)
    if not include_flagged:
        query = query.eq("flagged", False)
    res = query.order("confidence", desc=True).execute()
    out: list[Belief] = []
    for r in res.data or []:
        if _rank(r["status"]) >= _rank(min_status):
            out.append(_row_to_belief(r))
    return out


def get_actionable_beliefs(category: Optional[str] = None) -> list[Belief]:
    """Solo beliefs validated/strong, usate in proposte (priority 5 nell'engine)."""
    return list_beliefs(min_status="validated_belief", category=category)


def decay_old_beliefs(today: Optional[datetime] = None) -> int:
    """Cron settimanale: applica decay sulle beliefs vecchie + retira quelle <0.1.

    Returns: numero di beliefs aggiornate.
    """
    sb = get_supabase()
    today = today or datetime.now(timezone.utc)
    res = sb.table("beliefs").select("*").not_.eq("status", "retired").execute()
    n_updated = 0
    for r in res.data or []:
        b = _row_to_belief(r)
        eff = b.effective_confidence(today=today)
        if abs(eff - b.confidence) < 0.01:
            continue  # niente decay significativo
        new_status = _compute_status(b.evidence_n, eff,
                                     first_observed_at=b.first_observed_at, today=today)
        if eff < 0.15 and b.evidence_n >= 5:
            new_status = "retired"
        # last_reinforced_at va riallineato a oggi: la confidence persistita
        # ha GIÀ il decay applicato. Senza reset, il prossimo decay riparte
        # dal vecchio timestamp e compone il decay (~4-6x troppo veloce).
        sb.table("beliefs").update({
            "confidence": eff,
            "status": new_status,
            "last_reinforced_at": today.isoformat(),
            "last_updated_at": today.isoformat(),
        }).eq("id", b.id).execute()
        _log_history(sb, b.id, "decayed", b.confidence, eff,
                     b.evidence_n, b.evidence_n, b.status, new_status,
                     reason="evidence decay cron")
        n_updated += 1
    logger.info("Decay cron: %d beliefs updated", n_updated)
    return n_updated


# ============================================================================
# Helpers
# ============================================================================

STATUS_RANK = {
    "retired": -1,
    "hypothesis": 0,
    "weak_belief": 1,
    "validated_belief": 2,
    "strong_belief": 3,
}


def _rank(status: str) -> int:
    return STATUS_RANK.get(status, 0)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _row_to_belief(row: dict) -> Belief:
    return Belief(
        id=row.get("id"),
        belief_key=row["belief_key"],
        belief_text=row["belief_text"],
        confidence=float(row["confidence"]),
        evidence_n=int(row["evidence_n"]),
        status=row["status"],
        category=row.get("category"),
        prescription=row.get("prescription"),
        expected_outcome=row.get("expected_outcome"),
        supporting_outcomes=list(row.get("supporting_outcomes") or []),
        contradicting_outcomes=list(row.get("contradicting_outcomes") or []),
        evidence_decay_half_life_days=int(
            row.get("evidence_decay_half_life_days") or DEFAULT_HALF_LIFE_DAYS
        ),
        first_observed_at=_parse_ts(row.get("first_observed_at")),
        last_updated_at=_parse_ts(row.get("last_updated_at")),
        last_reinforced_at=_parse_ts(row.get("last_reinforced_at")),
        flagged=bool(row.get("flagged", False)),
        flag_reason=row.get("flag_reason"),
        source=row.get("source"),
    )


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="Lista beliefs validated/strong")
    p.add_argument("--decay", action="store_true", help="Run decay cron")
    args = p.parse_args()
    if args.list:
        bs = get_actionable_beliefs()
        for b in bs:
            print(f"{STATUS_EMOJI.get(b.status, '?')} [{b.status}] "
                  f"{b.belief_key} (n={b.evidence_n}, conf={b.confidence})")
            print(f"    {b.belief_text}")
            if b.prescription:
                print(f"    → {b.prescription}")
    elif args.decay:
        n = decay_old_beliefs()
        print(f"Decayed {n} beliefs")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
