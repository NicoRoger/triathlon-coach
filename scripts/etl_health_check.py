"""ETL Health Check — verifica copertura colonne e gap nelle tabelle critiche.

Uso: python -m scripts.etl_health_check
Integrato in ingest.yml come step post-sync.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import timedelta

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

ACTIVITY_REQUIRED = ["avg_hr"]
ACTIVITY_OPTIONAL = ["tss", "splits", "weather"]
WELLNESS_REQUIRED = ["hrv_rmssd", "sleep_score"]
WELLNESS_OPTIONAL = ["training_readiness_score"]
COVERAGE_THRESHOLD = 0.70


def _coverage(rows: list[dict], columns: list[str]) -> dict[str, float]:
    if not rows:
        return {c: 0.0 for c in columns}
    total = len(rows)
    return {c: sum(1 for r in rows if r.get(c) is not None) / total for c in columns}


def _metrics_gap_days(rows: list[dict], window: int) -> list[str]:
    today = today_rome()
    expected = {(today - timedelta(days=i)).isoformat() for i in range(window)}
    present = {r["date"] for r in rows if r.get("date")}
    return sorted(expected - present)


def run_check() -> dict:
    sb = get_supabase()
    today = today_rome()
    since_30 = (today - timedelta(days=30)).isoformat()
    since_90 = (today - timedelta(days=90)).isoformat()

    all_act_cols = ACTIVITY_REQUIRED + ACTIVITY_OPTIONAL
    select_act = "id," + ",".join(all_act_cols)
    activities = sb.table("activities").select(select_act).gte(
        "started_at", f"{since_30}T00:00:00Z"
    ).order("started_at", desc=True).limit(100).execute().data or []

    all_well_cols = WELLNESS_REQUIRED + WELLNESS_OPTIONAL
    select_well = "id,date," + ",".join(all_well_cols)
    wellness = sb.table("daily_wellness").select(select_well).gte(
        "date", since_30
    ).order("date", desc=True).limit(100).execute().data or []

    metrics = sb.table("daily_metrics").select("date").gte(
        "date", since_90
    ).order("date", desc=True).limit(200).execute().data or []

    act_cov = _coverage(activities, all_act_cols)
    well_cov = _coverage(wellness, all_well_cols)
    gaps = _metrics_gap_days(metrics, 90)

    critical = []
    for col in ACTIVITY_REQUIRED:
        if act_cov.get(col, 0) < COVERAGE_THRESHOLD:
            critical.append(f"activities.{col}: {act_cov[col]:.0%}")
    for col in WELLNESS_REQUIRED:
        if well_cov.get(col, 0) < COVERAGE_THRESHOLD:
            critical.append(f"daily_wellness.{col}: {well_cov[col]:.0%}")
    if len(gaps) > 7:
        critical.append(f"daily_metrics: {len(gaps)} giorni mancanti su 90")

    return {
        "activities_count": len(activities),
        "activities_coverage": act_cov,
        "wellness_count": len(wellness),
        "wellness_coverage": well_cov,
        "metrics_gap_days": len(gaps),
        "metrics_gaps_sample": gaps[:10],
        "critical": critical,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass

    report = run_check()

    print("\n=== ETL Health Check ===")
    print(f"\nActivities (last 30d): {report['activities_count']}")
    for col, pct in report["activities_coverage"].items():
        is_required = col in ACTIVITY_REQUIRED
        if pct < COVERAGE_THRESHOLD:
            flag = " ⚠️" if is_required else " ℹ️ (optional)"
        else:
            flag = " ✓"
        print(f"  {col}: {pct:.0%}{flag}")

    print(f"\nWellness (last 30d): {report['wellness_count']}")
    for col, pct in report["wellness_coverage"].items():
        is_required = col in WELLNESS_REQUIRED
        if pct < COVERAGE_THRESHOLD:
            flag = " ⚠️" if is_required else " ℹ️ (optional)"
        else:
            flag = " ✓"
        print(f"  {col}: {pct:.0%}{flag}")

    print(f"\nMetrics gaps (90d): {report['metrics_gap_days']} days missing")
    if report["metrics_gaps_sample"]:
        print(f"  Sample: {', '.join(report['metrics_gaps_sample'])}")

    if report["critical"]:
        print(f"\n🚨 {len(report['critical'])} critical issues:")
        for c in report["critical"]:
            print(f"  - {c}")

        msg = (
            "<b>🔍 ETL Health Check</b>\n\n"
            + "\n".join(f"⚠️ {c}" for c in report["critical"])
            + f"\n\n<i>Attività: {report['activities_count']} | Wellness: {report['wellness_count']}</i>"
        )
        try:
            from coach.utils.telegram_logger import send_and_log_message
            send_and_log_message(msg, purpose="generic", parent_workflow="ingest.yml")
            logger.info("ETL alert sent via Telegram")
        except Exception:
            logger.exception("Failed to send ETL alert")
    else:
        print("\n✅ All coverages above threshold")


if __name__ == "__main__":
    main()
