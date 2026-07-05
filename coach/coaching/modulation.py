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
from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Timestamp UTC ISO. Bug fix audit D: evita il literal 'now()' passato a
    PostgREST (cast string fragile, non valutazione SQL)."""
    return datetime.now(timezone.utc).isoformat()


def expire_past_modulations() -> int:
    """Scade tutte le modulazioni 'proposed' le cui session_date sono nel passato.

    Ritorna il numero di modulazioni scadute.
    """
    sb = get_supabase()
    # B2: data business Europe/Rome, non UTC (dopo le 22:00 Rome estive il
    # giorno UTC è ancora "ieri" e le modulazioni scadrebbero in ritardo/anticipo).
    today = today_rome().isoformat()

    res = sb.table("plan_modulations").select("id,proposed_changes").eq("status", "proposed").execute()
    rows = res.data or []

    expired_ids = []
    for row in rows:
        changes = row.get("proposed_changes") or []
        if not isinstance(changes, list):
            continue
        dates = [c.get("date") for c in changes if isinstance(c, dict) and c.get("date")]
        if dates and min(dates) < today:
            expired_ids.append(row["id"])

    if not expired_ids:
        return 0

    sb.table("plan_modulations").update({
        "status": "expired",
        "resolved_at": _now_iso(),
    }).in_("id", expired_ids).execute()

    logger.info("expire_past_modulations: scadute %d modulazioni obsolete", len(expired_ids))
    return len(expired_ids)


def should_trigger_modulation(analysis_text: str, metrics: Optional[dict]) -> bool:
    """Determina se l'analisi sessione richiede una modulazione mid-week."""
    triggers = []

    # Pattern critici nel testo. M2: un match grezzo su substring triggera
    # anche quando il testo NEGA il pattern ("nessun dolore segnalato"),
    # sprecando una chiamata Anthropic a pagamento (budget hard €5/mese) e
    # generando proposte di modulazione non necessarie. Scarta il match se
    # preceduto entro pochi caratteri da una negazione.
    critical_keywords = [
        "hrv crash", "hrv crollata", "sovraccarico", "overreaching",
        "dolore", "infortunio", "malattia", "febbre",
        "sotto le aspettative", "problematica",
    ]
    negations = ("nessun", "nessuna", "senza", "no ", "non ", "niente")
    text_lower = analysis_text.lower()
    for kw in critical_keywords:
        idx = text_lower.find(kw)
        if idx == -1:
            continue
        preceding = text_lower[max(0, idx - 20):idx]
        if any(neg in preceding for neg in negations):
            continue
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
    source: str = "auto",
) -> Optional[str]:
    """Crea proposta modulazione e manda Telegram con bottoni.

    Args:
        trigger_event: es. "hrv_crash_post_session"
        trigger_data: es. {"hrv_z": -2.1, "rpe": 9, "analysis_id": "..."}
        proposed_changes: lista di modifiche [{date, old, new}]
        source: "auto" (pipeline) o "coach" (decisione esplicita)

    Returns:
        modulation_id se creata, None se errore
    """
    # Pulisci le modulazioni obsolete prima di crearne una nuova
    try:
        expire_past_modulations()
    except Exception:
        logger.warning("expire_past_modulations fallita, procedo comunque", exc_info=True)

    sb = get_supabase()

    # Dedup: non rigenerare una proposta che tocca gli stessi giorni/sport di una
    # già 'proposed' aperta (era il bug delle 24 modulazioni "rest/recovery"
    # accumulate, una per sessione ogni giorno).
    def _change_keys(changes) -> set:
        return {
            (c.get("date"), c.get("sport"))
            for c in (changes or []) if isinstance(c, dict) and c.get("date")
        }
    new_keys = _change_keys(proposed_changes)
    if new_keys:
        open_res = sb.table("plan_modulations").select(
            "proposed_changes"
        ).eq("status", "proposed").execute()
        for row in (open_res.data or []):
            if _change_keys(row.get("proposed_changes")) & new_keys:
                logger.info("propose_modulation: proposta duplicata sugli stessi giorni, skip")
                return None

    # Salva proposta
    record = {
        "trigger_event": trigger_event,
        "trigger_data": trigger_data,
        "proposed_changes": proposed_changes,
        "status": "proposed",
        "source": source,
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
    # Solo le modulazioni con status='accepted' (tap atleta via Telegram) vengono
    # applicate. Accettare 'proposed' aggirava la regola confirm-before-write (CLAUDE.md §5.4).
    # apply_accepted_modulations() filtra già su 'accepted'; il bot Telegram setta
    # status='accepted' prima di chiamare apply_modulation. Stati terminali non vengono
    # riprocessati.
    if mod.get("status") != "accepted":
        logger.info("Modulation %s status=%s (not accepted), skipping", modulation_id, mod.get("status"))
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
    # Stato terminale 'applied' su pieno successo (evita riprocessamento dal cron).
    if failed == 0 and skipped == 0 and applied > 0:
        new_status = "applied"
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
    return new_status == "applied"


def apply_accepted_modulations() -> dict:
    """Trova le modulazioni accettate (dal tap Telegram) ma non ancora applicate
    e le applica al piano. Wired in ingest.yml (audit K1).

    Ritorna un riepilogo {applied, partial, failed, expired}.
    """
    sb = get_supabase()
    res = sb.table("plan_modulations").select("id").eq("status", "accepted").execute()
    rows = res.data or []
    summary = {"applied": 0, "partial": 0, "failed": 0, "expired": 0}
    for row in rows:
        mid = row["id"]
        try:
            ok = apply_modulation(mid)
            # rileggi lo status finale per il conteggio
            st = sb.table("plan_modulations").select("status").eq("id", mid).limit(1).execute()
            final = (st.data[0]["status"] if st.data else "failed")
            if final in summary:
                summary[final] += 1
        except Exception:
            logger.exception("apply_accepted_modulations: errore su %s", mid)
            summary["failed"] += 1
    if rows:
        logger.info("apply_accepted_modulations: %s", summary)
    return summary


def reject_modulation(modulation_id: str) -> bool:
    """Rifiuta una modulazione."""
    sb = get_supabase()
    sb.table("plan_modulations").update({
        "status": "rejected",
        "resolved_at": _now_iso(),
    }).eq("id", modulation_id).execute()
    logger.info("Modulation %s rejected", modulation_id)
    return True


# Una modulazione propone modifiche ai "prossimi 3 giorni": oltre questa finestra
# la proposta è obsoleta (i dati sono cambiati). La scadiamo per non lasciarla
# 'proposed' all'infinito — le proposte appese gonfiavano get_weekly_context e
# confondevano l'agente (BUG-011).
STALE_MODULATION_DAYS = 4


def expire_stale_modulations(max_age_days: int = STALE_MODULATION_DAYS) -> int:
    """Marca 'expired' le modulazioni 'proposed' più vecchie di max_age_days.

    Idempotente. Ritorna il numero di righe scadute.
    """
    sb = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    res = (
        sb.table("plan_modulations")
        .update({"status": "expired", "resolved_at": _now_iso()})
        .eq("status", "proposed")
        .lt("proposed_at", cutoff)
        .execute()
    )
    n = len(res.data or [])
    if n:
        logger.info("Expired %d stale modulation(s) older than %dd", n, max_age_days)
    return n


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

    # Non applicare modulazioni su sessioni già completate — evita di resettare
    # status='completed' a 'planned' su sessioni già eseguite.
    if base.get("status") == "completed":
        logger.warning("Skipping modulation on completed session: %s %s", target_date, sport)
        return False

    payload = {
        "planned_date": target_date,
        "sport": sport,
        "session_type": _pick("session_type", "recovery"),
        "duration_s": _pick("duration_s", 3600),
        "description": _pick("description", "Sessione modificata per recupero"),
        "status": "planned",
    }

    # C4: una modulazione che CAMBIA session_type (es. threshold→recovery, il
    # caso d'uso primario di §5.2) non deve fare upsert sulla chiave unique
    # (planned_date,sport,session_type): quella chiave è (date,sport,"threshold"),
    # il nuovo payload ha session_type="recovery" → nessun conflitto trovato →
    # INSERT di una riga nuova, lasciando la sessione intensa originale intatta
    # (doppio carico invece di sostituzione). Se esiste già una riga per
    # (planned_date,sport) la aggiorniamo per id, a prescindere dal session_type.
    if base.get("id"):
        sb.table("planned_sessions").update(payload).eq("id", base["id"]).execute()
    else:
        sb.table("planned_sessions").upsert(
            payload, on_conflict="planned_date,sport,session_type"
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
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_ALLOWED_CHAT_ID")
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not chat_id:
        logger.warning("Telegram not configured for modulation (TELEGRAM_BOT_TOKEN or TELEGRAM_*_CHAT_ID missing)")
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
            # 600 tagliava a metà il JSON di una proposta 3-giorni: il risultato
            # troncato falliva il parse e finiva mostrato come testo grezzo
            # all'atleta (fallback [{"description": text}] rimosso sotto).
            max_tokens=1200,
        )

        # Parse risposta come JSON se possibile
        import re
        text = result["text"]
        # Rimuove eventuali backticks markdown (es. ```json ... ```)
        text_clean = re.sub(r'^```(?:json)?\n?(.*?)\n?```$', r'\1', text.strip(), flags=re.DOTALL)
        try:
            parsed = json.loads(text_clean)
        except json.JSONDecodeError:
            logger.warning("Modulation proposal: JSON non parsabile, scarto (era: %r)", text_clean[:200])
            return []

        # Ogni change deve avere almeno date+sport (_apply_single_change li
        # richiede per applicare). Senza validazione, un output malformato
        # diventava una proposta con testo grezzo/troncato mostrata all'atleta
        # come se fosse una modifica reale, e il dedup (basato su date+sport)
        # non la intercettava mai.
        if not isinstance(parsed, list) or not all(
            isinstance(c, dict) and c.get("date") and c.get("sport") for c in parsed
        ):
            logger.warning("Modulation proposal: struttura invalida (manca date/sport), scarto: %r", parsed)
            return []
        return parsed

    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping modulation proposal")
        return []
    except Exception:
        logger.exception("Modulation proposal generation failed")
        return []


def main() -> None:
    """CLI: applica le modulazioni accettate ma non ancora applicate.

    Uso (wired in ingest.yml): python -m coach.coaching.modulation --apply-accepted
    """
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-accepted", action="store_true",
                        help="Applica le modulazioni con status='accepted'")
    parser.add_argument("--expire", action="store_true",
                        help="Scade le modulazioni 'proposed' con session_date nel passato")
    args = parser.parse_args()
    if args.expire:
        n = expire_past_modulations()
        logger.info("Expired %d stale modulations", n)
    if args.apply_accepted:
        summary = apply_accepted_modulations()
        logger.info("apply_accepted_modulations summary: %s", summary)


if __name__ == "__main__":
    main()
