"""Blocco 4.3 — Progress Tracker auto-generated.

Crea/aggiorna docs/progress_tracker.md con:
- Forma fisica (CTL trend)
- Zone fisiologiche (storico)
- Infortuni attivi
- Compliance piano
- Milestone raggiunti

Uso: python scripts/update_progress_tracker.py
Integrato nel workflow pattern-extraction (domenica notte).
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "docs" / "progress_tracker.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_tracker() -> str:
    from coach.utils.supabase_client import get_supabase
    from coach.utils.dt import today_rome

    sb = get_supabase()
    today = today_rome()
    lines = [
        "# Progress Tracker",
        "",
        f"*Aggiornato automaticamente il {today.isoformat()}*",
        "",
    ]

    # --- CTL Trend ---
    metrics_90d = sb.table("daily_metrics").select(
        "date,ctl,atl,tsb,readiness_score"
    ).gte("date", (today - timedelta(days=90)).isoformat()).order("date").execute().data or []

    lines.append("## Forma Fisica (CTL Trend)")
    lines.append("")
    if metrics_90d:
        latest = metrics_90d[-1]
        ctl_now = latest.get("ctl")
        first_ctl = next((m["ctl"] for m in metrics_90d if m.get("ctl") is not None), None)
        if ctl_now is not None:
            lines.append(f"- **CTL attuale**: {ctl_now:.1f}")
            if first_ctl is not None and first_ctl > 0:
                delta = ctl_now - first_ctl
                lines.append(f"- **Delta 90gg**: {delta:+.1f} ({delta / first_ctl * 100:+.0f}%)")
        if latest.get("tsb") is not None:
            lines.append(f"- **TSB oggi**: {latest['tsb']:.1f}")
        if latest.get("readiness_score") is not None:
            lines.append(f"- **Readiness**: {latest['readiness_score']}/100")

        ctl_vals = [m["ctl"] for m in metrics_90d if m.get("ctl") is not None]
        if len(ctl_vals) >= 7:
            recent_7 = ctl_vals[-7:]
            prev_7 = ctl_vals[-14:-7] if len(ctl_vals) >= 14 else ctl_vals[:7]
            from statistics import fmean
            trend = fmean(recent_7) - fmean(prev_7)
            arrow = "↗" if trend > 0.5 else "↘" if trend < -0.5 else "→"
            lines.append(f"- **Trend settimanale**: {arrow} ({trend:+.1f})")
    else:
        lines.append("- Dati insufficienti")
    lines.append("")

    # --- Zone fisiologiche ---
    lines.append("## Zone Fisiologiche")
    lines.append("")
    try:
        zones = sb.table("physiology_zones").select(
            "discipline,valid_from,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m,lthr,method"
        ).order("valid_from", desc=True).limit(10).execute().data or []
    except Exception:
        zones = []

    if zones:
        seen = set()
        for z in zones:
            disc = z.get("discipline", "?")
            if disc in seen:
                continue
            seen.add(disc)
            test_date = z.get("valid_from", "?")
            method = z.get("method") or ""
            parts = []
            if z.get("ftp_w"):
                parts.append(f"FTP {z['ftp_w']}W")
            if z.get("threshold_pace_s_per_km"):
                s = int(z["threshold_pace_s_per_km"])
                parts.append(f"soglia {s//60}:{s%60:02d}/km")
            if z.get("css_pace_s_per_100m"):
                s = int(z["css_pace_s_per_100m"])
                parts.append(f"CSS {s//60}:{s%60:02d}/100m")
            if z.get("lthr"):
                parts.append(f"LTHR {z['lthr']}bpm")
            val_str = ", ".join(parts) if parts else "da testare"
            lines.append(f"- **{disc}**: {val_str} (test {test_date}{', ' + method if method else ''})")
    else:
        lines.append("- Nessun test registrato — primo ciclo test previsto giugno 2026")
    lines.append("")

    # --- Infortuni ---
    lines.append("## Infortuni Attivi")
    lines.append("")
    injury_logs = sb.table("subjective_log").select(
        "logged_at,injury_details,injury_location"
    ).eq("injury_flag", True).gte(
        "logged_at", (today - timedelta(days=30)).isoformat()
    ).order("logged_at", desc=True).limit(5).execute().data or []

    if injury_logs:
        for inj in injury_logs:
            loc = inj.get("injury_location", "?")
            dt = inj["logged_at"][:10]
            details = (inj.get("injury_details") or "")[:80]
            lines.append(f"- [{dt}] {loc}: {details}")
    else:
        lines.append("- Nessun infortunio segnalato negli ultimi 30 giorni")
    lines.append("")

    # --- Compliance ---
    lines.append("## Compliance Piano")
    lines.append("")
    for week_offset in range(4):
        ws = today - timedelta(days=today.weekday() + 7 * (week_offset + 1))
        we = ws + timedelta(days=6)
        planned = sb.table("planned_sessions").select("id").gte(
            "planned_date", ws.isoformat()
        ).lte("planned_date", we.isoformat()).execute().data or []
        activities = sb.table("activities").select("id").gte(
            "started_at", ws.isoformat()
        ).lte("started_at", (we + timedelta(days=1)).isoformat()).execute().data or []
        p_count = len(planned)
        a_count = len(activities)
        pct = (a_count / p_count * 100) if p_count > 0 else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        lines.append(f"- Sett. {ws.strftime('%d/%m')}: {bar} {pct:.0f}% ({a_count}/{p_count})")
    lines.append("")

    # --- Prossima gara ---
    lines.append("## Prossimo Obiettivo")
    lines.append("")
    race = sb.table("races").select("name,race_date,priority").gte(
        "race_date", today.isoformat()
    ).order("race_date").limit(1).execute().data
    if race:
        r = race[0]
        days_left = (date.fromisoformat(r["race_date"]) - today).days
        lines.append(f"- **{r['name']}** ({r['priority']}): {r['race_date']} — {days_left} giorni")
    else:
        lines.append("- Nessuna gara in programma")

    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass

    sys.path.insert(0, str(ROOT))
    content = build_tracker()
    TRACKER.parent.mkdir(parents=True, exist_ok=True)
    TRACKER.write_text(content, encoding="utf-8")
    print(f"Progress tracker aggiornato: {TRACKER}")


if __name__ == "__main__":
    main()
