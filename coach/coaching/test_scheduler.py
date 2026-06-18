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
    "bike": 42,    # FTP ogni 6 settimane
    "run": 42,     # threshold ogni 6 settimane
    "swim": 56,    # CSS ogni 8 settimane
}

# Mapping disciplina -> session_type + Garmin name
TEST_TEMPLATES = {
    "bike": {
        "session_type": "fitness_test",
        "test_name": "FTP Test 20min",
        "duration_s": 60 * 60,  # 60min totali (warmup + test + cooldown)
        "target_tss": 90,
        "description": (
            "🧪 FTP Test 20min. Nome Garmin esatto: 'FTP Test 20min'.\n"
            "Struttura: 15min warmup progressivo + 5×30s allunghi + 5min easy + "
            "20min ALL-OUT sostenibile + 10min cooldown.\n"
            "Risultato: media potenza 20min × 0.95 = FTP."
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


def _pick_test_date(sb, today: date) -> date:
    """Sceglie il giorno del test: martedì o sabato della prossima settimana
    libera, evitando già pianificate."""
    candidate = today + timedelta(days=7)
    # Allinea a martedì (weekday 1) o sabato (weekday 5)
    while candidate.weekday() not in (1, 5):
        candidate += timedelta(days=1)
    # Verifica che il giorno scelto sia libero
    res = (
        sb.table("planned_sessions")
        .select("id")
        .eq("planned_date", candidate.isoformat())
        .execute()
    )
    # Bug fix audit H2: cap iterazioni per evitare loop infinito se ogni
    # martedì/sabato è occupato (piano molto denso). Orizzonte 26 settimane.
    max_iter = 52
    while res.data and max_iter > 0:
        candidate += timedelta(days=1)
        while candidate.weekday() not in (1, 5):
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
    """Pianifica test fisiologici scaduti. Ritorna lista di test pianificati.

    Side effect: inserisce planned_sessions con session_type='fitness_test'.
    """
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

        # Pianifica
        target_date = _pick_test_date(sb, today)
        tpl = TEST_TEMPLATES[discipline]
        row = {
            "planned_date": target_date.isoformat(),
            "sport": discipline,
            "session_type": tpl["session_type"],
            "duration_s": tpl["duration_s"],
            "target_tss": tpl["target_tss"],
            "description": tpl["description"],
            "status": "planned",
        }
        try:
            sb.table("planned_sessions").insert(row).execute()
            scheduled.append({
                "discipline": discipline,
                "test_name": tpl["test_name"],
                "planned_date": target_date.isoformat(),
            })
            logger.info("Scheduled fitness test [%s] for %s", discipline, target_date.isoformat())
        except Exception:
            logger.exception("Failed to schedule test for %s", discipline)

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
