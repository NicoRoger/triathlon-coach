import logging
import sys
from datetime import datetime, timedelta, timezone
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(level=logging.INFO)
    sb = get_supabase()
    now = datetime.now(timezone.utc)

    try:
        # Cleanup bot_messages older than 90 days
        bot_msgs_threshold = (now - timedelta(days=90)).isoformat()
        res1 = sb.table("bot_messages").delete().lt("sent_at", bot_msgs_threshold).execute()
        logger.info("Cleaned up old bot_messages. Count: %s", len(res1.data) if res1.data else 0)

        # Cleanup expired pending_confirmations older than 30 days
        pending_threshold = (now - timedelta(days=30)).isoformat()
        res2 = sb.table("pending_confirmations").delete().in_("status", ["expired", "rejected", "confirmed", "corrected"]).lt("created_at", pending_threshold).execute()
        logger.info("Cleaned up old pending_confirmations. Count: %s", len(res2.data) if res2.data else 0)

    except Exception as e:
        # Bug fix audit L2: ri-solleva (exit != 0) così il workflow risulta ROSSO.
        # Prima il bare except inghiottiva tutto e usciva 0 → cleanup poteva essere
        # rotto per mesi (bot_messages in crescita illimitata) senza alcun alert.
        from coach.utils.health import record_health
        record_health("db_cleanup", success=False, error=str(e))
        logger.exception("Failed during DB cleanup")
        sys.exit(1)
    else:
        from coach.utils.health import record_health
        record_health("db_cleanup", success=True)

if __name__ == "__main__":
    main()
