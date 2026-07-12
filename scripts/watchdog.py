"""Watchdog: legge tabella health, invia alert Telegram se anomalie."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# Componenti CORE: attesi sempre, alert anche se la riga health manca del tutto
# (bug fix audit L4: una riga mai scritta era invisibile → falso verde).
THRESHOLDS_HOURS = {
    "garmin_sync": 8,
    # "strava_sync": 8,  # disabled: Garmin is single source of truth
    "briefing_morning": 26,
    "analytics_daily": 8,
    "dr_snapshot": 30,
    "energy_update": 30,
}

# WP2 — copertura totale by-design: OGNI riga presente in `health` viene
# monitorata, anche se non elencata qui. Questi override tarano la soglia
# sulla cadenza reale del job; un componente NUOVO (riga mai vista) usa
# DEFAULT_THRESHOLD_HOURS — impossibile dimenticare di monitorarlo.
# A differenza dei CORE, l'assenza della riga non genera alert (i job
# settimanali non devono spammare "mai eseguito" fino alla prima domenica).
CADENCE_THRESHOLDS_HOURS = {
    "debrief_reminder": 26,
    "proactive_reminders": 6,       # cron ogni 30min (jitter GitHub incluso)
    "proactive_questions": 80,      # 3x/settimana
    "post_session_analysis": 8,     # ogni ingest (3h)
    "modulation_apply": 8,          # ogni ingest (3h)
    "pattern_extraction": 200,      # domenicale (+ margine ritardi cron)
    "weekly_analysis": 200,
    "weekly_review_reminder": 200,
    "db_cleanup": 200,
    "debrief_evening": 200,         # riga storica, nessun writer attivo
}
DEFAULT_THRESHOLD_HOURS = 30


def compute_alerts(rows: list[dict], now: datetime) -> list[str]:
    """Calcola gli alert dato lo stato health. Funzione pura (testabile).

    Unione di: componenti CORE (alert anche se riga assente, audit L4) +
    TUTTE le righe presenti in health (soglia da override cadenza o default).
    """
    by_comp = {row["component"]: row for row in (rows or [])}
    components: dict[str, float] = {
        comp: float(
            THRESHOLDS_HOURS.get(comp)
            or CADENCE_THRESHOLDS_HOURS.get(comp)
            or DEFAULT_THRESHOLD_HOURS
        )
        for comp in set(THRESHOLDS_HOURS) | set(by_comp)
    }
    alerts: list[str] = []
    for comp, threshold in sorted(components.items()):
        row = by_comp.get(comp)
        if row is None:
            alerts.append(f"⚠️ <b>{comp}</b>: nessuna riga health (mai eseguito?)")
            continue
        last = row.get("last_success_at")
        if not last:
            # Non-core senza NESSUN successo: alert solo se ci sono fallimenti
            # registrati — una riga stub (es. debrief_evening storica, tutta
            # null) non deve spammare "mai sincronizzato" ogni ora.
            if comp in THRESHOLDS_HOURS or row.get("last_failure_at"):
                alerts.append(f"⚠️ <b>{comp}</b>: mai sincronizzato")
            continue
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        age = (now - last_dt).total_seconds() / 3600
        if age > threshold:
            err = row.get("last_error") or "-"
            alerts.append(
                f"🚨 <b>{comp}</b>: {age:.1f}h dall'ultimo successo (soglia {threshold}h)\n  err: {err[:120]}"
            )
    return alerts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()
    res = sb.table("health").select("*").execute()
    now = datetime.now(timezone.utc)

    alerts = compute_alerts(res.data or [], now)

    if alerts:
        msg = "<b>Watchdog alert</b>\n\n" + "\n\n".join(alerts)
        from coach.utils.telegram_logger import send_and_log_message
        send_and_log_message(
            message=msg,
            purpose="generic",
            parent_workflow="watchdog.yml"
        )
        logger.warning("Watchdog: %d alert", len(alerts))
    else:
        logger.info("All healthy")

    # Always-on heartbeat to healthchecks.io
    hc = os.environ.get("HEALTHCHECKS_PING_URL_WATCHDOG")
    if hc:
        try:
            requests.get(hc, timeout=10)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
