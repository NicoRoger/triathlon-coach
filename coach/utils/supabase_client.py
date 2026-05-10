"""Supabase client singleton."""
from __future__ import annotations

import os
from functools import lru_cache

# Auto-load .env per dev locale (CI usa secret invece)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)