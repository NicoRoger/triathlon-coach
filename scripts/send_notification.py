import sys
import logging
from coach.utils.telegram_logger import send_and_log_message

def main():
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_notification.py <type>")
        sys.exit(1)
        
    notif_type = sys.argv[1]
    
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
            "Apri Claude da smartphone/web con il connector coach e digita:\n"
            "<code>fai la weekly review</code>\n\n"
            "Il coach analizzerà i dati della settimana, ti farà la diagnosi, e proporrà la struttura della settimana che inizia domani. Approvi o modifichi prima del commit nel piano.\n\n"
            "<i>Tempo richiesto: 15-20 min. Claude Code resta opzionale dal Mac.</i>"
        )
        send_and_log_message(msg, purpose="weekly_review_reminder", parent_workflow="weekly-review.yml")
    else:
        print(f"Unknown type: {notif_type}")
        sys.exit(1)

if __name__ == "__main__":
    main()
