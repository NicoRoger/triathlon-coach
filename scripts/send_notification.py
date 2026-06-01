import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from coach.utils.telegram_logger import send_and_log_message

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("notif_type")
    # Audit L5: gate DST. Il cron gira a UTC fisso (1h in anticipo in inverno).
    # Schedulando DUE cron (uno per estate, uno per inverno) e passando l'ora
    # Rome desiderata, solo il run che cade in quell'ora Rome invia davvero.
    parser.add_argument("--rome-hour", type=int, default=None,
                        help="Se impostato, invia solo se l'ora corrente Europe/Rome == questo valore")
    args = parser.parse_args()
    notif_type = args.notif_type

    if args.rome_hour is not None:
        rome_now = datetime.now(ZoneInfo("Europe/Rome"))
        if rome_now.hour != args.rome_hour:
            logger.info(
                "DST gate: ora Rome %02d:%02d != %02d, skip invio %s",
                rome_now.hour, rome_now.minute, args.rome_hour, notif_type,
            )
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
        send_and_log_message(msg, purpose="debrief_reminder", parent_workflow="debrief-reminder.yml")
        
    elif notif_type == "weekly-review":
        msg = (
            "<b>📋 È ora della weekly review</b>\n\n"
            "Domenica sera, momento di rivedere la settimana e pianificare la prossima.\n\n"
            "Apri Claude Code dal Mac e digita:\n"
            "<code>fai la weekly review</code>\n\n"
            "Il coach analizzerà i dati della settimana, ti farà la diagnosi, e proporrà la struttura della settimana che inizia domani. Approvi o modifichi prima del commit nel piano.\n\n"
            "<i>Tempo richiesto: 15-20 min</i>"
        )
        send_and_log_message(msg, purpose="weekly_review_reminder", parent_workflow="weekly-review.yml")
    else:
        print(f"Unknown type: {notif_type}")
        sys.exit(1)

if __name__ == "__main__":
    main()
