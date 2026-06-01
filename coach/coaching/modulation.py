"""Feature 2 — Modulazione mid-week con Telegram inline buttons.

Quando analyze_session rileva pattern critici (HRV crash, RPE alto, dolore),
genera proposta di modifica al piano dei prossimi 3 giorni.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from coach.utils.budget import BudgetExceededError
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Timestamp UTC ISO. Bug fix audit D: evita il literal 'now()' passato a
    PostgREST (cast string fragile, non valutazione SQL)."""
    return datetime.now(timezone.utc).isoformat()


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
    if mod.get("status") != "proposed":
        logger.info("Modulation %s already %s", modulation_id, mod.get("status"))
        return False

    # Bug fix audit D1: rifiuta modulazioni scadute. Una proposta basata su
    # condizioni di lunedì non deve essere applicata giorni dopo su stato stantio.
    # Retro-compatibile: expires_at NULL (righe pre-migration) = mai scade.
    expires_at = mod.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                logger.info("Modulation %s scaduta (%s), non applicata", modulation_id, expires_at)
                sb.table("plan_modulations").update({
                    "status": "expired",
                    "resolved_at": _now_iso(),
                }).eq("id", modulation_id).execute()
                return False
        except ValueError:
            logger.warning("Modulation %s: expires_at non parsabile (%s), procedo", modulation_id, expires_at)

    changes = mod.get("proposed_changes") or []
    applied = 0
    failed = 0
    skipped = 0
    for change in changes:
        try:
            ok = _apply_single_change(sb, change)
            if ok:
                applied += 1
            else:
                skipped += 1
                logger.warning("Modulation change skipped (date/sport mancante): %s", change)
        except Exception:
            logger.exception("Failed to apply change: %s", change)
            failed += 1

    # Bug fix audit D2: lo status riflette l'esito reale. Non dichiarare
    # "accepted" se alcune modifiche sono fallite o sono state saltate (così
    # l'atleta non viene informato di un successo con piano dimezzato).
    if failed == 0 and skipped == 0 and applied > 0:
        new_status = "accepted"
    elif applied == 0:
        new_status = "failed"
    else:
        new_status = "partial"

    sb.table("plan_modulations").update({
        "status": new_status,
        "resolved_at": _now_iso(),
    }).eq("id", modulation_id).execute()

    logger.info(
        "Modulation %s → %s (%d applied, %d skipped, %d failed)",
        modulation_id, new_status, applied, skipped, failed,
    )
    return new_status == "accepted"


def reject_modulation(modulation_id: str) -> bool:
    """Rifiuta una modulazione."""
    sb = get_supabase()
    sb.table("plan_modulations").update({
        "status": "rejected",
        "resolved_at": _now_iso(),
    }).eq("id", modulation_id).execute()
    logger.info("Modulation %s rejected", modulation_id)
    return True


def _apply_single_change(sb, change: dict) -> bool:
    """Applica una singola modifica al piano (upsert planned_sessions).

    Ritorna True se applicata, False se saltata (date/sport mancanti).
    Bug fix audit D3: fa MERGE sulla sessione esistente invece di sovrascrivere
    i campi non specificati con default — una modifica che tocca solo la durata
    non deve azzerare session_type/description della sessione reale.
    """
    target_date = change.get("date")
    sport = change.get("sport")
    new_session = change.get("new", {}) or {}

    if not target_date or not sport:
        return False

    # Recupera la sessione esistente per preservare i campi non modificati
    existing = sb.table("planned_sessions").select("*").eq(
        "planned_date", target_date
    ).eq("sport", sport).limit(1).execute()
    base = (existing.data[0] if existing.data else {}) or {}

    def _pick(key, default):
        if key in new_session and new_session[key] is not None:
            return new_session[key]
        if base.get(key) is not None:
            return base[key]
        return default

    payload = {
        "planned_date": target_date,
        "sport": sport,
        "session_type": _pick("session_type", "recovery"),
        "duration_s": _pick("duration_s", 3600),
        "description": _pick("description", "Sessione modificata per recupero"),
        "status": "planned",
    }

    sb.table("planned_sessions").upsert(
        payload, on_conflict="planned_date,sport"
    ).execute()
    return True


def _format_modulation_message(
    trigger: str, data: dict, changes: list[dict]
) -> str:
    """Formatta messaggio Telegram per proposta modulazione."""
    lines = ["🔍 <b>Ho notato che dopo la sessione di oggi:</b>\n"]

    # Trigger details. Bug fix audit D4: usa .get() is not None invece di
    # `in data`, altrimenti una chiave presente ma None fa crashare f"{None:.1f}".
    if data.get("hrv_z") is not None:
        lines.append(f"• HRV crashata ({data['hrv_z']:.1f}σ)")
    if data.get("rpe") is not None:
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
    """Manda messaggio con bottoni inline via Telegram e logga in bot_messages."""
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        logger.warning("Telegram not configured for modulation")
        return None

    from coach.utils.telegram_logger import send_and_log_message

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Accetto", "callback_data": f"accept_mod_{mod_id}"},
            {"text": "❌ Rifiuto", "callback_data": f"reject_mod_{mod_id}"},
            {"text": "💬 Discuto", "callback_data": f"discuss_mod_{mod_id}"},
        ]]
    }

    return send_and_log_message(
        message,
        purpose="modulation_proposal",
        context_data={"modulation_id": mod_id},
        reply_markup=keyboard,
    )


def generate_modulation_proposal(
    analysis_text: str,
    metrics: dict,
    upcoming_sessions: list[dict],
) -> list[dict]:
    """Genera proposta di modifica AI-driven per i prossimi 3 giorni."""
    try:
        from coach.utils.llm_client import get_client_for_purpose
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

        # Routing: "modulation" purpose va su Anthropic Haiku (decisione critica)
        client = get_client_for_purpose("modulation")
        result = client.call(
            purpose="modulation",
            system=system,
            messages=[{"role": "user", "content": context}],
            prefer_model="haiku",
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
