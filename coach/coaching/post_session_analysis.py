"""Feature 1 — Analisi automatica post-sessione.

Quando una nuova attività entra nel DB (post sync Garmin), analizza
automaticamente con Claude. Salva in session_analyses, manda Telegram.

Uso:
    python -m coach.coaching.post_session_analysis --recent
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from coach.utils.budget import BudgetExceededError
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SKILL_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "session_analysis.md"


def _load_skill() -> str:
    """Carica il system prompt dalla skill file."""
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return "Sei un coach di triathlon esperto. Analizza la sessione di allenamento."


def _get_planned_session(sb, activity_date: str, sport: str) -> Optional[dict]:
    """Trova sessione pianificata per data e sport."""
    res = sb.table("planned_sessions").select("*").eq(
        "planned_date", activity_date
    ).eq("sport", sport).limit(1).execute()
    return res.data[0] if res.data else None


def _get_historical(sb, sport: str, current_id: str, limit: int = 4) -> list[dict]:
    """Ultime N attività dello stesso sport, esclusa quella corrente."""
    res = sb.table("activities").select(
        "started_at,duration_s,distance_m,avg_hr,max_hr,avg_pace_s_per_km,avg_power_w,tss,splits"
    ).eq("sport", sport).neq("external_id", current_id).order(
        "started_at", desc=True
    ).limit(limit).execute()
    return res.data or []


def _get_recent_debrief(sb, days: int = 3) -> list[dict]:
    """Ultimi debrief soggettivi."""
    since = (date.today() - timedelta(days=days)).isoformat()
    res = sb.table("subjective_log").select("*").gte(
        "logged_at", since
    ).order("logged_at", desc=True).limit(5).execute()
    return res.data or []


def _get_daily_metrics(sb, day: str) -> Optional[dict]:
    """Daily metrics per il giorno."""
    res = sb.table("daily_metrics").select("*").eq("date", day).limit(1).execute()
    return res.data[0] if res.data else None


def _get_upcoming_sessions(sb, from_date: str, days: int = 3) -> list[dict]:
    """Prossime sessioni pianificate (per proposta modulazione)."""
    from datetime import date, timedelta
    until = (date.fromisoformat(from_date) + timedelta(days=days)).isoformat()
    res = sb.table("planned_sessions").select(
        "planned_date,sport,session_type,duration_s,description"
    ).gt("planned_date", from_date).lte("planned_date", until).order(
        "planned_date"
    ).execute()
    return res.data or []


def _compute_zone_compliance(planned: dict, activity: dict) -> Optional[dict]:
    """Confronta target_zones del piano con hr_zones_s effettivi.

    target_zones: {"z2": 0.8, "z4": 0.2}  — proporzioni (somma <= 1)
    hr_zones_s:   {"z1": 300, "z2": 3600, "z4": 120}  — secondi per zona
    """
    target = planned.get("target_zones")
    actual_raw = activity.get("hr_zones_s")
    if not target or not actual_raw:
        return None

    total_s = sum(actual_raw.values())
    if total_s == 0:
        return None

    actual = {z: round(s / total_s, 3) for z, s in actual_raw.items()}

    deviations = {}
    for zone, tgt in target.items():
        act = actual.get(zone, 0.0)
        deviations[zone] = round(act - tgt, 3)

    # Compliance score: fraction of prescribed intensity actually hit
    overlap = sum(min(actual.get(z, 0), tgt) for z, tgt in target.items())
    target_sum = sum(target.values())
    score = round(overlap / target_sum * 100) if target_sum > 0 else None

    return {
        "score": score,
        "target": target,
        "actual": actual,
        "deviations": deviations,
        "total_duration_s": total_s,
    }


def analyze_session(activity_id: str) -> Optional[dict]:
    """Analizza una singola attività con AI.

    Returns:
        dict con analysis_text e suggested_actions, o None se skippata.
    """
    sb = get_supabase()

    # Check se già analizzata
    existing = sb.table("session_analyses").select("id").eq(
        "activity_id", activity_id
    ).limit(1).execute()
    if existing.data:
        logger.info("Activity %s already analyzed, skipping", activity_id)
        return None

    # Recupera attività
    act_res = sb.table("activities").select("*").eq("external_id", activity_id).limit(1).execute()
    if not act_res.data:
        logger.warning("Activity %s not found", activity_id)
        return None

    activity = act_res.data[0]
    activity_date = activity["started_at"][:10]
    sport = activity.get("sport", "other")

    # Raccolta contesto
    planned = _get_planned_session(sb, activity_date, sport)
    historical = _get_historical(sb, sport, activity_id)
    debrief = _get_recent_debrief(sb)
    metrics = _get_daily_metrics(sb, activity_date)
    zone_compliance = _compute_zone_compliance(planned, activity) if planned else None

    # Costruisci prompt
    context_parts = [
        f"## Attività analizzata\n{json.dumps(_clean_for_prompt(activity), indent=2, default=str)}",
    ]
    if planned:
        context_parts.append(f"## Sessione pianificata\n{json.dumps(_clean_for_prompt(planned), indent=2, default=str)}")
    if zone_compliance:
        context_parts.append(
            f"## Compliance zone (confronto piano vs eseguito)\n"
            f"Score: {zone_compliance['score']}% — "
            f"target {zone_compliance['target']} / effettivo {zone_compliance['actual']}\n"
            f"Deviazioni per zona: {zone_compliance['deviations']}"
        )
    if historical:
        context_parts.append(f"## Storico ultime {len(historical)} sessioni {sport}\n{json.dumps([_clean_for_prompt(h) for h in historical], indent=2, default=str)}")
    if metrics:
        context_parts.append(f"## Metriche giornaliere\n{json.dumps(_clean_for_prompt(metrics), indent=2, default=str)}")
    if debrief:
        context_parts.append(f"## Debrief soggettivi recenti\n{json.dumps([_clean_for_prompt(d) for d in debrief], indent=2, default=str)}")

    user_message = "\n\n".join(context_parts)

    # Chiamata AI
    try:
        from coach.utils.llm_client import get_client
        client = get_client()
        result = client.call(
            purpose="session_analysis",
            system=_load_skill(),
            messages=[{"role": "user", "content": user_message}],
            prefer_model="sonnet",
            max_tokens=800,
            temperature=0.3,
        )
    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping session analysis for %s", activity_id)
        return None
    except Exception:
        logger.exception("LLM call failed for session analysis %s", activity_id)
        return None

    analysis_text = result["text"]

    # Salva su DB
    actions = _extract_actions(analysis_text)
    if zone_compliance:
        actions.append({"zone_compliance": zone_compliance})
    record = {
        "activity_id": activity_id,
        "analysis_text": analysis_text,
        "suggested_actions": actions,
        "model_used": result["model"],
        "cost_usd": result["cost_usd"],
    }
    sb.table("session_analyses").insert(record).execute()

    # Manda Telegram
    _send_analysis_telegram(activity, analysis_text)

    # Valuta se serve modulazione mid-week
    try:
        from coach.coaching.modulation import (
            should_trigger_modulation,
            propose_modulation,
            generate_modulation_proposal,
        )
        if should_trigger_modulation(analysis_text, metrics):
            upcoming = _get_upcoming_sessions(sb, activity_date)
            changes = generate_modulation_proposal(analysis_text, metrics or {}, upcoming)
            if changes:
                flags = (metrics or {}).get("flags") or []
                propose_modulation(
                    trigger_event="post_session_critical",
                    trigger_data={
                        "analysis_excerpt": analysis_text[:300],
                        "flags": flags,
                        "hrv_z": (metrics or {}).get("hrv_z_score"),
                    },
                    proposed_changes=changes,
                )
    except Exception:
        logger.warning("Modulation check failed for %s", activity_id, exc_info=True)

    logger.info("Session analysis saved for %s (cost: $%.4f)", activity_id, result["cost_usd"])
    return record


def analyze_recent(days: int = 2) -> int:
    """Analizza attività recenti non ancora analizzate.

    Args:
        days: quanti giorni indietro guardare (default 2, usare >2 per backfill)

    Returns:
        Numero di attività analizzate.
    """
    sb = get_supabase()
    since = (date.today() - timedelta(days=days)).isoformat()

    # Attività recenti
    activities = sb.table("activities").select("external_id").gte(
        "started_at", since
    ).execute()

    if not activities.data:
        logger.info("No recent activities to analyze")
        return 0

    count = 0
    for act in activities.data:
        ext_id = act.get("external_id")
        if ext_id:
            result = analyze_session(ext_id)
            if result:
                count += 1

    return count


def _clean_for_prompt(d: dict) -> dict:
    """Rimuove campi pesanti dal dict per prompt (raw_payload, id, created_at)."""
    skip = {"raw_payload", "id", "created_at", "updated_at"}
    return {k: v for k, v in d.items() if k not in skip and v is not None}


def _extract_actions(text: str) -> list[dict]:
    """Estrae azioni suggerite dal testo (heuristic: righe con → o •)."""
    actions = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("→", "•", "- ")) and len(line) > 10:
            actions.append({"action": line.lstrip("→•- ").strip()})
    return actions


def _send_analysis_telegram(activity: dict, analysis: str) -> None:
    """Manda analisi sessione via Telegram."""
    sport_emoji = {"swim": "🏊", "bike": "🚴", "run": "🏃", "strength": "💪"}.get(
        activity.get("sport", ""), "🏋️"
    )
    duration_min = int(activity.get("duration_s") or 0) // 60

    msg = (
        f"{sport_emoji} <b>Analisi sessione</b> — {activity.get('sport', '?')} {duration_min}min\n\n"
        f"{analysis}"
    )
    try:
        from coach.utils.telegram_logger import send_and_log_message
        send_and_log_message(
            msg,
            purpose="session_analysis",
            context_data={"activity_id": activity.get("id"), "sport": activity.get("sport")},
        )
    except Exception:
        logger.warning("Failed to send session analysis to Telegram")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--recent", action="store_true", help="Analizza attività recenti non analizzate")
    parser.add_argument("--days", type=int, default=2, help="Giorni indietro per --recent (default 2, usa 90+ per backfill)")
    parser.add_argument("--activity-id", type=str, help="Analizza una attività specifica")
    args = parser.parse_args()

    if args.activity_id:
        result = analyze_session(args.activity_id)
        if result:
            print(result["analysis_text"])
    elif args.recent:
        n = analyze_recent(days=args.days)
        print(f"Analizzate {n} sessioni")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
