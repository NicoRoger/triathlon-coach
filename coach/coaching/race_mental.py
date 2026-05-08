"""Feature 5 — Race week mental coaching.

Genera mental check giornaliero (T-7→T-1), race briefing (T-2), vigilia (T-1), race day brief (T-0).
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from coach.utils.budget import BudgetExceededError

logger = logging.getLogger(__name__)


MENTAL_TECHNIQUES = {
    7: ("Visualizzazione", "Chiudi gli occhi 5 minuti. Visualizza la sequenza gara: partenza, T1, bici, T2, corsa, arrivo. Senti la fatica, gestiscila."),
    6: ("Body scan", "Prima di dormire: scansiona ogni parte del corpo dalla testa ai piedi. Nota tensioni, rilasciale."),
    5: ("Mantra personale", "Scegli 3 parole che ti rappresentano in gara. Ripetile durante il riscaldamento dei prossimi giorni."),
    4: ("Respirazione 4-7-8", "4s inspira, 7s trattieni, 8s espira. 3 cicli prima di dormire. Abbassa il cortisolo."),
    3: ("Focus points", "Identifica 3 momenti chiave della gara dove sai che sarà dura. Per ognuno, prepara una strategia mentale."),
    2: ("Routine pre-gara", "Scrivi la timeline di domani e dopodomani mattina minuto per minuto. Elimina le decisioni."),
    1: ("Accettazione", "Domani è gara. Hai fatto il lavoro. Non puoi cambiare niente. Accetta e goditi l'esperienza."),
}


def generate_mental_check(days_to_race: int) -> str:
    """Genera domanda mental + tecnica giornaliera per race week."""
    if days_to_race not in range(1, 8):
        return ""

    technique_name, technique_desc = MENTAL_TECHNIQUES.get(days_to_race, ("", ""))
    questions = {
        7: "Come ti senti a una settimana dalla gara? Eccitato, ansioso, tranquillo?",
        6: "Stai riuscendo a separare la preparazione fisica dalla pressione mentale?",
        5: "Qual è la tua più grande preoccupazione per la gara? Parliamone.",
        4: "Come dormi in questi giorni? Il sonno è il tuo superpotere.",
        3: "Hai il piano gara chiaro? Pacing, nutrizione, contingency?",
        2: "Domani è l'ultimo allenamento. Dopo, solo recovery e focus mentale.",
        1: "Vigilia. Come ti senti? Ricorda: l'ansia è energia da canalizzare.",
    }
    question = questions.get(days_to_race, "Come stai?")

    return (
        f"🧠 <b>Mental check — T-{days_to_race}</b>\n\n"
        f"{question}\n\n"
        f"<b>Tecnica del giorno: {technique_name}</b>\n"
        f"{technique_desc}"
    )


def generate_race_briefing(race_info: dict) -> str:
    """Genera race briefing personalizzato T-2 via AI."""
    try:
        from coach.utils.llm_client import get_client
        skill_path = Path(__file__).resolve().parent.parent.parent / "skills" / "race_briefing.md"
        system = skill_path.read_text(encoding="utf-8") if skill_path.exists() else "Sei un coach triathlon. Genera un race briefing."

        import json
        client = get_client()
        result = client.call(
            purpose="race_briefing",
            system=system,
            messages=[{"role": "user", "content": json.dumps(race_info, default=str, ensure_ascii=False)}],
            prefer_model="sonnet",
            max_tokens=1000,
        )
        return result["text"]
    except (BudgetExceededError, Exception) as e:
        logger.warning("Race briefing AI failed: %s", e)
        return "⚠️ Race briefing AI non disponibile. Usa il protocollo in skills/race_week_protocol.md."


def generate_vigilia_message() -> str:
    """T-1 sera: messaggio vigilia."""
    return (
        "🌙 <b>Vigilia di gara</b>\n\n"
        "Checklist serale:\n"
        "✅ Attrezzatura pronta e controllata\n"
        "✅ Nutrizione gara preparata\n"
        "✅ Sveglia impostata (con margine)\n"
        "✅ Outfit steso\n\n"
        "Cena leggera entro le 19:30. Niente cibi nuovi.\n"
        "A letto entro le 22:00. Se non dormi subito, è normale — il riposo conta comunque.\n\n"
        "Domani è il giorno. Hai fatto il lavoro. Fidati del processo. 💪"
    )


def generate_race_day_brief() -> str:
    """T-0 mattina: race day brief."""
    return (
        "🏁 <b>RACE DAY</b>\n\n"
        "Piano d'azione:\n"
        "1. Colazione 3h prima dello start\n"
        "2. Warm-up 20min prima\n"
        "3. Ricorda: i primi 10min sono sempre duri, non farti ingannare\n"
        "4. Pacing: parti conservativo, chiudi forte\n"
        "5. Nutrizione: segui il piano, non improvvisare\n\n"
        "Apri Claude Code per il piano gara dettagliato: <code>race day brief</code>\n\n"
        "In bocca al lupo! 🐺"
    )
