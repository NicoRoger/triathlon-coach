import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from coach.utils.supabase_client import get_supabase
from coach.utils.telegram_logger import send_and_log_message

logger = logging.getLogger(__name__)


def _already_sent_today(purpose: str) -> bool:
    """Controlla se e' gia' stato inviato un messaggio con questo purpose oggi (Rome)."""
    try:
        sb = get_supabase()
        rome_today = datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()
        # bot_messages ha created_at UTC; controlliamo se e' presente un record
        # con questo purpose e created_at >= mezzanotte Rome di oggi.
        res = sb.table("bot_messages").select("id").eq("purpose", purpose).gte(
            "created_at", f"{rome_today}T00:00:00+02:00"
        ).limit(1).execute()
        return bool(res.data)
    except Exception:
        logger.warning("Cannot check bot_messages (DB error) — assuming not sent")
        return False


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("notif_type")
    # Audit L5: gate DST. Il cron gira a UTC fisso (1h in anticipo in inverno).
    # Schedulando DUE cron (uno per estate, uno per inverno) e passando l'ora
    # Rome desiderata, solo il run che cade in quell'ora Rome invia davvero.
    parser.add_argument("--rome-hour", type=int, default=None,
                        help="Se impostato, invia solo se l'ora corrente Europe/Rome e' in [hora, hora+1]")
    args = parser.parse_args()
    notif_type = args.notif_type

    if args.rome_hour is not None:
        rome_now = datetime.now(ZoneInfo("Europe/Rome"))
        # Window +60min: se il job viene accodato fino a 59min dopo il cron,
        # passa ancora (es. cron 19:30 UTC, job parte 20:25 UTC = 22:25 CEST)
        # Il gate accetta [rome_hour, rome_hour+1) incluso.
        if rome_now.hour not in (args.rome_hour, args.rome_hour + 1):
            logger.info(
                "DST gate: ora Rome %02d:%02d non in [%02d, %02d], skip invio %s",
                rome_now.hour, rome_now.minute, args.rome_hour, args.rome_hour + 1, notif_type,
            )
            return
        # Idempotency: evita doppio invio se entrambi i cron passano il gate
        if _already_sent_today(f"{notif_type.replace('-', '_')}"):
            logger.info("Gate: %s gia' inviato oggi, skip", notif_type)
            return

    if notif_type == "debrief-reminder":
        msg = (
            "<b>📋 Debrief serale</b>\n\n"
            "Rispondi con:\n"
            "1. RPE sessione (1-10)\n"
            "2. Sensazioni\n"
            "3. Dolori? (no / dove)\n"
            "4. Energia + sonno previsto\n\n"
            "<i>Ignora se off oggi</i>"
        )
        result = send_and_log_message(msg, purpose="debrief_reminder", parent_workflow="debrief-reminder.yml")
        if result is None:
            logger.error("Debrief reminder send FAILED (Telegram returned None)")
            sys.exit(1)

    elif notif_type == "weekly-review":
        msg = (
            "<b>📋 Weekly review</b>\n\n"
            "Domenica sera: rivedi la settimana e pianifica la prossima.\n\n"
            "Apri Claude Code e digita: <code>fai la weekly review</code>\n\n"
            "<i>Tempo richiesto: 15-20 min</i>"
        )
        result = send_and_log_message(msg, purpose="weekly_review_reminder", parent_workflow="weekly-review.yml")
        if result is None:
            logger.error("Weekly review reminder send FAILED (Telegram returned None)")
            sys.exit(1)
    else:
        print(f"Unknown type: {notif_type}")
        sys.exit(1)

if __name__ == "__main__":
    main()
