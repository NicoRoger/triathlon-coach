"""Ingest Strava → Supabase. Backup di Garmin.

OAuth refresh-token flow. Storage: refresh token in env var, access token rinfrescato
ad ogni run (vita 6h). Vedi docs/SETUP.md §4 per setup iniziale.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from coach.models import Activity, Source, Sport
from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health

logger = logging.getLogger(__name__)

STRAVA_API = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"

SPORT_MAP = {
    "Run": Sport.RUN,
    "TrailRun": Sport.RUN,
    "VirtualRun": Sport.RUN,
    "Ride": Sport.BIKE,
    "VirtualRide": Sport.BIKE,
    "GravelRide": Sport.BIKE,
    "MountainBikeRide": Sport.BIKE,
    "Swim": Sport.SWIM,
    "WeightTraining": Sport.STRENGTH,
}


def _refresh_access_token() -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _list_activities(access_token: str, after: datetime, page: int = 1, per_page: int = 100) -> list[dict]:
    resp = requests.get(
        f"{STRAVA_API}/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"after": int(after.timestamp()), "page": page, "per_page": per_page},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _normalize(raw: dict) -> Optional[Activity]:
    sport = SPORT_MAP.get(raw.get("sport_type") or raw.get("type"), None)
    if sport is None:
        return None

    started = datetime.fromisoformat(raw["start_date"].replace("Z", "+00:00"))

    avg_pace_km = None
    avg_pace_100m = None
    if raw.get("average_speed"):
        speed = float(raw["average_speed"])
        if speed > 0:
            if sport == Sport.RUN:
                avg_pace_km = 1000.0 / speed
            elif sport == Sport.SWIM:
                avg_pace_100m = 100.0 / speed

    return Activity(
        external_id=f"strava_{raw['id']}",
        source=Source.STRAVA,
        sport=sport,
        started_at=started,
        duration_s=int(raw.get("moving_time") or raw.get("elapsed_time") or 0),
        distance_m=raw.get("distance"),
        elevation_gain_m=raw.get("total_elevation_gain"),
        avg_hr=int(raw["average_heartrate"]) if raw.get("average_heartrate") else None,
        max_hr=int(raw["max_heartrate"]) if raw.get("max_heartrate") else None,
        avg_power_w=raw.get("average_watts"),
        np_w=raw.get("weighted_average_watts"),
        avg_pace_s_per_km=avg_pace_km,
        avg_pace_s_per_100m=avg_pace_100m,
        raw_payload=raw,
    )


def sync(days_back: int = 7) -> int:
    token = _refresh_access_token()
    after = datetime.now(timezone.utc) - timedelta(days=days_back)
    sb = get_supabase()

    count = 0
    page = 1
    while True:
        batch = _list_activities(token, after, page=page)
        if not batch:
            break
        for raw in batch:
            act = _normalize(raw)
            if act is None:
                continue
            try:
                sb.table("activities").upsert(
                    act.model_dump(mode="json", exclude_none=True),
                    on_conflict="external_id,source",
                ).execute()
                count += 1
            except Exception:  # noqa: BLE001
                logger.exception("Strava upsert failed for %s", raw.get("id"))
        page += 1

    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        n = sync(days_back=int(os.environ.get("INGEST_DAYS_BACK", "7")))
        logger.info("Strava synced %d activities", n)
        record_health("strava_sync", success=True, metadata={"activities": n})
    except Exception as e:  # noqa: BLE001
        logger.exception("Strava sync failed")
        record_health("strava_sync", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
