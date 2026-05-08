"""Riprocessa gli ultimi N giorni di dati Garmin con la pipeline aggiornata.

Task 0.5 di Step 5.1. Confronta copertura colonne PRIMA/DOPO.

Uso:
    python scripts/reprocess_recent.py [--days 30]
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Colonne di interesse per l'audit (escluse quelle di sistema)
WELLNESS_COLS = [
    "hrv_rmssd", "hrv_status", "sleep_score", "sleep_total_s",
    "sleep_deep_s", "sleep_rem_s", "sleep_efficiency",
    "body_battery_min", "body_battery_max", "stress_avg",
    "resting_hr", "training_status", "training_load_acute",
    "training_load_chronic", "vo2max_run", "vo2max_bike",
    "training_readiness_score", "avg_sleep_stress",
]

ACTIVITY_COLS = [
    "external_id", "source", "sport", "started_at", "duration_s",
    "distance_m", "elevation_gain_m", "avg_hr", "max_hr", "hr_zones_s",
    "avg_power_w", "np_w", "avg_pace_s_per_km", "avg_pace_s_per_100m",
    "tss", "if_value", "rpe", "splits", "weather",
]


def count_populated(rows: list[dict], columns: list[str]) -> dict[str, int]:
    """Conta quante righe hanno ciascuna colonna non-NULL."""
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for col in columns:
            if row.get(col) is not None:
                counts[col] += 1
    return counts


def audit_coverage(table: str, columns: list[str], days: int) -> None:
    """Stampa report copertura per tabella."""
    sb = get_supabase()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    if table == "daily_wellness":
        res = sb.table(table).select(",".join(columns)).gte("date", cutoff).execute()
    else:
        res = sb.table(table).select(",".join(columns)).gte("started_at", cutoff).execute()

    rows = res.data or []
    total = len(rows)

    if total == 0:
        print(f"\n{table}: NESSUN DATO negli ultimi {days} giorni")
        return

    counts = count_populated(rows, columns)
    populated = sum(1 for c in columns if counts.get(c, 0) > 0)

    print(f"\n{'='*60}")
    print(f"{table} — ultimi {days} giorni ({total} righe)")
    print(f"{'='*60}")
    print(f"{'Colonna':<35} {'Popolata':<10} {'%':<8}")
    print(f"{'-'*35} {'-'*10} {'-'*8}")

    for col in columns:
        n = counts.get(col, 0)
        pct = n / total * 100 if total > 0 else 0
        marker = "✅" if n > 0 else "❌"
        print(f"{marker} {col:<33} {n}/{total:<8} {pct:>5.1f}%")

    print(f"\nCopertura colonne: {populated}/{len(columns)} ({populated/len(columns)*100:.0f}%)")


def trigger_reprocess(days: int) -> None:
    """Triggera il reprocessing via garmin sync + analytics."""
    print(f"\n🔄 Riprocessando ultimi {days} giorni...")
    try:
        from coach.ingest.garmin import sync_activities, sync_wellness
        n_act = sync_activities(days_back=days)
        n_well = sync_wellness(days_back=days)
        print(f"   Sync completato: {n_act} attività, {n_well} wellness giorni")
    except Exception as e:
        print(f"   ⚠️ Sync fallito: {e}")
        print("   Procedo con l'audit sui dati esistenti...")

    try:
        from coach.analytics.daily import compute_for
        for offset in range(days, -1, -1):
            day = date.today() - timedelta(days=offset)
            compute_for(day)
        print(f"   Analytics ricalcolate per {days+1} giorni")
    except Exception as e:
        print(f"   ⚠️ Analytics fallite: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Riprocessa e audita dati Garmin recenti")
    parser.add_argument("--days", type=int, default=30, help="Giorni da riprocessare (default: 30)")
    parser.add_argument("--audit-only", action="store_true", help="Solo audit, no reprocess")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    print("=" * 60)
    print("STEP 5.1 — Validazione miglioramento completezza Garmin")
    print("=" * 60)

    if not args.audit_only:
        print("\n📊 PRIMA del reprocessing:")
        audit_coverage("daily_wellness", WELLNESS_COLS, args.days)
        audit_coverage("activities", ACTIVITY_COLS, args.days)

        trigger_reprocess(args.days)

    print("\n📊 DOPO il reprocessing:" if not args.audit_only else "\n📊 Stato attuale:")
    audit_coverage("daily_wellness", WELLNESS_COLS, args.days)
    audit_coverage("activities", ACTIVITY_COLS, args.days)

    return 0


if __name__ == "__main__":
    sys.exit(main())
