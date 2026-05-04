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

def _extract_vo2max(max_metrics_payload: Optional[dict], discipline: str) -> Optional[float]:
    """Estrae VO2max dal payload max_metrics. Garmin restituisce struttura diversa per running/cycling."""
    if not max_metrics_payload:
        return None
    # max_metrics può essere lista o dict, robusto a entrambi
    items = max_metrics_payload if isinstance(max_metrics_payload, list) else [max_metrics_payload]
    for item in items:
        if not isinstance(item, dict):
            continue
        # generic struttura: {"generic": {"vo2MaxValue": X}, "cycling": {"vo2MaxValue": Y}}
        if discipline == "running":
            generic = item.get("generic") or {}
            v = generic.get("vo2MaxValue") or generic.get("vo2MaxPreciseValue")
            if v:
                return float(v)
        elif discipline == "cycling":
            cycling = item.get("cycling") or {}
            v = cycling.get("vo2MaxValue") or cycling.get("vo2MaxPreciseValue")
            if v:
                return float(v)
    return None


def _extract_training_status(payload: Optional[dict]) -> Optional[str]:
    """Estrae il training status testuale (productive, maintaining, overreaching, ecc.)."""
    if not payload or not isinstance(payload, dict):
        return None
    # Garmin annida in mostRecentTrainingStatus
    mrts = payload.get("mostRecentTrainingStatus") or {}
    summary = mrts.get("latestTrainingStatusData") or {}
    # summary è dict con un device id come chiave
    if isinstance(summary, dict) and summary:
        first_device = next(iter(summary.values()), None)
        if isinstance(first_device, dict):
            ts = first_device.get("trainingStatus")
            if ts is not None:
                # Spesso è int, mappa standard Garmin: 1=peaking, 2=productive, 3=maintaining,
                # 4=recovery, 5=unproductive, 6=detraining, 7=overreaching, 0=no_status
                map_status = {
                    0: "no_status",
                    1: "peaking",
                    2: "productive",
                    3: "maintaining",
                    4: "recovery",
                    5: "unproductive",
                    6: "detraining",
                    7: "overreaching",
                    8: "strained",       # carico molto alto, vicino limite
                    9: "no_recent_load", # poco carico recente
                }
                if isinstance(ts, int):
                    return map_status.get(ts, str(ts))
                return str(ts).lower()
    return None


def _extract_training_load(payload: Optional[dict], kind: str) -> Optional[float]:
    """Estrae acute/chronic training load da mostRecentTrainingStatus.

    Path corretto: mostRecentTrainingStatus.latestTrainingStatusData.<deviceId>.acuteTrainingLoadDTO
    Contiene dailyTrainingLoadAcute e dailyTrainingLoadChronic.
    """
    if not payload or not isinstance(payload, dict):
        return None
    mrts = payload.get("mostRecentTrainingStatus") or {}
    summary = mrts.get("latestTrainingStatusData") or {}
    if not isinstance(summary, dict) or not summary:
        return None
    first_device = next(iter(summary.values()), None)
    if not isinstance(first_device, dict):
        return None
    atl_dto = first_device.get("acuteTrainingLoadDTO") or {}
    if kind == "acute":
        return atl_dto.get("dailyTrainingLoadAcute")
    elif kind == "chronic":
        return atl_dto.get("dailyTrainingLoadChronic")
    return None

def _normalize_wellness(raw: dict, day: date) -> DailyWellness:
    """Garmin user_summary + sleep + hrv → DailyWellness.
    
    Path verificati su payload reali (maggio 2026):
    - HRV: sleep.avgOvernightHrv (numerico) + hrv.hrvSummary.status (label)
    - Sleep: sleep.dailySleepDTO.sleepScores.overall.value (score 0-100)
    - Sleep durations: sleep.dailySleepDTO.{sleepTime,deepSleep,remSleep}Seconds
    - Body battery, stress, resting HR: top-level del user_summary
    - VO2max e training_status: NULL per ora, fix in iterazione successiva
      con endpoint Garmin dedicati (get_vo2max_data, get_training_status).
    """
    sleep = raw.get("sleep") or {}
    hrv = raw.get("hrv") or {}
    sleep_dto = sleep.get("dailySleepDTO") or {}
    sleep_scores = sleep_dto.get("sleepScores") or {}
    overall_score = (sleep_scores.get("overall") or {}).get("value")

    # Sleep efficiency: tempo dormendo / tempo a letto
    sleep_total = sleep_dto.get("sleepTimeSeconds")
    awake = sleep_dto.get("awakeSleepSeconds")
    sleep_eff = None
    if sleep_total and awake is not None:
        time_in_bed = sleep_total + awake
        sleep_eff = round(sleep_total / time_in_bed, 4) if time_in_bed > 0 else None

    return DailyWellness(
        date=day,
        # HRV
        hrv_rmssd=sleep.get("avgOvernightHrv") or (hrv.get("hrvSummary") or {}).get("lastNightAvg"),
        hrv_status=(hrv.get("hrvSummary") or {}).get("status") or sleep.get("hrvStatus"),
        # Sleep — nuovo fix
        sleep_score=overall_score,
        sleep_total_s=sleep_total,
        sleep_deep_s=sleep_dto.get("deepSleepSeconds"),
        sleep_rem_s=sleep_dto.get("remSleepSeconds"),
        sleep_efficiency=sleep_eff,
        # Top-level user_summary
        body_battery_min=raw.get("bodyBatteryLowestValue"),
        body_battery_max=raw.get("bodyBatteryHighestValue"),
        stress_avg=raw.get("averageStressLevel"),
        resting_hr=raw.get("restingHeartRate"),
        # VO2max — da endpoint dedicato max_metrics
        vo2max_run=_extract_vo2max(raw.get("max_metrics"), "running"),
        vo2max_bike=_extract_vo2max(raw.get("max_metrics"), "cycling"),
        # Training status — da endpoint dedicato
        training_status=_extract_training_status(raw.get("training_status")),
        training_load_acute=_extract_training_load(raw.get("training_status"), "acute"),
        training_load_chronic=_extract_training_load(raw.get("training_status"), "chronic"),
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
            
            # HRV: opzionale
            hrv = None
            try:
                hrv = g.get_hrv_data(day.isoformat())
            except Exception:
                pass
            
            # VO2max: opzionale, endpoint diverso
            vo2max = None
            try:
                vo2max = g.get_max_metrics(day.isoformat())
            except Exception:
                pass
            
            # Training status: opzionale, endpoint diverso
            training_status = None
            try:
                training_status = g.get_training_status(day.isoformat())
            except Exception:
                pass
            
            payload = {
                **(user_summary or {}),
                "sleep": sleep,
                "hrv": hrv,
                "max_metrics": vo2max,
                "training_status": training_status,
            }
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
