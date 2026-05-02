"""Backfill daily_metrics per tutto lo storico, giorno per giorno."""
from datetime import date, timedelta
from coach.analytics.daily import compute_for
from coach.utils.supabase_client import get_supabase


def main() -> None:
    sb = get_supabase()
    a = sb.table("activities").select("started_at").order("started_at").limit(1).execute()
    w = sb.table("daily_wellness").select("date").order("date").limit(1).execute()

    starts = []
    if a.data:
        starts.append(a.data[0]["started_at"][:10])
    if w.data:
        starts.append(w.data[0]["date"])
    if not starts:
        print("No data found")
        return

    start = date.fromisoformat(min(starts))
    end = date.today()
    total = (end - start).days + 1

    print(f"Backfilling {total} days: {start} -> {end}")

    cur = start
    n = 0
    while cur <= end:
        try:
            compute_for(cur)
            n += 1
            if n % 50 == 0:
                print(f"  ...{n}/{total} ({cur})")
        except Exception as e:
            print(f"  FAIL {cur}: {e}")
        cur += timedelta(days=1)

    print(f"Done: {n}/{total} days computed")


if __name__ == "__main__":
    main()
