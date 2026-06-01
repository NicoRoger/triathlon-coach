"""Update health table for watchdog monitoring."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def record_health(
    component: str,
    success: bool,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    # Bug fix audit I4: record_health è best-effort. Una scrittura health che
    # solleva (Supabase down) NON deve abbattere il caller — proprio quando
    # vogliamo registrare lo stato. Inoltre usiamo UPSERT così una riga
    # componente assente viene creata invece di un update no-op silenzioso.
    now = datetime.now(timezone.utc).isoformat()
    try:
        sb = get_supabase()
        if success:
            sb.table("health").upsert(
                {
                    "component": component,
                    "last_success_at": now,
                    "failure_count": 0,
                    "last_error": None,
                    "metadata": metadata,
                },
                on_conflict="component",
            ).execute()
        else:
            current = sb.table("health").select("failure_count").eq("component", component).execute()
            prev = (current.data[0]["failure_count"] if current.data else 0) or 0
            sb.table("health").upsert(
                {
                    "component": component,
                    "last_failure_at": now,
                    "failure_count": prev + 1,
                    "last_error": error,
                    "metadata": metadata,
                },
                on_conflict="component",
            ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("record_health: scrittura health fallita per %s", component, exc_info=True)

    # Healthchecks.io ping (dead man's switch). Normalizza il nome componente in
    # un token valido per env var (es. 'morning-brief' → MORNING_BRIEF).
    env_key = "HEALTHCHECKS_PING_URL_" + re.sub(r"[^A-Za-z0-9]", "_", component).upper()
    ping_url = os.environ.get(env_key)
    if ping_url:
        try:
            suffix = "" if success else "/fail"
            requests.get(f"{ping_url}{suffix}", timeout=10)
        except Exception:  # noqa: BLE001
            pass  # Best effort
