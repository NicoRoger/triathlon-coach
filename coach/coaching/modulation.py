"""Feature 2 — Modulazione mid-week con Telegram inline buttons.

Quando analyze_session rileva pattern critici (HRV crash, RPE alto, dolore),
genera proposta di modifica al piano dei prossimi 3 giorni.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

from coach.utils.budget import BudgetExceededError
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def should_trigger_modulation(analysis_text: str, metrics: Optional[dict]) -> bool:
    """Determina se l'analisi sessione richiede una modulazione mid-week."""
    triggers = []

    # Pattern critici nel testo
    critical_keywords = [
        "hrv crash", "hrv crollata", "sovraccarico", "overreaching",
        "dolore", "infortunio", "malattia", "febbre",
        "sotto le aspettative", "problematica",
    ]
    text_lower = analysis_text.lower()
    for kw in critical_keywords:
        if kw in text_lower:
            triggers.append(kw)

    # Pattern critici nelle metriche
    if metrics:
        hrv_z = metrics.get("hrv_z_score")
        if hrv_z is not None and hrv_z < -1.5:
            triggers.append(f"hrv_z={hrv_z}")

        flags = metrics.get("flags") or []
        critical_flags = {"fatigue_critical", "hrv_crash", "illness_flag", "injury_flag"}
        for f in flags:
            if f in critical_flags:
                triggers.append(f"flag:{f}")

    return len(triggers) > 0


def propose_modulation(
    trigger_event: str,
    trigger_data: dict,
    proposed_changes: list[dict],
) -> Optional[str]:
    """Crea proposta modulazione e manda Telegram con bottoni.

    Args:
        trigger_event: es. "hrv_crash_post_session"
        trigger_data: es. {"hrv_z": -2.1, "rpe": 9, "analysis_id": "..."}
        proposed_changes: lista di modifiche [{date, old, new}]

    Returns:
        modulation_id se creata, None se errore
    """
    sb = get_supabase()

    # Salva proposta
    record = {
        "trigger_event": trigger_event,
        "trigger_data": trigger_data,
        "proposed_changes": proposed_changes,
        "status": "proposed",
    }
    res = sb.table("plan_modulations").insert(record).execute()
    if not res.data:
        logger.error("Failed to insert modulation")
        return None

    mod_id = res.data[0]["id"]

    # Manda Telegram con bottoni inline
    msg = _format_modulation_message(trigger_event, trigger_data, proposed_changes)
    msg_id = _send_modulation_telegram(msg, mod_id)

    if msg_id:
        sb.table("plan_modulations").update(
            {"telegram_message_id": msg_id}
        ).eq("id", mod_id).execute()

    logger.info("Modulation proposed: %s (trigger: %s)", mod_id, trigger_event)
    return mod_id


def apply_modulation(modulation_id: str) -> bool:
    """Applica una modulazione accettata: committa le modifiche sul piano."""
    sb = get_supabase()

    res = sb.table("plan_modulations").select("*").eq("id", modulation_id).limit(1).execute()
    if not res.data:
        return False

    mod = res.data[0]
    if mod["status"] != "proposed":
        logger.info("Modulation %s already %s", modulation_id, mod["status"])
        return False

    changes = mod.get("proposed_changes") or []
    for change in changes:
        try:
            _apply_single_change(sb, change)
        except Exception:
            logger.exception("Failed to apply change: %s", change)

    sb.table("plan_modulations").update({
        "status": "accepted",
        "resolved_at": "now()",
    }).eq("id", modulation_id).execute()

    logger.info("Modulation %s accepted and applied", modulation_id)
    return True


def reject_modulation(modulation_id: str) -> bool:
    """Rifiuta una modulazione."""
    sb = get_supabase()
    sb.table("plan_modulations").update({
        "status": "rejected",
        "resolved_at": "now()",
    }).eq("id", modulation_id).execute()
    logger.info("Modulation %s rejected", modulation_id)
    return True


def _apply_single_change(sb, change: dict) -> None:
    """Applica una singola modifica al piano (upsert planned_sessions)."""
    target_date = change.get("date")
    sport = change.get("sport")
    new_session = change.get("new", {})

    if not target_date or not sport:
        return

    payload = {
        "planned_date": target_date,
        "sport": sport,
        "session_type": new_session.get("session_type", "recovery"),
        "duration_s": new_session.get("duration_s", 3600),
        "description": new_session.get("description", "Sessione modificata per recupero"),
        "status": "planned",
    }

    sb.table("planned_sessions").upsert(
        payload, on_conflict="planned_date,sport"
    ).execute()


def _format_modulation_message(
    trigger: str, data: dict, changes: list[dict]
) -> str:
    """Formatta messaggio Telegram per proposta modulazione."""
    lines = ["🔍 <b>Ho notato che dopo la sessione di oggi:</b>\n"]

    # Trigger details
    if "hrv_z" in data:
        lines.append(f"• HRV crashata ({data['hrv_z']:.1f}σ)")
    if "rpe" in data:
        lines.append(f"• RPE {data['rpe']} vs previsto")
    if "flags" in data:
        for f in data["flags"]:
            lines.append(f"• Flag: {f}")
    if "analysis_excerpt" in data:
        lines.append(f"\n{data['analysis_excerpt']}")

    lines.append("\n<b>Propongo:</b>\n")
    for c in changes:
        old_desc = c.get("old_description", "come previsto")
        new_desc = c.get("new", {}).get("description", "modificato")
        lines.append(f"📅 {c.get('date', '?')}: {old_desc} → {new_desc}")

    return "\n".join(lines)


def _send_modulation_telegram(message: str, mod_id: str) -> Optional[int]:
    """Manda messaggio con bottoni inline via Telegram."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram not configured for modulation")
        return None

    import requests
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Accetto", "callback_data": f"accept_mod_{mod_id}"},
            {"text": "❌ Rifiuto", "callback_data": f"reject_mod_{mod_id}"},
            {"text": "💬 Discuto", "callback_data": f"discuss_mod_{mod_id}"},
        ]]
    }

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": int(chat_id),
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        },
        timeout=10,
    )
    if resp.ok:
        result = resp.json()
        return result.get("result", {}).get("message_id")
    else:
        logger.warning("Failed to send modulation Telegram: %s", resp.text)
        return None


def generate_modulation_proposal(
    analysis_text: str,
    metrics: dict,
    upcoming_sessions: list[dict],
) -> list[dict]:
    """Genera proposta di modifica AI-driven per i prossimi 3 giorni."""
    try:
        from coach.utils.llm_client import get_client
        from pathlib import Path

        skill_path = Path(__file__).resolve().parent.parent.parent / "skills" / "modulation.md"
        system = skill_path.read_text(encoding="utf-8") if skill_path.exists() else (
            "Sei un coach di triathlon. Sulla base dell'analisi sessione e delle metriche, "
            "proponi modifiche al piano dei prossimi 3 giorni per garantire recupero."
        )

        context = json.dumps({
            "analysis": analysis_text,
            "metrics": {k: v for k, v in metrics.items() if v is not None},
            "upcoming": upcoming_sessions,
        }, indent=2, default=str)

        client = get_client()
        result = client.call(
            purpose="modulation_proposal",
            system=system,
            messages=[{"role": "user", "content": context}],
            prefer_model="sonnet",
            max_tokens=600,
        )

        # Parse risposta come JSON se possibile
        import re
        text = result["text"]
        # Rimuove eventuali backticks markdown (es. ```json ... ```)
        text_clean = re.sub(r'^```(?:json)?\n?(.*?)\n?```$', r'\1', text.strip(), flags=re.DOTALL)
        try:
            return json.loads(text_clean)
        except json.JSONDecodeError:
            return [{"description": text_clean}]

    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping modulation proposal")
        return []
    except Exception:
        logger.exception("Modulation proposal generation failed")
        return []
