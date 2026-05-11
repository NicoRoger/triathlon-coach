"""Blocco 3.2 — Adaptive Planner: compliance analysis + auto-adjustments.

Analizza la compliance settimanale (planned_sessions vs activities) e
propone adattamenti automatici per la settimana successiva.

Regole AUTO-APPLY (senza conferma):
  - compliance < 70% → riduci volume 10%
  - sessioni nuoto saltate per spalla → sposta su bici/corsa
  - RPE medio > 7.5 → aggiungi giorno recovery extra

Regole PROPOSTA (richiede conferma):
  - compliance < 50% → proponi piano ridotto
  - sessione chiave saltata (long run, key interval) → proponi sostituzione

Uso: python -m coach.coaching.adaptive_planner
Integrato in ingest.yml domenica sera.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


@dataclass
class WeeklyCompliance:
    week_start: date
    planned_count: int
    completed_count: int
    missed_sports: list[str]
    avg_rpe: Optional[float]
    compliance_pct: float
    total_planned_duration_min: int
    total_actual_duration_min: int


@dataclass
class Adjustment:
    kind: str  # "auto" | "proposal"
    action: str
    reason: str
    sport: Optional[str] = None
    details: dict = field(default_factory=dict)


def compute_weekly_compliance(week_start: Optional[date] = None) -> WeeklyCompliance:
    """Calcola compliance della settimana specificata (default: settimana scorsa)."""
    sb = get_supabase()
    today = today_rome()

    if week_start is None:
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday + 7)

    week_end = week_start + timedelta(days=6)

    planned_res = sb.table("planned_sessions").select(
        "planned_date,sport,session_type,duration_s,status"
    ).gte("planned_date", week_start.isoformat()).lte(
        "planned_date", week_end.isoformat()
    ).execute()
    planned = planned_res.data or []

    activities_res = sb.table("activities").select(
        "started_at,sport,duration_s,tss"
    ).gte("started_at", week_start.isoformat()).lte(
        "started_at", (week_end + timedelta(days=1)).isoformat()
    ).execute()
    activities = activities_res.data or []

    debrief_res = sb.table("subjective_log").select(
        "rpe,logged_at"
    ).gte("logged_at", week_start.isoformat()).lte(
        "logged_at", (week_end + timedelta(days=1)).isoformat()
    ).execute()
    rpes = [d["rpe"] for d in (debrief_res.data or []) if d.get("rpe") is not None]

    completed_sports = {a["started_at"][:10] + "_" + (a.get("sport") or "") for a in activities}
    planned_keys = {p["planned_date"] + "_" + (p.get("sport") or "") for p in planned}

    missed = planned_keys - completed_sports
    missed_sports = [k.split("_", 1)[1] for k in missed if "_" in k]

    planned_count = len(planned)
    completed_count = sum(1 for pk in planned_keys if pk in completed_sports)
    compliance = (completed_count / planned_count * 100) if planned_count > 0 else 100.0

    total_planned_min = sum((p.get("duration_s") or 0) for p in planned) // 60
    total_actual_min = sum((a.get("duration_s") or 0) for a in activities) // 60

    return WeeklyCompliance(
        week_start=week_start,
        planned_count=planned_count,
        completed_count=completed_count,
        missed_sports=missed_sports,
        avg_rpe=round(sum(rpes) / len(rpes), 1) if rpes else None,
        compliance_pct=round(compliance, 1),
        total_planned_duration_min=total_planned_min,
        total_actual_duration_min=total_actual_min,
    )


def generate_adjustments(compliance: WeeklyCompliance) -> list[Adjustment]:
    """Genera aggiustamenti basati sulla compliance settimanale."""
    adjustments: list[Adjustment] = []

    # Auto: RPE troppo alto
    if compliance.avg_rpe is not None and compliance.avg_rpe > 7.5:
        adjustments.append(Adjustment(
            kind="auto",
            action="add_recovery_day",
            reason=f"RPE medio {compliance.avg_rpe} > 7.5 — aggiungere recovery giorno extra",
            details={"avg_rpe": compliance.avg_rpe},
        ))

    # Auto: compliance < 70%
    if compliance.compliance_pct < 70 and compliance.planned_count >= 3:
        adjustments.append(Adjustment(
            kind="auto",
            action="reduce_volume_10pct",
            reason=f"Compliance {compliance.compliance_pct}% < 70% — ridurre volume 10%",
            details={"compliance_pct": compliance.compliance_pct},
        ))

    # Auto: nuoto saltato (probabilmente per spalla)
    swim_missed = compliance.missed_sports.count("swim")
    if swim_missed >= 1:
        adjustments.append(Adjustment(
            kind="auto",
            action="swap_swim_to_cross",
            reason=f"{swim_missed} nuoto saltato/i — proponi cross-training (bici o corsa Z2)",
            sport="swim",
            details={"missed_count": swim_missed},
        ))

    # Proposal: compliance molto bassa
    if compliance.compliance_pct < 50 and compliance.planned_count >= 3:
        adjustments.append(Adjustment(
            kind="proposal",
            action="reduced_plan",
            reason=f"Compliance {compliance.compliance_pct}% < 50% — piano ridotto per prossima settimana",
            details={"compliance_pct": compliance.compliance_pct},
        ))

    # Proposal: volume eseguito molto inferiore al pianificato
    if compliance.total_planned_duration_min > 0:
        vol_ratio = compliance.total_actual_duration_min / compliance.total_planned_duration_min
        if vol_ratio < 0.6 and compliance.total_planned_duration_min > 120:
            adjustments.append(Adjustment(
                kind="proposal",
                action="volume_mismatch",
                reason=(
                    f"Volume eseguito {compliance.total_actual_duration_min}min vs "
                    f"pianificato {compliance.total_planned_duration_min}min "
                    f"({vol_ratio:.0%}) — ricalibra volume prossima settimana"
                ),
            ))

    return adjustments


def run_adaptive_check() -> dict:
    """Esegue analisi compliance e genera report con aggiustamenti."""
    compliance = compute_weekly_compliance()
    adjustments = generate_adjustments(compliance)

    auto_adjustments = [a for a in adjustments if a.kind == "auto"]
    proposals = [a for a in adjustments if a.kind == "proposal"]

    report = {
        "week_start": compliance.week_start.isoformat(),
        "compliance_pct": compliance.compliance_pct,
        "planned": compliance.planned_count,
        "completed": compliance.completed_count,
        "missed_sports": compliance.missed_sports,
        "avg_rpe": compliance.avg_rpe,
        "volume_planned_min": compliance.total_planned_duration_min,
        "volume_actual_min": compliance.total_actual_duration_min,
        "auto_adjustments": [{"action": a.action, "reason": a.reason} for a in auto_adjustments],
        "proposals": [{"action": a.action, "reason": a.reason} for a in proposals],
    }

    if auto_adjustments or proposals:
        _notify_telegram(report)

    logger.info(
        "Adaptive check: compliance=%.0f%%, auto=%d, proposals=%d",
        compliance.compliance_pct, len(auto_adjustments), len(proposals),
    )
    return report


def _notify_telegram(report: dict) -> None:
    """Manda notifica Telegram con adjustments."""
    lines = [
        f"📊 <b>Analisi compliance settimana {report['week_start']}</b>",
        f"Completamento: {report['compliance_pct']:.0f}% ({report['completed']}/{report['planned']})",
        f"Volume: {report['volume_actual_min']}min / {report['volume_planned_min']}min pianificati",
    ]
    if report["avg_rpe"] is not None:
        lines.append(f"RPE medio: {report['avg_rpe']}")

    if report["auto_adjustments"]:
        lines.append("\n<b>Aggiustamenti automatici:</b>")
        for adj in report["auto_adjustments"]:
            lines.append(f"→ {adj['reason']}")

    if report["proposals"]:
        lines.append("\n<b>Proposte (richiede conferma):</b>")
        for p in report["proposals"]:
            lines.append(f"💬 {p['reason']}")
        lines.append("\n<i>Apri Claude Code per discutere le proposte.</i>")

    msg = "\n".join(lines)
    try:
        from coach.utils.telegram_logger import send_and_log_message
        send_and_log_message(msg, purpose="adaptive_planner")
    except Exception:
        logger.warning("Failed to send adaptive planner notification")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass

    report = run_adaptive_check()
    import json
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
