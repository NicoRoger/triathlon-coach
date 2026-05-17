"""Fase 3.4 — Decision provenance / audit trail.

Per ogni decisione strutturale del coach, salva un record completo:
- Tipo decisione
- Input considerati (CTL, TSB, HRV, race proximity, etc.)
- Beliefs invocate
- Citazioni scientifiche
- Risk scores valutati
- Tradeoff
- Confidence

Questo permette di rispondere a "perché abbiamo proposto X mesi fa?" e di
auditare retrospettivamente le decisioni del sistema.

API principale: `record_decision()` chiamata dai moduli che producono
proposte (weekly_review consuma e logga; modulation.py logga proposta;
test_scheduler logga test pianificato).

Decision_audit è il prerequisito del priority engine (Fase 4.2) che
produrrà output strutturato direttamente serializzabile in questa tabella.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# Decision types: alle aggiunte serve solo update commento (non vincolo DB)
DECISION_TYPES = {
    "weekly_review",
    "mesocycle_commit",
    "modulation_applied",
    "modulation_proposed",
    "race_briefing",
    "session_proposal",
    "test_scheduled",
    "test_prediction",
    "manual_override",
    "auto_volume_reduction",
}


# ============================================================================
# Public API
# ============================================================================

def record_decision(
    decision_type: str,
    decision_summary: str,
    data_inputs: Optional[dict] = None,
    beliefs_used: Optional[list[dict]] = None,
    citations: Optional[list[dict]] = None,
    risks_considered: Optional[dict] = None,
    tradeoffs: Optional[dict] = None,
    confidence: Optional[float] = None,
    expected_outcome: Optional[str] = None,
    related_prediction_ids: Optional[list[str]] = None,
    applied: bool = False,
    metadata: Optional[dict] = None,
) -> str:
    """Persiste una decisione del coach con audit completo. Ritorna id.

    Args:
        decision_type: chiave da DECISION_TYPES (es. 'weekly_review')
        decision_summary: 1-3 righe descrizione della decisione
        data_inputs: dict con metriche/state usati (ctl, tsb, hrv_z, readiness, flags)
        beliefs_used: lista di {belief: str, confidence: float, source: str}
        citations: lista di {source: str, topic: str} (es. {source: "Seiler 2010", topic: "polarized"})
        risks_considered: dict con overreaching/injury/recovery scores
        tradeoffs: dict con sacrificed/gained chiavi
        confidence: 0-1 self-assessment della decisione
        expected_outcome: stringa descrittiva (es. "+3 CTL fine settimana")
        related_prediction_ids: UUID di predictions correlate
        applied: True se decisione applicata immediatamente; False se attende conferma
        metadata: extra fields
    """
    if decision_type not in DECISION_TYPES:
        logger.warning("Unknown decision_type=%s (consider adding to DECISION_TYPES)", decision_type)

    sb = get_supabase()
    row = {
        "decision_type": decision_type,
        "decision_summary": decision_summary,
        "data_inputs": data_inputs,
        "beliefs_used": beliefs_used,
        "citations": citations,
        "risks_considered": risks_considered,
        "tradeoffs": tradeoffs,
        "confidence": confidence,
        "expected_outcome": expected_outcome,
        "related_prediction_ids": related_prediction_ids or [],
        "applied": applied,
        "applied_at": datetime.utcnow().isoformat() if applied else None,
        "metadata": metadata,
    }
    row = {k: v for k, v in row.items() if v is not None}
    res = sb.table("decision_audit").insert(row).execute()
    did = res.data[0]["id"]
    logger.info("Decision recorded: type=%s id=%s confidence=%s applied=%s",
                decision_type, did, confidence, applied)
    return did


def mark_applied(decision_id: str) -> None:
    """Segna una decisione come applicata (passa da 'proposed' a 'applied')."""
    sb = get_supabase()
    sb.table("decision_audit").update({
        "applied": True,
        "applied_at": datetime.utcnow().isoformat(),
    }).eq("id", decision_id).execute()


def mark_overridden(decision_id: str, reason: str) -> None:
    """L'atleta ha rifiutato/modificato la decisione. Salva motivo."""
    sb = get_supabase()
    sb.table("decision_audit").update({
        "overridden": True,
        "override_reason": reason,
    }).eq("id", decision_id).execute()


# ============================================================================
# Helpers: parsing citazioni e beliefs dal testo
# ============================================================================

CITATION_PATTERN = re.compile(r"\[source:\s*([^\]]+)\]", re.IGNORECASE)
BELIEF_PATTERN = re.compile(
    r"\[athlete-belief:\s*(.+?)(?:\s*\(n=(\d+)(?:,\s*conf=([\d.]+))?\))?\]",
    re.IGNORECASE,
)


def extract_citations(text: str) -> list[dict]:
    """Estrae [source: ...] tags dal testo prodotto da skill weekly_review/etc.

    Output: lista di {"source": "Seiler 2010", "topic": "polarized 80/20"}
    Topic è dedotto dal contesto immediatamente precedente (50 char).
    """
    citations: list[dict] = []
    for m in CITATION_PATTERN.finditer(text):
        source = m.group(1).strip()
        # Topic = parole prima della citation (fino a 50 char), rimuovi punteggiatura
        start = max(0, m.start() - 80)
        before = text[start:m.start()].rstrip()
        # Prendi le ultime 5-10 parole
        words = re.findall(r"\w+", before)
        topic = " ".join(words[-6:]) if words else None
        citations.append({"source": source, "topic": topic})
    return citations


def extract_beliefs(text: str) -> list[dict]:
    """Estrae [athlete-belief: ... (n=X, conf=Y)] tags."""
    beliefs: list[dict] = []
    for m in BELIEF_PATTERN.finditer(text):
        belief = m.group(1).strip()
        n = int(m.group(2)) if m.group(2) else None
        conf = float(m.group(3)) if m.group(3) else None
        entry: dict = {"belief": belief}
        if n is not None:
            entry["evidence_n"] = n
        if conf is not None:
            entry["confidence"] = conf
        beliefs.append(entry)
    return beliefs


def audit_from_text(
    decision_type: str,
    decision_text: str,
    data_inputs: Optional[dict] = None,
    risks_considered: Optional[dict] = None,
    confidence: Optional[float] = None,
    expected_outcome: Optional[str] = None,
    related_prediction_ids: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Helper: estrae citations + beliefs dal testo e crea record decision_audit.

    Usato dalle skill che producono output testuale ricco di tag inline.
    """
    citations = extract_citations(decision_text)
    beliefs = extract_beliefs(decision_text)
    summary = decision_text[:300]
    return record_decision(
        decision_type=decision_type,
        decision_summary=summary,
        data_inputs=data_inputs,
        beliefs_used=beliefs or None,
        citations=citations or None,
        risks_considered=risks_considered,
        confidence=confidence,
        expected_outcome=expected_outcome,
        related_prediction_ids=related_prediction_ids,
        metadata={**(metadata or {}), "raw_text_preview": decision_text[:500]},
    )


# ============================================================================
# Query helpers
# ============================================================================

def recent_decisions(decision_type: Optional[str] = None, days: int = 30) -> list[dict]:
    """Restituisce decisioni recenti, opzionalmente filtrate per tipo."""
    sb = get_supabase()
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    q = sb.table("decision_audit").select("*").gte("created_at", since)
    if decision_type:
        q = q.eq("decision_type", decision_type)
    res = q.order("created_at", desc=True).execute()
    return res.data or []


def decision_summary_by_type(days: int = 30) -> dict[str, int]:
    """Conteggio per tipo nelle ultime N giorni."""
    rows = recent_decisions(days=days)
    counts: dict[str, int] = {}
    for r in rows:
        t = r.get("decision_type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


def main() -> None:
    """CLI: --summary | --type <decision_type>."""
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--summary", action="store_true", help="Conteggio per tipo")
    p.add_argument("--type", type=str, help="Lista decisioni recenti di tipo")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    if args.summary:
        counts = decision_summary_by_type(args.days)
        print(json.dumps(counts, indent=2))
    elif args.type:
        rows = recent_decisions(decision_type=args.type, days=args.days)
        for r in rows:
            print(f"[{r['created_at']}] {r['decision_type']}: {r['decision_summary'][:120]}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
