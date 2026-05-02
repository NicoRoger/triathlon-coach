"""Keepalive: tocca Supabase ogni giorno per evitare la pausa free-tier (7 giorni).

Idempotente, costo trascurabile, safety net.
"""
from __future__ import annotations

import logging

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()
    res = sb.table("health").select("component").limit(1).execute()
    logger.info("Keepalive ok, %d row read", len(res.data or []))


if __name__ == "__main__":
    main()
