"""Generatore brief mattutino — RULE-BASED, ZERO chiamate LLM.

Output: stringa markdown formattata per Telegram (HTML mode).
Costo: €0. Filosofia: numeri prima delle parole, brevità, flag espliciti.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests

from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health

logger = logging.getLogger(__name__)

FRESHNESS_THRESHOLD_HOURS = 18


def _emoji_for_flag(flag: str) -> str:
    return {
        "fatigue_critical": "🚨",
        "fatigue_warning": "⚠️",
        "trend_negative": "📉",
        "anticipate_recovery_week": "🔄",
        "illness_flag": "🤒",
        "injury_flag": "🩹",
        "high_soreness": "😣",
        "low_motivation": "😐",
        "post_illness_caution": "🐢",
    }.get(flag, "ℹ️")


def _fmt_pace(s_per_km: Optional[float]) -> str:
    if not s_per_km:
        return "—"
    m = int(s_per_km // 60)
    s = int(s_per_km % 60)
    return f"{m}:{s:02d}/km"


def _planned_session_today(supabase) -> Optional[dict]:
    today = date.today().isoformat()
    res = supabase.table("planned_sessions").select("*").eq(
        "planned_date", today
    ).eq("status", "planned").execute()
    return res.data[0] if res.data else None


def _last_sync_age_hours(supabase) -> Optional[float]:
    res = supabase.table("health").select("last_success_at").eq(
        "component", "garmin_sync"
    ).execute()
    if not res.data or not res.data[0]["last_success_at"]:
        return None
    last = datetime.fromisoformat(res.data[0]["last_success_at"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def _today_metrics(supabase) -> Optional[dict]:
    today = date.today().isoformat()
    res = supabase.table("daily_metrics").select("*").eq("date", today).execute()
    return res.data[0] if res.data else None


def _today_wellness(supabase) -> Optional[dict]:
    today = date.today().isoformat()
    res = supabase.table("daily_wellness").select("*").eq("date", today).execute()
    return res.data[0] if res.data else None


def build_brief() -> str:
    sb = get_supabase()
    today = date.today()
    age = _last_sync_age_hours(sb)
    metrics = _today_metrics(sb)
    wellness = _today_wellness(sb)
    session = _planned_session_today(sb)

    lines = [f"<b>🏊 Brief {today.strftime('%a %d %b')}</b>"]

    # Freshness warning
    if age is not None and age > FRESHNESS_THRESHOLD_HOURS:
        lines.append(f"⚠️ <i>Ultimo sync Garmin {age:.0f}h fa — valutazione parziale.</i>")

    # PMC line
    if metrics:
        tsb = metrics.get("tsb")
        ctl = metrics.get("ctl")
        hrv_z = metrics.get("hrv_z_score")
        tsb_str = f"{tsb:+.0f}" if tsb is not None else "—"
        ctl_str = f"{ctl:.0f}" if ctl is not None else "—"
        hrv_str = f"{hrv_z:+.1f}σ" if hrv_z is not None else "—"
        lines.append(f"TSB <b>{tsb_str}</b> | CTL {ctl_str} | HRV {hrv_str}")

        # Readiness
        score = metrics.get("readiness_score")
        label = metrics.get("readiness_label")
        if score is not None:
            label_emoji = {"ready": "🟢", "caution": "🟡", "rest": "🔴"}.get(label, "⚪")
            lines.append(f"Readiness: <b>{score}/100</b> {label_emoji} ({label})")
    else:
        lines.append("<i>Metriche non ancora calcolate per oggi.</i>")

    # Wellness
    if wellness:
        sleep = wellness.get("sleep_score")
        bb_max = wellness.get("body_battery_max")
        if sleep or bb_max:
            sleep_str = f"😴 {sleep}" if sleep else "😴 —"
            bb_str = f"🔋 {bb_max}" if bb_max else "🔋 —"
            lines.append(f"{sleep_str} | {bb_str}")

    # Session
    if session:
        sport_emoji = {"swim": "🏊", "bike": "🚴", "run": "🏃", "brick": "🚴🏃", "strength": "💪"}.get(
            session.get("sport"), "🏋️"
        )
        dur_min = (session.get("duration_s") or 0) // 60
        type_str = session.get("session_type") or ""
        lines.append("")
        lines.append(f"{sport_emoji} <b>Oggi:</b> {type_str} · {dur_min}min")
        if session.get("description"):
            desc = session["description"]
            # Clip a 4 righe
            desc_lines = desc.strip().split("\n")[:4]
            lines.append(f"<i>{chr(10).join(desc_lines)}</i>")
    else:
        lines.append("")
        lines.append("📋 <i>Nessuna sessione pianificata.</i>")

    # Flags
    flags = (metrics or {}).get("flags") or []
    if flags:
        lines.append("")
        for f in flags:
            lines.append(f"{_emoji_for_flag(f)} {f}")

    # Footer azioni
    lines.append("")
    lines.append("<i>/log per note, /debrief stasera</i>")

    return "\n".join(lines)


def send_to_telegram(message: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        msg = build_brief()
        send_to_telegram(msg)
        record_health("briefing_morning", success=True)
        logger.info("Brief sent")
    except Exception as e:  # noqa: BLE001
        logger.exception("Brief failed")
        record_health("briefing_morning", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
