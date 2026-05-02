"""Audit completo del DB: cosa abbiamo, cosa manca, cosa è null per campo."""
from coach.utils.supabase_client import get_supabase


def main() -> None:
    sb = get_supabase()

    print("=" * 70)
    print("ACTIVITIES")
    print("=" * 70)
    r = sb.table("activities").select("id", count="exact").execute()
    total = r.count
    print(f"Totale: {total}")

    fields = ["distance_m", "elevation_gain_m", "avg_hr", "max_hr", "hr_zones_s",
              "avg_power_w", "np_w", "avg_pace_s_per_km", "avg_pace_s_per_100m",
              "tss", "if_value", "rpe"]
    for f in fields:
        r = sb.table("activities").select("id", count="exact").not_.is_(f, "null").execute()
        pct = (r.count / total * 100) if total else 0
        print(f"  {f:30s} popolato in {r.count:4d}/{total} ({pct:5.1f}%)")

    # Per sport
    print("\nPer sport:")
    for sport in ["swim", "bike", "run", "brick", "strength", "other"]:
        r = sb.table("activities").select("id", count="exact").eq("sport", sport).execute()
        print(f"  {sport:10s} {r.count}")

    print()
    print("=" * 70)
    print("DAILY_WELLNESS")
    print("=" * 70)
    r = sb.table("daily_wellness").select("id", count="exact").execute()
    total = r.count
    print(f"Totale: {total} giorni")

    fields = ["hrv_rmssd", "hrv_status", "sleep_score", "sleep_total_s",
              "body_battery_max", "stress_avg", "resting_hr",
              "training_status", "vo2max_run", "vo2max_bike"]
    for f in fields:
        r = sb.table("daily_wellness").select("id", count="exact").not_.is_(f, "null").execute()
        pct = (r.count / total * 100) if total else 0
        print(f"  {f:30s} popolato in {r.count:4d}/{total} ({pct:5.1f}%)")

    print()
    print("=" * 70)
    print("DAILY_METRICS")
    print("=" * 70)
    r = sb.table("daily_metrics").select("id", count="exact").execute()
    total = r.count
    print(f"Totale: {total}")

    fields = ["ctl", "atl", "tsb", "daily_tss", "hrv_z_score",
              "readiness_score", "readiness_label"]
    for f in fields:
        r = sb.table("daily_metrics").select("id", count="exact").not_.is_(f, "null").execute()
        pct = (r.count / total * 100) if total else 0
        print(f"  {f:30s} popolato in {r.count:4d}/{total} ({pct:5.1f}%)")

    print()
    print("=" * 70)
    print("HEALTH (ultima sync per componente)")
    print("=" * 70)
    r = sb.table("health").select("component,last_success_at,failure_count").execute()
    for x in r.data:
        print(f"  {x['component']:25s} {x['last_success_at']} fails={x['failure_count']}")


if __name__ == "__main__":
    main()
