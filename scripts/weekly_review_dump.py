"""Dump dati per weekly review. Stampa tutto su stdout in formato leggibile.

Range:
  - Past 7 days: settimana da analizzare (ultimi 7 giorni completi)
  - Past 14 days: per trend HRV/PMC
  - Next 14 days: planned_sessions già presenti

Uso: PYTHONPATH=. python -m scripts.weekly_review_dump [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from coach.utils.supabase_client import get_supabase


def fmt_dur(s):
    if s is None:
        return "—"
    s = int(s)
    return f"{s // 3600}h{(s % 3600) // 60:02d}'"


def fmt_num(x, decimals=1):
    if x is None:
        return "—"
    return f"{float(x):.{decimals}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None)
    args = ap.parse_args()

    today = (
        datetime.fromisoformat(args.today).date()
        if args.today
        else datetime.now(ZoneInfo("Europe/Rome")).date()
    )

    week_start = today - timedelta(days=7)
    week_end = today - timedelta(days=1)
    metrics_start = today - timedelta(days=14)
    plan_end = today + timedelta(days=14)

    sb = get_supabase()

    print(f"# WEEKLY REVIEW DUMP")
    print(f"Today: {today} ({today.strftime('%A')})")
    print(f"Past week analyzed: {week_start} → {week_end}")
    print(f"Metrics range: {metrics_start} → {today}")
    print()

    # 1) ACTIVITIES (past 7 days)
    print("=" * 70)
    print("1) ACTIVITIES (last 7 days)")
    print("=" * 70)
    acts = (
        sb.table("activities")
        .select("*")
        .gte("started_at", week_start.isoformat())
        .lt("started_at", today.isoformat())
        .order("started_at")
        .execute()
    ).data
    print(f"Totale: {len(acts)}")
    total_dur = sum((a.get("duration_s") or 0) for a in acts)
    total_tss = sum(float(a.get("tss") or 0) for a in acts)
    print(f"Volume tot: {fmt_dur(total_dur)} | TSS tot: {total_tss:.0f}")
    print()
    for a in acts:
        d = a["started_at"][:10]
        wd = datetime.fromisoformat(a["started_at"].replace("Z", "+00:00")).strftime("%a")
        sport = a.get("sport")
        dur = fmt_dur(a.get("duration_s"))
        dist = a.get("distance_m")
        dist_str = f"{dist/1000:.1f}km" if dist else "—"
        tss = a.get("tss")
        rpe = a.get("rpe")
        avg_hr = a.get("avg_hr")
        print(
            f"  {d} {wd} {sport:8s} {dur:>7s} dist={dist_str:>7s} "
            f"TSS={fmt_num(tss, 0):>4s} RPE={rpe or '—'} HR={avg_hr or '—'}"
        )
    print()

    # 2) DAILY METRICS (past 14 days for trend)
    print("=" * 70)
    print("2) DAILY METRICS (last 14 days)")
    print("=" * 70)
    metrics = (
        sb.table("daily_metrics")
        .select("*")
        .gte("date", metrics_start.isoformat())
        .lte("date", today.isoformat())
        .order("date")
        .execute()
    ).data
    print(f"{'date':12s} {'CTL':>6s} {'ATL':>6s} {'TSB':>6s} {'TSS':>5s} {'HRVz':>6s} {'flags'}")
    for m in metrics:
        flags = ",".join(m.get("flags") or [])
        print(
            f"  {m['date']:10s} {fmt_num(m.get('ctl')):>6s} "
            f"{fmt_num(m.get('atl')):>6s} {fmt_num(m.get('tsb')):>6s} "
            f"{fmt_num(m.get('daily_tss'), 0):>5s} {fmt_num(m.get('hrv_z_score'), 2):>6s} "
            f"{flags}"
        )
    print()

    # 3) DAILY WELLNESS (past 14 days)
    print("=" * 70)
    print("3) DAILY WELLNESS (last 14 days)")
    print("=" * 70)
    wellness = (
        sb.table("daily_wellness")
        .select("date,hrv_rmssd,sleep_score,sleep_total_s,body_battery_max,stress_avg,resting_hr,training_status,training_load_acute,training_load_chronic")
        .gte("date", metrics_start.isoformat())
        .lte("date", today.isoformat())
        .order("date")
        .execute()
    ).data
    print(
        f"{'date':12s} {'HRV':>5s} {'sleep':>6s} {'sleepH':>7s} "
        f"{'BB':>4s} {'stress':>6s} {'rHR':>4s} {'g_acute':>8s} {'g_chron':>8s} status"
    )
    for w in wellness:
        sleep_h = (w.get("sleep_total_s") or 0) / 3600
        print(
            f"  {w['date']:10s} {fmt_num(w.get('hrv_rmssd'), 0):>5s} "
            f"{fmt_num(w.get('sleep_score'), 0):>6s} {sleep_h:>6.1f}h "
            f"{fmt_num(w.get('body_battery_max'), 0):>4s} "
            f"{fmt_num(w.get('stress_avg'), 0):>6s} "
            f"{fmt_num(w.get('resting_hr'), 0):>4s} "
            f"{fmt_num(w.get('training_load_acute'), 0):>8s} "
            f"{fmt_num(w.get('training_load_chronic'), 0):>8s} "
            f"{w.get('training_status') or '—'}"
        )
    print()

    # 4) SUBJECTIVE LOG (past 7 days)
    print("=" * 70)
    print("4) SUBJECTIVE LOG (last 7 days)")
    print("=" * 70)
    subj = (
        sb.table("subjective_log")
        .select("*")
        .gte("logged_at", week_start.isoformat())
        .order("logged_at")
        .execute()
    ).data
    print(f"Totale entries: {len(subj)}")
    for s in subj:
        d = s["logged_at"][:10]
        kind = s.get("kind")
        rpe = s.get("rpe")
        sore = s.get("soreness")
        mot = s.get("motivation")
        ill = "ILL" if s.get("illness_flag") else ""
        inj = f"INJ:{s.get('injury_location') or '?'}" if s.get("injury_flag") else ""
        text = (s.get("raw_text") or "")[:80].replace("\n", " ")
        parsed = s.get("parsed_data")
        parsed_str = f" parsed={json.dumps(parsed)[:80]}" if parsed else ""
        print(
            f"  {d} {kind:18s} RPE={rpe or '—'} sore={sore or '—'} "
            f"mot={mot or '—'} {ill} {inj}"
        )
        if text:
            print(f"     text: {text}")
        if parsed_str:
            print(f"    {parsed_str}")
    print()

    # 5) PLANNED VS EXECUTED (past 7 days)
    print("=" * 70)
    print("5) PLANNED SESSIONS (last 7 days, status check)")
    print("=" * 70)
    plans = (
        sb.table("planned_sessions")
        .select("*")
        .gte("planned_date", week_start.isoformat())
        .lt("planned_date", today.isoformat())
        .order("planned_date")
        .execute()
    ).data
    print(f"Totale sessioni pianificate: {len(plans)}")
    for p in plans:
        print(
            f"  {p['planned_date']} {p.get('sport'):8s} "
            f"{p.get('session_type') or '?':20s} "
            f"dur={fmt_dur(p.get('duration_s'))} "
            f"tss={fmt_num(p.get('target_tss'), 0)} "
            f"status={p.get('status')}"
        )
    print()

    # 6) UPCOMING PLANNED SESSIONS
    print("=" * 70)
    print("6) UPCOMING PLANNED SESSIONS (next 14 days)")
    print("=" * 70)
    upcoming = (
        sb.table("planned_sessions")
        .select("*")
        .gte("planned_date", today.isoformat())
        .lte("planned_date", plan_end.isoformat())
        .order("planned_date")
        .execute()
    ).data
    print(f"Totale: {len(upcoming)}")
    for p in upcoming:
        print(
            f"  {p['planned_date']} {p.get('sport'):8s} "
            f"{p.get('session_type') or '?':20s} "
            f"dur={fmt_dur(p.get('duration_s'))} "
            f"status={p.get('status')}"
        )
    print()

    # 7) MESOCYCLES
    print("=" * 70)
    print("7) MESOCYCLES (active)")
    print("=" * 70)
    mesos = (
        sb.table("mesocycles")
        .select("*")
        .lte("start_date", today.isoformat())
        .gte("end_date", today.isoformat())
        .execute()
    ).data
    for m in mesos:
        print(f"  {m.get('name')} | {m.get('phase')} | {m.get('start_date')} → {m.get('end_date')}")
        if m.get("notes"):
            print(f"    notes: {m['notes']}")
    print()

    # 8) RACES upcoming
    print("=" * 70)
    print("8) RACES UPCOMING")
    print("=" * 70)
    races = (
        sb.table("races")
        .select("*")
        .gte("race_date", today.isoformat())
        .order("race_date")
        .execute()
    ).data
    for r in races:
        days = (date.fromisoformat(r["race_date"]) - today).days
        print(
            f"  {r.get('name')} | {r.get('race_date')} ({days}d) | "
            f"prio={r.get('priority')} | dist={r.get('distance')}"
        )
    print()

    # 9) PHYSIOLOGY ZONES (current)
    print("=" * 70)
    print("9) PHYSIOLOGY ZONES (current)")
    print("=" * 70)
    zones = (
        sb.table("physiology_zones")
        .select("*")
        .or_(f"valid_to.is.null,valid_to.gte.{today.isoformat()}")
        .order("valid_from", desc=True)
        .execute()
    ).data
    for z in zones:
        print(
            f"  {z.get('discipline'):6s} | ftp={z.get('ftp_w')}W | "
            f"thr_pace={z.get('threshold_pace_s_per_km')}s/km | "
            f"css={z.get('css_pace_s_per_100m')}s/100m | "
            f"lthr={z.get('lthr')} | hrmax={z.get('hr_max')} | "
            f"valid {z.get('valid_from')} → {z.get('valid_to') or 'now'}"
        )
    print()

    # 10) HEALTH
    print("=" * 70)
    print("10) HEALTH STATUS (sync freshness)")
    print("=" * 70)
    h = sb.table("health").select("*").execute().data
    for x in h:
        print(
            f"  {x['component']:25s} last_ok={x.get('last_success_at')} "
            f"fails={x.get('failure_count')}"
        )


if __name__ == "__main__":
    main()
