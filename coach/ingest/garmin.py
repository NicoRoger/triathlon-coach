"""Ingest Garmin Connect → Supabase.

Usa python-garminconnect (non ufficiale ma stabile). Token cache in env var
`GARMIN_SESSION_JSON` (base64 di ~/.garminconnect/oauth1_token.json + oauth2_token.json).

Idempotente: upsert su (external_id, source).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from coach.models import Activity, DailyWellness, Source, Sport
from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health

logger = logging.getLogger(__name__)


SPORT_MAP = {
    "running": Sport.RUN,
    "treadmill_running": Sport.RUN,
    "indoor_running": Sport.RUN,
    "trail_running": Sport.RUN,
    "cycling": Sport.BIKE,
    "road_biking": Sport.BIKE,
    "indoor_cycling": Sport.BIKE,
    "mountain_biking": Sport.BIKE,
    "gravel_cycling": Sport.BIKE,
    "lap_swimming": Sport.SWIM,
    "open_water_swimming": Sport.SWIM,
    "swimming": Sport.SWIM,
    "strength_training": Sport.STRENGTH,
    "multi_sport": Sport.BRICK,
}


def _restore_garmin_session() -> Path:
    """Restore session from base64 env var to temp dir."""
    raw = os.environ.get("GARMIN_SESSION_JSON")
    if not raw:
        raise RuntimeError("GARMIN_SESSION_JSON not set")
    decoded = json.loads(base64.b64decode(raw))
    tokendir = Path(tempfile.mkdtemp(prefix="garmin_"))
    for name, content in decoded.items():
        (tokendir / name).write_text(content)
    # Library espera GARMINTOKENS env var
    os.environ["GARMINTOKENS"] = str(tokendir)
    return tokendir


def _login():
    from garminconnect import Garmin  # type: ignore
    _restore_garmin_session()
    g = Garmin()
    g.login()  # legge da GARMINTOKENS env var
    return g


def _normalize_activity(raw: dict) -> Activity:
    """Garmin activity → Pydantic Activity."""
    raw_sport = (raw.get("activityType", {}).get("typeKey") or "").lower()
    sport = SPORT_MAP.get(raw_sport, Sport.OTHER)

    started = datetime.fromisoformat(raw["startTimeGMT"].replace("Z", "+00:00"))

    # HR zones
    hr_zones = None
    if raw.get("hrTimeInZone_1") is not None:
        hr_zones = {
            f"z{i}": int(raw.get(f"hrTimeInZone_{i}", 0) or 0)
            for i in range(1, 6)
        }

    # TSS: se Garmin lo fornisce, usalo; altrimenti lascia None (calcolato dopo
    # nel layer analytics se mancano dati)
    tss = raw.get("trainingStressScore")

    # Pace per nuoto/corsa
    avg_pace_per_km = None
    avg_pace_per_100m = None
    if sport == Sport.RUN and raw.get("averageSpeed"):
        # averageSpeed in m/s
        speed = float(raw["averageSpeed"])
        if speed > 0:
            avg_pace_per_km = 1000.0 / speed
    elif sport == Sport.SWIM and raw.get("averageSpeed"):
        speed = float(raw["averageSpeed"])
        if speed > 0:
            avg_pace_per_100m = 100.0 / speed

    return Activity(
        external_id=f"garmin_{raw['activityId']}",
        source=Source.GARMIN,
        sport=sport,
        started_at=started,
        duration_s=int(raw.get("duration", 0) or 0),
        distance_m=raw.get("distance"),
        elevation_gain_m=raw.get("elevationGain"),
        avg_hr=int(raw["averageHR"]) if raw.get("averageHR") else None,
        max_hr=int(raw["maxHR"]) if raw.get("maxHR") else None,
        hr_zones_s=hr_zones,
        avg_power_w=raw.get("avgPower"),
        np_w=raw.get("normPower"),
        avg_pace_s_per_km=avg_pace_per_km,
        avg_pace_s_per_100m=avg_pace_per_100m,
        tss=tss,
        if_value=raw.get("intensityFactor"),
        raw_payload=raw,
    )


def _normalize_wellness(raw: dict, day: date) -> DailyWellness:
    """Garmin user_summary + sleep + hrv → DailyWellness."""
    sleep = raw.get("sleep", {}) or {}
    hrv = raw.get("hrv", {}) or {}

    return DailyWellness(
        date=day,
        hrv_rmssd=hrv.get("lastNightAvg"),
        hrv_status=hrv.get("status"),
        sleep_score=(sleep.get("sleepScores", {}) or {}).get("overall", {}).get("value"),
        sleep_total_s=sleep.get("sleepTimeSeconds"),
        sleep_deep_s=sleep.get("deepSleepSeconds"),
        sleep_rem_s=sleep.get("remSleepSeconds"),
        sleep_efficiency=sleep.get("sleepEfficiency"),
        body_battery_min=raw.get("bodyBatteryLowestValue"),
        body_battery_max=raw.get("bodyBatteryHighestValue"),
        stress_avg=raw.get("averageStressLevel"),
        resting_hr=raw.get("restingHeartRate"),
        training_status=raw.get("trainingStatus", {}).get("trainingStatus") if isinstance(raw.get("trainingStatus"), dict) else None,
        training_load_acute=raw.get("acuteTrainingLoad"),
        training_load_chronic=raw.get("chronicTrainingLoad"),
        vo2max_run=raw.get("vo2MaxRunning"),
        vo2max_bike=raw.get("vo2MaxCycling"),
        raw_payload=raw,
    )


def sync_activities(days_back: int = 7) -> int:
    """Sync attività ultimi N giorni. Idempotente.

    Returns:
        Numero attività sincronizzate (insert + update).
    """
    g = _login()
    end = date.today()
    start = end - timedelta(days=days_back)

    activities_raw = g.get_activities_by_date(
        start.isoformat(), end.isoformat()
    )

    sb = get_supabase()
    count = 0
    for raw in activities_raw:
        try:
            act = _normalize_activity(raw)
            sb.table("activities").upsert(
                act.model_dump(mode="json", exclude_none=True),
                on_conflict="external_id,source",
            ).execute()
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to ingest activity %s: %s", raw.get("activityId"), e)

    return count


def sync_wellness(days_back: int = 7) -> int:
    g = _login()
    sb = get_supabase()
    count = 0
    for offset in range(days_back, -1, -1):
        day = date.today() - timedelta(days=offset)
        try:
            user_summary = g.get_user_summary(day.isoformat())
            sleep = g.get_sleep_data(day.isoformat())
            hrv = None
            try:
                hrv = g.get_hrv_data(day.isoformat())
            except Exception:
                pass
            payload = {**(user_summary or {}), "sleep": sleep, "hrv": hrv}
            wellness = _normalize_wellness(payload, day)
            sb.table("daily_wellness").upsert(
                wellness.model_dump(mode="json", exclude_none=True),
                on_conflict="date",
            ).execute()
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to ingest wellness for %s: %s", day, e)

    return count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        n_act = sync_activities(days_back=int(os.environ.get("INGEST_DAYS_BACK", "7")))
        n_well = sync_wellness(days_back=int(os.environ.get("INGEST_DAYS_BACK", "7")))
        logger.info("Synced %d activities, %d wellness days", n_act, n_well)
        record_health("garmin_sync", success=True, metadata={"activities": n_act, "wellness": n_well})
    except Exception as e:  # noqa: BLE001
        logger.exception("Garmin sync failed")
        record_health("garmin_sync", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
