"""Ricalcola `daily_metrics` per un intervallo di giorni.

Serve quando l'analytics giornaliero non ha girato (guasto, migration
mancante, job fermo): i dati GREZZI restano in DB — attività e wellness
arrivano dall'ingest, che è indipendente — ma i valori DERIVATI (CTL/ATL/TSB,
readiness, HRV z-score) mancano per quei giorni.

`compute_for` è idempotente (upsert su (athlete_id, date)), quindi rieseguirlo
su giorni già calcolati è sicuro.

Uso:
    python scripts/backfill_metrics.py                      # tutto lo storico
    python scripts/backfill_metrics.py --from 2026-08-23    # da una data a oggi
    python scripts/backfill_metrics.py --from 2026-08-23 --to 2026-09-22
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from coach.analytics.daily import compute_for
from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _earliest_data_date() -> str | None:
    """Prima data con dati grezzi disponibili (attività o wellness)."""
    sb = get_supabase()
    starts = []
    a = sb.table("activities").select("started_at").order("started_at").limit(1).execute()
    if a.data:
        starts.append(a.data[0]["started_at"][:10])
    w = sb.table("daily_wellness").select("date").order("date").limit(1).execute()
    if w.data:
        starts.append(w.data[0]["date"])
    return min(starts) if starts else None


def backfill(start: date, end: date) -> tuple[int, list[str]]:
    """Ricalcola l'intervallo. Ritorna (giorni riusciti, elenco falliti)."""
    total = (end - start).days + 1
    print(f"Backfill {total} giorni: {start} → {end}")

    failures: list[str] = []
    ok = 0
    cur = start
    while cur <= end:
        try:
            compute_for(cur)
            ok += 1
            if ok % 25 == 0:
                print(f"  ...{ok}/{total} ({cur})")
        except Exception as e:  # noqa: BLE001
            # Si continua: un giorno senza dati sufficienti non deve bloccare
            # il recupero di tutti gli altri. I falliti sono elencati in fondo.
            print(f"  FAIL {cur}: {e}")
            failures.append(cur.isoformat())
        cur += timedelta(days=1)

    print(f"Fatto: {ok}/{total} giorni calcolati")
    if failures:
        print(f"Falliti ({len(failures)}): {', '.join(failures[:20])}"
              + (" ..." if len(failures) > 20 else ""))
    return ok, failures


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ricalcola daily_metrics per un intervallo")
    p.add_argument("--from", dest="start", help="Data iniziale YYYY-MM-DD (default: primo dato disponibile)")
    p.add_argument("--to", dest="end", help="Data finale YYYY-MM-DD (default: oggi)")
    args = p.parse_args()

    if args.start:
        start = date.fromisoformat(args.start)
    else:
        earliest = _earliest_data_date()
        if not earliest:
            print("Nessun dato grezzo trovato: niente da ricalcolare")
            return
        start = date.fromisoformat(earliest)

    end = date.fromisoformat(args.end) if args.end else today_rome()
    if start > end:
        raise SystemExit(f"Intervallo vuoto: {start} > {end}")

    backfill(start, end)


if __name__ == "__main__":
    main()
