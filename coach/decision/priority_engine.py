"""Fase 4.2 — Decision Priority Engine.

Motore di arbitration rigido per risolvere conflitti fra priorità.

Gerarchia (priority 1 vince sempre su priority 9):
  1. Athlete safety constraints (HARD)
  2. Acute recovery state
  3. Injury / illness state
  4. Race proximity + race priority
  5. Athlete-specific validated beliefs (status >= validated_belief, conf > 0.6)
  6. Long-term progression goals
  7. Scientific literature priors
  8. Athlete preferences
  9. Session-level optimization

Rule invariante: nessuna ottimizzazione fitness può overrideare safety,
injury escalation, recovery collapse. Priority 1-3 sono HARD constraints.

Output: DecisionOutcome con winning_priority, overridden_priorities, reason,
tradeoffs quantificati. Ogni decisione strutturale del coach DEVE passare di qui.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import IntEnum
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Priority hierarchy
# ============================================================================

class Priority(IntEnum):
    SAFETY = 1
    RECOVERY = 2
    INJURY_ILLNESS = 3
    RACE_PROXIMITY = 4
    VALIDATED_BELIEFS = 5
    LONG_TERM_PROGRESSION = 6
    LITERATURE = 7
    ATHLETE_PREFERENCES = 8
    SESSION_OPTIMIZATION = 9


PRIORITY_NAMES: dict[int, str] = {
    1: "Safety constraints",
    2: "Acute recovery state",
    3: "Injury/illness state",
    4: "Race proximity + priority",
    5: "Validated athlete beliefs",
    6: "Long-term progression",
    7: "Scientific literature priors",
    8: "Athlete preferences",
    9: "Session-level optimization",
}

# Priority HARD (non possono essere overridden da niente sotto)
HARD_PRIORITIES = {Priority.SAFETY, Priority.RECOVERY, Priority.INJURY_ILLNESS}


# ============================================================================
# Context input
# ============================================================================

@dataclass
class DecisionContext:
    """Input al priority engine: stato completo dell'atleta + opzioni considerate.

    Tutti i campi sono opzionali — il motore considera solo i fattori presenti.
    """
    # Safety (priority 1)
    safety_blockers: list[str] = field(default_factory=list)
    # es. ["temperatura corporea 38°C", "dolore acuto severity=severe"]

    # Recovery (priority 2)
    readiness_score: Optional[float] = None         # 0-100
    hrv_z_score: Optional[float] = None
    tsb: Optional[float] = None
    recovery_flags: list[str] = field(default_factory=list)
    # es. ["fatigue_critical", "hrv_z<-2"]

    # Injury/illness (priority 3)
    active_injury_severity: Optional[str] = None    # mild | moderate | severe | None
    active_illness_severity: Optional[str] = None
    body_location: Optional[str] = None

    # Race (priority 4)
    days_to_next_race_a: Optional[int] = None
    days_to_next_race_b: Optional[int] = None
    race_week_phase: Optional[str] = None           # taper | race | post_race | None

    # Validated beliefs (priority 5)
    applicable_validated_beliefs: list[dict] = field(default_factory=list)
    # Each: {belief_key, belief_text, prescription, confidence}

    # Long-term (priority 6)
    mesocycle_phase: Optional[str] = None           # base | build | specific | peak | taper | recovery
    weekly_volume_target_min: Optional[float] = None
    weekly_volume_actual_min: Optional[float] = None

    # Literature priors (priority 7)
    literature_priors: list[dict] = field(default_factory=list)
    # Each: {principle, source, recommendation}

    # Athlete preferences (priority 8)
    athlete_preferences: list[str] = field(default_factory=list)

    # Session optimization (priority 9)
    proposed_session: Optional[dict] = None

    # Metadata
    decision_topic: str = "generic"                 # weekly_review | modulation | session_proposal
    today: Optional[date] = None


# ============================================================================
# Outcome output
# ============================================================================

@dataclass
class DecisionOutcome:
    """Output strutturato del priority engine."""
    decision: str
    winning_priority: int
    winning_priority_name: str
    overridden_priorities: list[int]
    reason: str
    tradeoffs: dict[str, str] = field(default_factory=dict)
    safety_blocks: list[str] = field(default_factory=list)
    applied_beliefs: list[str] = field(default_factory=list)
    applied_citations: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Risolutore principale
# ============================================================================

def resolve_decision(ctx: DecisionContext,
                     candidate_decisions: Optional[list[dict]] = None) -> DecisionOutcome:
    """Risolve una decisione tenendo conto della gerarchia rigida.

    Args:
        ctx: stato completo dell'atleta
        candidate_decisions: opzionale, lista di alternative da considerare.
            Ogni dict: {label, priority_source, action, expected_gain, expected_cost}
            Se None, il motore propone una decisione default basata sul fattore winning.

    Returns:
        DecisionOutcome con decisione winning, priority + tradeoff espliciti.
    """
    # 1. Safety blockers (priority 1) → blocco assoluto
    if ctx.safety_blockers:
        return DecisionOutcome(
            decision="STOP — block training/intensity",
            winning_priority=Priority.SAFETY,
            winning_priority_name=PRIORITY_NAMES[Priority.SAFETY],
            overridden_priorities=[],
            reason=f"Safety blockers attivi: {', '.join(ctx.safety_blockers)}",
            safety_blocks=ctx.safety_blockers,
            tradeoffs={
                "sacrificed": "tutte le altre considerazioni (race, beliefs, fitness)",
                "gained": "integrità dell'atleta",
            },
        )

    overridden: list[int] = []

    # 2. Recovery critical
    recovery_critical = (
        (ctx.readiness_score is not None and ctx.readiness_score < 40)
        or (ctx.hrv_z_score is not None and ctx.hrv_z_score < -2.0)
        or "fatigue_critical" in (ctx.recovery_flags or [])
    )
    if recovery_critical:
        return DecisionOutcome(
            decision="Recovery day — only Z1 or off",
            winning_priority=Priority.RECOVERY,
            winning_priority_name=PRIORITY_NAMES[Priority.RECOVERY],
            overridden_priorities=_below(Priority.RECOVERY),
            reason=(
                f"Recovery state critico: readiness={ctx.readiness_score}, "
                f"HRV_z={ctx.hrv_z_score}, flags={ctx.recovery_flags}"
            ),
            tradeoffs={
                "performance_gain_sacrificed": "estimato -1 a -2 CTL nel breve",
                "recovery_debt_reduction": "alta",
                "injury_probability_reduction": "moderate",
            },
        )

    # 2b. Recovery warning (CLAUDE.md §5.2, non-hard): fatigue_warning
    # (HRV z<-1 per 2 giorni consecutivi) → sostituisci sessione intensa con Z2
    if "fatigue_warning" in (ctx.recovery_flags or []):
        return DecisionOutcome(
            decision="Sostituisci sessione intensa con Z2 60-75min",
            winning_priority=Priority.RECOVERY,
            winning_priority_name=PRIORITY_NAMES[Priority.RECOVERY],
            overridden_priorities=_below(Priority.RECOVERY),
            reason=(
                f"fatigue_warning attivo (HRV z<-1.0 per 2+ giorni consecutivi): "
                f"HRV_z={ctx.hrv_z_score}, readiness={ctx.readiness_score}. "
                "Regola CLAUDE.md §5.2."
            ),
            tradeoffs={
                "performance_gain_sacrificed": "1 sessione qualità posticipata",
                "recovery_debt_reduction": "moderate",
                "injury_probability_reduction": "moderate",
            },
        )

    # 2c. trend_negative + TSB < -20 (CLAUDE.md §5.2) → anticipa scarico
    if "trend_negative" in (ctx.recovery_flags or []) and ctx.tsb is not None and ctx.tsb < -20:
        return DecisionOutcome(
            decision="Anticipa scarico 2-3 giorni",
            winning_priority=Priority.RECOVERY,
            winning_priority_name=PRIORITY_NAMES[Priority.RECOVERY],
            overridden_priorities=_below(Priority.RECOVERY),
            reason=(
                f"trend_negative (HRV rolling 7d >5% sotto baseline 28d) con "
                f"TSB={ctx.tsb} < -20: fatica cumulativa. Regola CLAUDE.md §5.2."
            ),
            tradeoffs={
                "performance_gain_sacrificed": "2-3 giorni di carico pianificato",
                "recovery_debt_reduction": "high",
                "injury_probability_reduction": "moderate",
            },
        )

    # 3. Injury/illness escalation
    if ctx.active_injury_severity in ("severe",) or ctx.active_illness_severity in ("severe",):
        return DecisionOutcome(
            decision="STOP training — recovery only + medical assessment",
            winning_priority=Priority.INJURY_ILLNESS,
            winning_priority_name=PRIORITY_NAMES[Priority.INJURY_ILLNESS],
            overridden_priorities=_below(Priority.INJURY_ILLNESS),
            reason=(
                f"Severity severe: injury={ctx.active_injury_severity}, "
                f"illness={ctx.active_illness_severity}"
            ),
            tradeoffs={
                "performance_gain_sacrificed": "alto (1-2 settimane CTL)",
                "injury_probability_reduction": "high (prevenzione cronicizzazione)",
            },
        )
    if ctx.active_injury_severity == "moderate" or ctx.active_illness_severity == "moderate":
        return DecisionOutcome(
            decision="Reduce volume 30-50%, swap intensity to Z1-Z2 only",
            winning_priority=Priority.INJURY_ILLNESS,
            winning_priority_name=PRIORITY_NAMES[Priority.INJURY_ILLNESS],
            overridden_priorities=_below(Priority.INJURY_ILLNESS),
            reason=(
                f"Injury/illness moderate ({ctx.active_injury_severity or ctx.active_illness_severity}, "
                f"location={ctx.body_location or 'n/a'}). Sostegno aerobico, no carichi acuti."
            ),
            tradeoffs={
                "performance_gain_sacrificed": "stimato -2 a -3 CTL settimana",
                "injury_probability_reduction": "moderate-high",
                "recovery_debt_reduction": "moderate",
            },
        )

    # 4. Race proximity HIGH (T-2 to T-7 for A or T-3 for B)
    if ctx.days_to_next_race_a is not None and 0 <= ctx.days_to_next_race_a <= 7:
        d = ctx.days_to_next_race_a
        return DecisionOutcome(
            decision=f"Race week protocol attivo (T-{d}, race A)",
            winning_priority=Priority.RACE_PROXIMITY,
            winning_priority_name=PRIORITY_NAMES[Priority.RACE_PROXIMITY],
            overridden_priorities=_below(Priority.RACE_PROXIMITY),
            reason=f"Race A in {d}gg: taper [Mujika 2003] override su build/progression",
            applied_citations=[{"source": "Mujika & Padilla 2003", "topic": "tapering response"}],
            tradeoffs={
                "performance_gain_sacrificed": "0 (tapering è performance-positive)",
                "fatigue_reduction": "high",
                "race_readiness": "max",
            },
        )

    # 4b. Race B a T-3 o meno: scarico breve, NIENTE taper completo — una gara
    # di preparazione non deve distruggere la settimana di carico.
    if ctx.days_to_next_race_b is not None and 0 <= ctx.days_to_next_race_b <= 3:
        d = ctx.days_to_next_race_b
        return DecisionOutcome(
            decision=f"Scarico breve pre-gara B (T-{d}) — niente taper completo",
            winning_priority=Priority.RACE_PROXIMITY,
            winning_priority_name=PRIORITY_NAMES[Priority.RACE_PROXIMITY],
            overridden_priorities=_below(Priority.RACE_PROXIMITY),
            reason=(
                f"Race B in {d}gg: riduzione volume solo negli ultimi 2-3 giorni, "
                "settimana di carico preservata (gara di preparazione)."
            ),
            tradeoffs={
                "performance_gain_sacrificed": "minima (2-3gg volume ridotto)",
                "race_b_execution": "buona senza compromettere il blocco",
            },
        )

    # 5. Validated beliefs applicabili
    actionable = [b for b in (ctx.applicable_validated_beliefs or [])
                  if b.get("confidence", 0) > 0.6
                  and b.get("status") in ("validated_belief", "strong_belief")]
    if actionable:
        b = actionable[0]
        below = _below(Priority.VALIDATED_BELIEFS)
        overridden.extend(below)
        return DecisionOutcome(
            decision=f"Applica belief: {b.get('prescription', b['belief_text'])}",
            winning_priority=Priority.VALIDATED_BELIEFS,
            winning_priority_name=PRIORITY_NAMES[Priority.VALIDATED_BELIEFS],
            overridden_priorities=below,
            reason=(
                f"Belief validated '{b['belief_key']}' (n={b.get('evidence_n', '?')}, "
                f"conf={b.get('confidence')}) applicabile in questo contesto."
            ),
            applied_beliefs=[b["belief_key"]],
            tradeoffs={
                "personalization_gain": "high",
                "literature_default_overridden": "yes",
            },
        )

    # 6. Long-term progression (mesociclo phase coherent)
    if ctx.mesocycle_phase:
        d = _default_decision_by_phase(ctx)
        return DecisionOutcome(
            decision=d["text"],
            winning_priority=Priority.LONG_TERM_PROGRESSION,
            winning_priority_name=PRIORITY_NAMES[Priority.LONG_TERM_PROGRESSION],
            overridden_priorities=_below(Priority.LONG_TERM_PROGRESSION),
            reason=f"Fase mesociclo {ctx.mesocycle_phase}: {d['rationale']}",
            applied_citations=d.get("citations", []),
            tradeoffs={"progression_alignment": "high"},
        )

    # 7-9. Literature default fallback
    return DecisionOutcome(
        decision="Sessione standard come da literature default (polarized Z1-Z2)",
        winning_priority=Priority.LITERATURE,
        winning_priority_name=PRIORITY_NAMES[Priority.LITERATURE],
        overridden_priorities=[],
        reason="Nessun fattore higher-priority attivo. Applica default Seiler polarized.",
        applied_citations=[{"source": "Seiler 2010", "topic": "polarized 80/20"}],
        tradeoffs={"safety": "preserved", "personalization": "low (literature default)"},
    )


# ============================================================================
# Helpers
# ============================================================================

def _below(p: Priority) -> list[int]:
    """Lista priority overridden (tutte sotto p)."""
    return [v.value for v in Priority if v.value > p.value]


def _default_decision_by_phase(ctx: DecisionContext) -> dict:
    """Decisione default coerente con la fase del mesociclo corrente."""
    phase = ctx.mesocycle_phase
    if phase == "base":
        return {
            "text": "Volume Z2 progressivo (80/20 polarized), niente qualità",
            "rationale": "fase base: costruzione aerobic, RPE ≤ 6",
            "citations": [{"source": "Seiler 2010", "topic": "polarized 80/20"}],
        }
    if phase == "build":
        return {
            "text": "Build: 1 sessione qualità (threshold/sweet spot) + volume Z2",
            "rationale": "fase build: aerobic + threshold development",
            "citations": [{"source": "Issurin 2008", "topic": "block periodization"}],
        }
    if phase == "specific":
        return {
            "text": "Specific: race-pace simulation + volume Z2 stabile",
            "rationale": "fase specific: adattamento metabolico race-specific",
            "citations": [{"source": "Issurin 2008", "topic": "block periodization"}],
        }
    if phase == "peak":
        return {
            "text": "Peak: 2 sessioni intense brevi + volume ridotto -15%",
            "rationale": "fase peak: massima espressione potenza, fatica controllata",
            "citations": [{"source": "Mujika 2003", "topic": "peak performance"}],
        }
    if phase == "taper":
        return {
            "text": "Taper: volume -40%, intensità mantenuta in micro-dosi",
            "rationale": "fase taper: scarico volume preserve intensity",
            "citations": [{"source": "Mujika & Padilla 2003", "topic": "tapering response"}],
        }
    if phase == "recovery":
        return {
            "text": "Recovery: Z1 only, volume basso (50% normale)",
            "rationale": "fase recovery: ripristino post-stress",
            "citations": [],
        }
    return {
        "text": "Sessione standard (default Z2 polarized)",
        "rationale": "fase non specificata",
        "citations": [{"source": "Seiler 2010", "topic": "polarized 80/20"}],
    }


def main() -> None:
    import json
    logging.basicConfig(level=logging.INFO)
    # Demo: 4 scenari
    scenarios = [
        ("Safety block", DecisionContext(
            safety_blockers=["febbre 38.5°C confermata"],
            decision_topic="weekly_review",
        )),
        ("Injury moderate + race week", DecisionContext(
            active_injury_severity="moderate",
            body_location="fascite plantare",
            days_to_next_race_a=5,
            readiness_score=70,
            decision_topic="weekly_review",
        )),
        ("Recovery critical", DecisionContext(
            readiness_score=35,
            hrv_z_score=-2.4,
            recovery_flags=["fatigue_critical"],
            decision_topic="modulation",
        )),
        ("Validated belief in base phase", DecisionContext(
            readiness_score=85,
            mesocycle_phase="base",
            applicable_validated_beliefs=[{
                "belief_key": "hrv_low_saturday",
                "belief_text": "HRV basso sabato",
                "prescription": "Sposta qualità da sabato a mercoledì",
                "confidence": 0.82,
                "evidence_n": 12,
                "status": "validated_belief",
            }],
            decision_topic="weekly_review",
        )),
        ("Pure base phase, no signals", DecisionContext(
            readiness_score=80,
            mesocycle_phase="base",
            decision_topic="session_proposal",
        )),
    ]
    for label, ctx in scenarios:
        print(f"\n=== {label} ===")
        out = resolve_decision(ctx)
        print(f"Decision: {out.decision}")
        print(f"Winning priority: {out.winning_priority} ({out.winning_priority_name})")
        print(f"Reason: {out.reason}")
        if out.tradeoffs:
            print(f"Tradeoffs: {out.tradeoffs}")


if __name__ == "__main__":
    main()
