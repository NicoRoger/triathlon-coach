"""Watchdog: legge tabella health, invia alert Telegram se anomalie."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


THRESHOLDS_HOURS = {
    "garmin_sync": 8,         # ingest 3h → 8h è 2-3 fallimenti consecutivi
    #"strava_sync": 8,
    "briefing_morning": 26,    # daily 06:30, 26h dà margine
    "analytics_daily": 8,
    "dr_snapshot": 30,         # daily, 30h margine
}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()
    res = sb.table("health").select("*").execute()
    now = datetime.now(timezone.utc)

    alerts = []
    for row in res.data or []:
        comp = row["component"]
        threshold = THRESHOLDS_HOURS.get(comp)
        if threshold is None:
            continue
        last = row.get("last_success_at")
        if not last:
            alerts.append(f"⚠️ <b>{comp}</b>: mai sincronizzato")
            continue
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age = (now - last_dt).total_seconds() / 3600
        if age > threshold:
            err = row.get("last_error") or "-"
            alerts.append(
                f"🚨 <b>{comp}</b>: {age:.1f}h dall'ultimo successo (soglia {threshold}h)\n  err: {err[:120]}"
            )

    if alerts:
        msg = "<b>Watchdog alert</b>\n\n" + "\n\n".join(alerts)
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=20,
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
