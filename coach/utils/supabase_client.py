"""Supabase client singleton."""
from __future__ import annotations

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

# Auto-load .env per dev locale (CI usa secret invece)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        # Fallback esplicito, non silenzioso: con RLS attivo e nessuna policy,
        # la anon key fa tornare [] a TUTTE le SELECT senza alcun errore.
        logger.warning(
            "SUPABASE_SERVICE_KEY assente: fallback su SUPABASE_ANON_KEY — "
            "con RLS senza policy tutte le query torneranno vuote senza errore."
        )
        key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)