"""Compute daily_metrics: PMC + readiness + flags. Esegue dopo ogni ingest.

Idempotente: ricalcola sempre dall'inizio della finestra rilevante.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from coach.analytics.pmc import (
    DailyTSS,
    aggregate_daily_tss,
    compute_pmc_series,
)
from coach.analytics.readiness import (
    SubjectiveState,
    TrainingState,
    WellnessHistory,
    compute_readiness,
    hrv_z_score,
)
from coach.utils.health import record_health
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _fetch_activities_window(sb, start: date) -> list[dict]:
    res = sb.table("activities").select("id,started_at,sport,tss").gte(
        "started_at", start.isoformat()
    ).execute()
    return res.data or []


def _fetch_wellness_window(sb, start: date) -> list[dict]:
    res = sb.table("daily_wellness").select("*").gte("date", start.isoformat()).execute()
    return sorted(res.data or [], key=lambda r: r["date"])


def _fetch_recent_subjective(sb, day: date) -> dict:
    """Ultime 24h di subjective log."""
    since = (day - timedelta(days=1)).isoformat()
    res = sb.table("subjective_log").select("*").gte("logged_at", since).execute()
    rows = res.data or []
    out = {
        "motivation": None,
        "soreness": None,
        "illness_flag": False,
        "injury_flag": False,
        "illness_recent_days": 0,
    }
    for r in rows:
        if r.get("motivation") is not None:
            out["motivation"] = r["motivation"]
        if r.get("soreness") is not None:
            out["soreness"] = r["soreness"]
        if r.get("illness_flag"):
            out["illness_flag"] = True
        if r.get("injury_flag"):
            out["injury_flag"] = True

    # Check illness past 5 days
    since_5 = (day - timedelta(days=5)).isoformat()
    res2 = sb.table("subjective_log").select("logged_at").eq(
        "illness_flag", True
    ).gte("logged_at", since_5).execute()
    if res2.data:
        last = max(r["logged_at"] for r in res2.data)
        # Days since
        from datetime import datetime as dt, timezone
        last_dt = dt.fromisoformat(last.replace("Z", "+00:00")).date()
        out["illness_recent_days"] = (day - last_dt).days

    return out


def compute_for(day: date, history_days: int = 90) -> dict:
    """Calcola daily_metrics per `day` e fa upsert."""
    sb = get_supabase()
    window_start = day - timedelta(days=history_days)

    activities = _fetch_activities_window(sb, window_start)
    daily_tss = aggregate_daily_tss(activities)
    pmc_series = compute_pmc_series(daily_tss)

    today_pmc = next((p for p in pmc_series if p.day == day), None)

    # HRV z-score
    wellness_rows = _fetch_wellness_window(sb, day - timedelta(days=28))
    hrv_history = [r["hrv_rmssd"] for r in wellness_rows if r.get("hrv_rmssd") is not None]
    today_wellness = next((r for r in wellness_rows if r["date"] == day.isoformat()), {})

    z = None
    baseline_28 = None
    baseline_sd = None
    if today_wellness.get("hrv_rmssd") is not None and len(hrv_history) >= 7:
        # Escludi oggi dalla baseline
        baseline = [v for v in hrv_history if v != today_wellness["hrv_rmssd"]]
        if baseline:
            import statistics
            baseline_28 = statistics.fmean(baseline)
            baseline_sd = statistics.pstdev(baseline) if len(baseline) > 1 else 0
            z = hrv_z_score(today_wellness["hrv_rmssd"], baseline)

    # Readiness
    recent_z_scores = []
    for r in wellness_rows[-5:]:
        if r.get("hrv_rmssd") is not None and len(hrv_history) >= 7:
            recent_z_scores.append(hrv_z_score(r["hrv_rmssd"], hrv_history))

    wh = WellnessHistory(
        hrv_today=today_wellness.get("hrv_rmssd"),
        hrv_history_28d=hrv_history,
        hrv_recent_z_scores=recent_z_scores,
        sleep_score_today=today_wellness.get("sleep_score"),
        sleep_avg_7d=None,  # TODO se serve
        body_battery_morning=today_wellness.get("body_battery_max"),
        resting_hr_today=today_wellness.get("resting_hr"),
        resting_hr_baseline=None,
    )
    ts = TrainingState(
        ctl=today_pmc.ctl if today_pmc else 0,
        atl=today_pmc.atl if today_pmc else 0,
        tsb=today_pmc.tsb if today_pmc else 0,
        days_since_hard_session=None,
    )
    subj_data = _fetch_recent_subjective(sb, day)
    ss = SubjectiveState(**subj_data)

    readiness = compute_readiness(wh, ts, ss)

    metrics = {
        "date": day.isoformat(),
        "ctl": round(today_pmc.ctl, 2) if today_pmc else None,
        "atl": round(today_pmc.atl, 2) if today_pmc else None,
        "tsb": round(today_pmc.tsb, 2) if today_pmc else None,
        "daily_tss": round(today_pmc.daily_tss, 2) if today_pmc else None,
        "hrv_z_score": round(z, 2) if z is not None else None,
        "hrv_baseline_28d": round(baseline_28, 2) if baseline_28 is not None else None,
        "hrv_baseline_28d_sd": round(baseline_sd, 2) if baseline_sd is not None else None,
        "readiness_score": readiness.score,
        "readiness_label": readiness.label,
        "readiness_factors": readiness.factors,
        "flags": readiness.flags,
    }
    sb.table("daily_metrics").upsert(metrics, on_conflict="date").execute()
    return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        m = compute_for(date.today())
        logger.info("daily_metrics: %s", m)
        record_health("analytics_daily", success=True)
    except Exception as e:  # noqa: BLE001
        logger.exception("Analytics daily failed")
        record_health("analytics_daily", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
