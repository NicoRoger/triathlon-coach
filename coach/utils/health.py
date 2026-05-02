"""Update health table for watchdog monitoring."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import requests

from coach.utils.supabase_client import get_supabase


def record_health(
    component: str,
    success: bool,
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    if success:
        sb.table("health").update(
            {
                "last_success_at": now,
                "failure_count": 0,
                "last_error": None,
                "metadata": metadata,
            }
        ).eq("component", component).execute()
    else:
        # Increment failure_count
        current = sb.table("health").select("failure_count").eq("component", component).execute()
        prev = (current.data[0]["failure_count"] if current.data else 0) or 0
        sb.table("health").update(
            {
                "last_failure_at": now,
                "failure_count": prev + 1,
                "last_error": error,
                "metadata": metadata,
            }
        ).eq("component", component).execute()

    # Healthchecks.io ping (dead man's switch)
    ping_url = os.environ.get(f"HEALTHCHECKS_PING_URL_{component.upper()}")
    if ping_url:
        try:
            suffix = "" if success else "/fail"
            requests.get(f"{ping_url}{suffix}", timeout=10)
        except Exception:  # noqa: BLE001
            pass  # Best effort
