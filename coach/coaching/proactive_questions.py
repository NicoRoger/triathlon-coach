"""Feature 3 — Domande proattive 2-3x/settimana.

Uso: python -m coach.coaching.proactive_questions
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.purposes import PROACTIVE_DISABLED_TODAY, PROACTIVE_QUESTION
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

QUESTIONS = {
    "injury": [
        "Come va la spalla oggi? Scala 0-10.",
        "Hai notato rigidità o dolore dopo l'ultimo allenamento?",
        "La fascite come risponde al volume attuale?",
        "Stai facendo gli esercizi di prevenzione questa settimana?",
    ],
    "recovery": [
        "Come hai dormito le ultime 2 notti?",
        "Ti senti recuperato dopo l'ultimo lungo?",
        "Quanto stress lavorativo questa settimana? 1-5.",
        "Stai bevendo abbastanza?",
        "Fatica insolita durante la giornata?",
    ],
    "motivation": [
        "Motivazione questa settimana: 1-10?",
        "C'è una sessione che ti entusiasma?",
        "Ti senti in track con gli obiettivi?",
        "Giusto equilibrio allenamento-vita?",
    ],
    "technique": [
        "Nell'ultima sessione nuoto, come l'appoggio?",
        "In bici, asimmetrie o scomodità?",
        "Nella corsa, cadenza naturale o forzata?",
        "Su cosa lavorare tecnicamente?",
    ],
    "race_week": [
        "Come ti senti mentalmente a N giorni dalla gara?",
        "Percorso e logistica controllati?",
        "Attrezzatura pronta e testata?",
        "Gestisci bene l'ansia pre-gara?",
        "Come dormi in questo periodo?",
    ],
    "general": [
        "Qualcosa da comunicarmi che non ti ho chiesto?",
        "Come giudichi la settimana finora? 1-10.",
        "Miglioramenti rispetto al mese scorso?",
        "Aspetto dell'allenamento da cambiare?",
        "Come va la nutrizione questa settimana?",
    ],
}


def select_question(context: dict) -> tuple[str, str]:
    flags = context.get("flags") or []
    if context.get("days_to_race") is not None and context["days_to_race"] <= 7:
        category = "race_week"
    elif any(f in flags for f in ("injury_flag", "injury_warning")):
        category = "injury"
    elif any(f in flags for f in ("fatigue_critical", "hrv_crash")):
        category = "recovery"
    else:
        day = today_rome().weekday()
        category = ["motivation", "general", "technique", "recovery", "general", "motivation", "general"][day]
    return category, random.choice(QUESTIONS[category])


def select_and_send_question() -> Optional[str]:
    sb = get_supabase()
    today = today_rome()

    # Cooldown: non mandare se già inviata nelle ultime 24h (evita spam se l'utente non risponde)
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = sb.table("bot_messages").select("id").eq(
        "purpose", PROACTIVE_QUESTION
    ).gte("sent_at", cutoff_24h).limit(1).execute()
    if recent.data:
        logger.info("Proactive question skipped: already sent in last 24h")
        return None

    # "🚫 Disabilita oggi" (bottone Telegram). Il flag vive in `sent_reminders`,
    # che ha UNIQUE (trigger_type, sent_date) ed è la tabella pensata per i
    # flag giornalieri. Prima il bot scriveva in `bot_messages`, dove
    # telegram_message_id è NOT NULL UNIQUE ed era già occupato dal messaggio
    # della domanda stessa: l'INSERT andava sempre in 409 e il bottone non ha
    # mai funzionato, pur rispondendo "disabilitate".
    disabled = sb.table("sent_reminders").select("id").eq(
        "trigger_type", PROACTIVE_DISABLED_TODAY
    ).eq("sent_date", today.isoformat()).limit(1).execute()
    if disabled.data:
        logger.info("Proactive question skipped: disabilitate oggi dall'atleta")
        return None

    metrics_res = sb.table("daily_metrics").select("flags,readiness_label").eq("date", today.isoformat()).limit(1).execute()
    metrics = metrics_res.data[0] if metrics_res.data else {}
    # Le gare vivono in `races` (come per briefing e proactive_reminders), non
    # in planned_sessions con session_type='race': quella riga non esiste in
    # tutto il repo, quindi days_to_race era sempre None e la categoria
    # "race_week" non è mai stata scelta — nella settimana di gara l'atleta
    # riceveva una domanda casuale invece del check-in dedicato.
    race_res = sb.table("races").select("race_date").gte(
        "race_date", today.isoformat()
    ).order("race_date").limit(1).execute()
    days_to_race = None
    if race_res.data:
        days_to_race = (date.fromisoformat(race_res.data[0]["race_date"]) - today).days
    context = {"flags": metrics.get("flags") or [], "readiness": metrics.get("readiness_label"), "days_to_race": days_to_race}
    category, question = select_question(context)
    cat_emoji = {"injury": "🩹", "recovery": "😴", "motivation": "🔥", "technique": "🔧", "race_week": "🏁", "general": "💬"}
    msg = f"{cat_emoji.get(category, '💬')} <b>Check-in coach</b>\n\n{question}\n\n<i>Rispondi qui, lo registro per la prossima analisi.</i>"
    try:
        from coach.utils.telegram_logger import send_and_log_message

        buttons = {
            "inline_keyboard": [[
                {"text": "💬 Rispondo dopo", "callback_data": "proactive_later"},
                {"text": "🤐 Salta", "callback_data": "proactive_skip"},
                {"text": "🚫 Disabilita oggi", "callback_data": "proactive_disable_today"},
            ]]
        }
        send_and_log_message(
            msg,
            purpose=PROACTIVE_QUESTION,
            context_data={"category": category, "question": question},
            parent_workflow="proactive-check-in.yml",
            reply_markup=buttons,
        )
        logger.info("Proactive question sent: [%s] %s", category, question)
        return question
    except Exception:
        logger.exception("Failed to send proactive question")
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError: pass
    from coach.utils.health import record_health
    try:
        q = select_and_send_question()
    except Exception as e:  # noqa: BLE001
        record_health("proactive_questions", success=False, error=str(e))
        raise
    record_health("proactive_questions", success=True)
    print(f"Domanda: {q}" if q else "Nessuna domanda")


if __name__ == "__main__":
    main()
