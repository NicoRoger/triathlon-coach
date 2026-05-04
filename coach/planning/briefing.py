"""Briefing v2 — versione narrativa comprensibile.

Cambiamenti vs v1:
- Italiano naturale, niente sigle non spiegate
- Interpretazione esplicita di ogni numero
- Usa Garmin training load (acute/chronic) ora che è popolato
- Sezione "cosa fare oggi" + "watch-out specifici"
- Stratificato per dati disponibili (skip sezioni se dati assenti)

Costo runtime: 0 chiamate LLM, tutto rule-based.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import requests

from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health

logger = logging.getLogger(__name__)

FRESHNESS_HOURS = 18


# ============================================================================
# Interpretazioni hardcoded
# ============================================================================

def _interpret_sleep(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    if score >= 85:
        return f"{score}/100 — ottimo"
    if score >= 70:
        return f"{score}/100 — buono"
    if score >= 50:
        return f"{score}/100 — discreto"
    return f"{score}/100 — scarso, considera scarico"


def _interpret_hrv(z: Optional[float]) -> Optional[str]:
    if z is None:
        return None
    if z > 1:
        return f"+{z:.1f}σ — sopra la tua media, freschezza alta"
    if z >= -0.5:
        return f"{z:+.1f}σ — nella tua norma"
    if z >= -1:
        return f"{z:.1f}σ — leggermente bassa"
    if z >= -2:
        return f"{z:.1f}σ — bassa, segnale di affaticamento"
    return f"{z:.1f}σ — molto bassa, oggi recupero"


def _interpret_body_battery(bb: Optional[int]) -> Optional[str]:
    if bb is None:
        return None
    if bb >= 75:
        return f"{bb}/100 — alta"
    if bb >= 50:
        return f"{bb}/100 — media"
    return f"{bb}/100 — bassa"


def _interpret_acwr(acute: Optional[float], chronic: Optional[float]) -> tuple[Optional[float], Optional[str]]:
    """Restituisce (ratio, interpretazione)."""
    if acute is None or chronic is None or chronic == 0:
        return None, None
    ratio = acute / chronic
    if ratio < 0.8:
        return ratio, "decarica (carico recente sotto la fitness)"
    if ratio <= 1.3:
        return ratio, "zona allenante ottimale"
    if ratio <= 1.5:
        return ratio, "alto, monitorare"
    return ratio, "rischio infortunio (sopra 1.5 = soglia Gabbett)"


def _interpret_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    map_ita = {
        "productive": "fase produttiva",
        "peaking": "vicino al picco di forma",
        "maintaining": "mantenimento",
        "recovery": "in recupero",
        "unproductive": "carico non sta producendo adattamenti",
        "strained": "carico molto alto, sotto stress",
        "overreaching": "troppo carico, rischio overtraining",
        "detraining": "perdita di fitness",
        "no_recent_load": "poco carico recente",
        "no_status": "dati insufficienti",
    }
    return map_ita.get(status, status)


# ============================================================================
# Sezioni del brief
# ============================================================================

def _build_header(d: date) -> str:
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"<b>🏊 Brief {giorni[d.weekday()]} {d.day} {mesi[d.month-1]}</b>"


def _build_freshness_warning(age_hours: Optional[float]) -> str:
    if age_hours is not None and age_hours > FRESHNESS_HOURS:
        return f"⚠️ <i>Ultimo sync Garmin {age_hours:.0f}h fa — valutazione parziale.</i>\n"
    return ""


def _build_wellness_section(wellness: dict, metrics: dict) -> str:
    lines = []
    sleep_str = _interpret_sleep(wellness.get("sleep_score"))
    hrv_str = _interpret_hrv(metrics.get("hrv_z_score"))
    bb_str = _interpret_body_battery(wellness.get("body_battery_max"))

    if not any([sleep_str, hrv_str, bb_str]):
        return ""

    lines.append("<b>📊 Come stai oggi</b>")
    if sleep_str:
        lines.append(f"Sonno stanotte: {sleep_str}")
    if hrv_str:
        lines.append(f"HRV: {hrv_str}")
    if bb_str:
        lines.append(f"Energia al risveglio: {bb_str}")
    return "\n".join(lines)


def _build_load_section(metrics: dict) -> str:
    acute = metrics.get("garmin_acute_load")
    chronic = metrics.get("garmin_chronic_load")
    status = metrics.get("garmin_training_status")

    if acute is None and chronic is None and status is None:
        return ""

    lines = ["<b>📈 Carico (secondo Garmin)</b>"]
    if acute is not None:
        lines.append(f"Acute load: {acute:.0f} (carico recente, ultimi 7gg)")
    if chronic is not None:
        lines.append(f"Chronic load: {chronic:.0f} (la tua fitness, ultimi 28gg)")

    ratio, ratio_interp = _interpret_acwr(acute, chronic)
    if ratio is not None:
        lines.append(f"Rapporto acute/chronic: {ratio:.2f} → {ratio_interp}")

    status_interp = _interpret_status(status)
    if status_interp:
        lines.append(f"Stato Garmin: {status_interp}")

    return "\n".join(lines)


def _build_session_section(planned: Optional[dict]) -> str:
    lines = ["<b>🎯 Cosa fare oggi</b>"]
    if planned:
        sport_emoji = {"swim": "🏊", "bike": "🚴", "run": "🏃",
                       "brick": "🚴🏃", "strength": "💪"}.get(planned.get("sport"), "🏋️")
        dur_min = (planned.get("duration_s") or 0) // 60
        type_str = planned.get("session_type") or ""
        lines.append(f"{sport_emoji} {type_str} · {dur_min}min")
        if planned.get("description"):
            desc = planned["description"].strip().split("\n")[:4]
            lines.append(f"<i>{chr(10).join(desc)}</i>")
        return "\n".join(lines)

    lines.append("Nessuna sessione pianificata.")
    lines.append("<i>Il sistema di pianificazione automatica non è ancora attivo. "
                 "Per ora gestisci tu la sessione, oppure apri una conversazione "
                 "col coach in Claude Code per discutere cosa fare.</i>")
    return "\n".join(lines)


def _build_warnings_section(metrics: dict) -> str:
    """Warning specifici (hardcoded da CLAUDE.md, gestiti via env var)."""
    flags = metrics.get("flags") or []
    flag_msgs = {
        "fatigue_critical": "🚨 HRV in crash (z<-2) → recovery obbligatorio oggi",
        "fatigue_warning": "⚠️ HRV in calo da 2+ giorni → rimodula sessione di oggi",
        "trend_negative": "📉 HRV trend 7gg sotto baseline 28gg",
        "anticipate_recovery_week": "🔄 Suggerito anticipo settimana di scarico",
        "illness_flag": "🤒 Flag malattia attivo → stop intensità",
        "injury_flag": "🩹 Flag infortunio attivo → stop disciplina coinvolta",
        "high_soreness": "😣 Soreness alta segnalata",
        "low_motivation": "😐 Motivazione bassa segnalata",
        "post_illness_caution": "🐢 Cautela post-malattia",
    }
    flag_lines = [flag_msgs[f] for f in flags if f in flag_msgs]

    # Warning permanenti gestiti da env var (default True, settali a "false" quando risolti)
    permanent = []
    if os.environ.get("SHOULDER_ACTIVE", "true").lower() == "true":
        permanent.append(
            "<b>Spalla dx</b> (borsite ancora attiva): se nuoti, solo Z1-Z2 con focus tecnica. Niente serie intense."
        )
    if os.environ.get("PLANTAR_ACTIVE", "true").lower() == "true":
        permanent.append(
            "<b>Fascite plantare sx</b>: se corri, max +10% volume rispetto a settimana scorsa."
        )

    if not flag_lines and not permanent:
        return ""

    lines = ["<b>⚠️ Da tenere d'occhio</b>"]
    for f in flag_lines:
        lines.append(f)
    for p in permanent:
        lines.append(f"• {p}")
    return "\n".join(lines)


def _build_footer() -> str:
    return "<i>💬 /log note · /debrief stasera · /help comandi</i>"


# ============================================================================
# Main
# ============================================================================

def _last_sync_age_hours(sb) -> Optional[float]:
    res = sb.table("health").select("last_success_at").eq("component", "garmin_sync").execute()
    if not res.data or not res.data[0]["last_success_at"]:
        return None
    last = datetime.fromisoformat(res.data[0]["last_success_at"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def build_brief() -> str:
    sb = get_supabase()
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    today_iso = today.isoformat()

    age = _last_sync_age_hours(sb)

    metrics_res = sb.table("daily_metrics").select("*").eq("date", today_iso).execute()
    metrics = metrics_res.data[0] if metrics_res.data else {}

    wellness_res = sb.table("daily_wellness").select("*").eq("date", today_iso).execute()
    wellness = wellness_res.data[0] if wellness_res.data else {}

    planned_res = sb.table("planned_sessions").select("*").eq(
        "planned_date", today_iso
    ).eq("status", "planned").execute()
    planned = planned_res.data[0] if planned_res.data else None

    sections = [
        _build_header(today),
        _build_freshness_warning(age),
        _build_wellness_section(wellness, metrics),
        _build_load_section(metrics),
        _build_session_section(planned),
        _build_warnings_section(metrics),
        _build_footer(),
    ]
    # Join non-empty con doppia newline
    return "\n\n".join(s for s in sections if s.strip())


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
        logger.info("Brief v2 sent")
    except Exception as e:  # noqa: BLE001
        logger.exception("Brief v2 failed")
        record_health("briefing_morning", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()