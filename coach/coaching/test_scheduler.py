"""Fase 2.6 — Fitness test active scheduling.

Cron settimanale (domenica notte): se l'ultimo test di una disciplina è
> 42 giorni AND non c'è un test pianificato nei prossimi 14 giorni AND
non siamo in race week, il sistema propone il prossimo test.

Inserisce in `planned_sessions` con session_type='fitness_test' e
description con il nome esatto Garmin per il rilevamento automatico
(via fitness_test_processor.py).

Trigger reminder Telegram (gestito da proactive_reminders.py).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# Cadenza test per disciplina (in giorni)
TEST_INTERVAL_DAYS = {
    "bike": 42,    # threshold HR ogni 6 settimane
    "run": 42,     # threshold ogni 6 settimane
    "swim": 56,    # CSS ogni 8 settimane
}

# Giorni della struttura settimanale fissa (CLAUDE.md §2) per disciplina —
# un test va piazzato in un giorno già dedicato a quello sport, non in un
# martedì/sabato generico che potrebbe cadere su un giorno di un altro sport
# (es. un test corsa piazzato di martedì, giorno nuoto).
# weekday(): lunedi=0 ... domenica=6
DISCIPLINE_WEEKDAYS = {
    "run": {0, 4, 6},   # lunedì, venerdì, domenica
    "swim": {1, 3},     # martedì, giovedì
    "bike": {2, 5},     # mercoledì, sabato
}

# Mapping disciplina -> session_type + Garmin name
TEST_TEMPLATES = {
    "bike": {
        "session_type": "fitness_test",
        "test_name": "Threshold Bike HR 20min",
        "duration_s": 60 * 60,  # 60min totali (warmup + test + cooldown)
        "target_tss": 90,
        "description": (
            "🧪 Threshold Bike HR 20min. Nome Garmin esatto: 'Threshold Bike HR 20min'.\n"
            "Struttura: 15min warmup progressivo + 5×30s allunghi + 5min easy + "
            "20min ALL-OUT sostenibile a sforzo costante + 10min cooldown.\n"
            "Risultato: media HR dei 20min = LTHR bici. "
            "NOTA: atleta senza wattmetro — test a frequenza cardiaca, non a potenza."
        ),
    },
    "run": {
        "session_type": "fitness_test",
        "test_name": "Threshold Run 30min",
        "duration_s": 50 * 60,
        "target_tss": 70,
        "description": (
            "🧪 Threshold Run 30min. Nome Garmin esatto: 'Threshold Run 30min'.\n"
            "Struttura: 15min warmup easy + 4×30s allunghi + 30min ALL-OUT "
            "sostenibile + 10min cooldown.\n"
            "Risultato: media HR ultimi 20min = LTHR; media pace 30min = soglia."
        ),
    },
    "swim": {
        "session_type": "fitness_test",
        "test_name": "CSS Test 400-200",
        "duration_s": 50 * 60,
        "target_tss": 50,
        "description": (
            "🧪 CSS Test (400m + 200m). Nome Garmin esatto: 'CSS Test 400-200'.\n"
            "Struttura: 400m warmup tecnica + 200m progressivo + riposo 5min + "
            "400m ALL-OUT + 10min easy + 200m ALL-OUT + 400m cooldown.\n"
            "Risultato CSS = (400m_time − 200m_time) / 2 secondi per 100m."
        ),
    },
}


# ============================================================================
# Schedule logic
# ============================================================================

def _last_test_date(sb, discipline: str) -> Optional[date]:
    """Data ultimo test (valid_from) per disciplina dalla tabella physiology_zones."""
    res = (
        sb.table("physiology_zones")
        .select("valid_from")
        .eq("discipline", discipline)
        .order("valid_from", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data or not res.data[0].get("valid_from"):
        return None
    try:
        return date.fromisoformat(res.data[0]["valid_from"])
    except Exception:
        return None


def _is_test_already_planned(sb, discipline: str, today: date, days_ahead: int = 14) -> bool:
    until = today + timedelta(days=days_ahead)
    res = (
        sb.table("planned_sessions")
        .select("id")
        .eq("sport", discipline)
        .eq("session_type", "fitness_test")
        .gte("planned_date", today.isoformat())
        .lte("planned_date", until.isoformat())
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _is_race_week(sb, today: date) -> bool:
    """True se gara A/B entro 10 giorni (taper, evita test)."""
    until = today + timedelta(days=10)
    res = (
        sb.table("races")
        .select("id,race_date,priority")
        .in_("priority", ["A", "B"])
        .gte("race_date", today.isoformat())
        .lte("race_date", until.isoformat())
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _pick_test_date(sb, today: date, discipline: str) -> date:
    """Sceglie il giorno del test: un giorno della struttura settimanale fissa
    dedicato a `discipline` (A1), nella prossima settimana libera."""
    weekdays = DISCIPLINE_WEEKDAYS.get(discipline, {1, 5})
    candidate = today + timedelta(days=7)
    while candidate.weekday() not in weekdays:
        candidate += timedelta(days=1)
    # Verifica che il giorno scelto sia libero
    res = (
        sb.table("planned_sessions")
        .select("id")
        .eq("planned_date", candidate.isoformat())
        .execute()
    )
    # Bug fix audit H2: cap iterazioni per evitare loop infinito se ogni
    # giorno dedicato è occupato (piano molto denso). Orizzonte 26 settimane.
    max_iter = 52
    while res.data and max_iter > 0:
        candidate += timedelta(days=1)
        while candidate.weekday() not in weekdays:
            candidate += timedelta(days=1)
        res = (
            sb.table("planned_sessions")
            .select("id")
            .eq("planned_date", candidate.isoformat())
            .execute()
        )
        max_iter -= 1
    if res.data:
        logger.warning(
            "_pick_test_date: nessuno slot libero entro l'orizzonte, uso %s comunque",
            candidate.isoformat(),
        )
    return candidate


def schedule_overdue_tests(today: Optional[date] = None) -> list[dict]:
    """Propone test fisiologici scaduti. Ritorna lista di proposte create.

    A1: NON scrive più direttamente in planned_sessions (violava la regola
    inviolabile §5.4 — nessuna modifica al piano senza conferma esplicita
    dell'atleta). Ogni test scaduto diventa una proposta in plan_modulations
    coi soliti bottoni Telegram ✅/❌: solo dopo l'accettazione
    apply_accepted_modulations() (già in ingest.yml) la scrive sul piano.
    """
    from coach.coaching.modulation import propose_modulation

    sb = get_supabase()
    today = today or today_rome()
    scheduled: list[dict] = []

    if _is_race_week(sb, today):
        logger.info("Race week (entro 10gg) → skip test scheduling")
        return scheduled

    for discipline, interval in TEST_INTERVAL_DAYS.items():
        last_test = _last_test_date(sb, discipline)
        if last_test is not None:
            days_since = (today - last_test).days
            if days_since < interval:
                logger.info("[%s] last test %dgg fa (< %d) → skip", discipline, days_since, interval)
                continue
        # Test mai fatto o scaduto
        if _is_test_already_planned(sb, discipline, today):
            logger.info("[%s] test già pianificato entro 14gg → skip", discipline)
            continue

        # Proponi (richiede conferma atleta via Telegram prima di finire sul piano)
        target_date = _pick_test_date(sb, today, discipline)
        tpl = TEST_TEMPLATES[discipline]
        mod_id = propose_modulation(
            trigger_event="fitness_test_due",
            trigger_data={
                "analysis_excerpt": (
                    f"Test {discipline} scaduto (>{interval}gg dall'ultimo). "
                    f"Propongo {tpl['test_name']} per {target_date.isoformat()}."
                ),
            },
            proposed_changes=[{
                "date": target_date.isoformat(),
                "sport": discipline,
                "new": {
                    "session_type": tpl["session_type"],
                    "duration_s": tpl["duration_s"],
                    "target_tss": tpl["target_tss"],
                    "description": tpl["description"],
                },
            }],
            source="test_scheduler",
        )
        if mod_id:
            scheduled.append({
                "discipline": discipline,
                "test_name": tpl["test_name"],
                "planned_date": target_date.isoformat(),
                "modulation_id": mod_id,
            })
            logger.info("Proposed fitness test [%s] for %s (modulation %s)",
                        discipline, target_date.isoformat(), mod_id)
        else:
            logger.info("[%s] proposta test non creata (duplicata o errore)", discipline)

    return scheduled


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scheduled = schedule_overdue_tests()
    if not scheduled:
        logger.info("No tests scheduled this run")
    for s in scheduled:
        logger.info("Scheduled: %s for %s on %s", s["test_name"], s["discipline"], s["planned_date"])


if __name__ == "__main__":
    main()
