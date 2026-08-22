"""Pausa coaching: sopprime le notifiche all'atleta, non quelle di sistema."""
from __future__ import annotations

from datetime import date

import pytest

from coach.utils.pause import SYSTEM_PURPOSES, is_paused, pause_until
from coach.utils.purposes import (
    BUDGET_ALERT,
    DEBRIEF_REMINDER,
    ENERGY_UPDATE,
    GENERIC,
    MORNING_BRIEF,
    PROACTIVE_QUESTION,
    WEEKLY_REVIEW_REMINDER,
)

@pytest.fixture(autouse=True)
def _pausa_attiva(monkeypatch):
    """La conftest disattiva la pausa per tutta la suite: questi test la
    riattivano su una data fissa, così non dipendono dal valore committato."""
    import coach.utils.pause as mod
    monkeypatch.setattr(mod, "PAUSE_UNTIL", date(2026, 8, 27))


DURANTE = date(2026, 8, 22)
GIORNO_FINE = date(2026, 8, 27)
DOPO = date(2026, 8, 28)


def test_notifiche_atleta_soppresse_durante_la_pausa():
    for purpose in (MORNING_BRIEF, ENERGY_UPDATE, DEBRIEF_REMINDER,
                    PROACTIVE_QUESTION, WEEKLY_REVIEW_REMINDER):
        assert is_paused(purpose, today=DURANTE), f"{purpose} doveva essere sospesa"


def test_alert_di_sistema_passano_sempre():
    """Budget, fallback provider e watchdog non parlano di allenamento:
    silenziarli significherebbe non accorgersi di un guasto mentre non guardi."""
    for purpose in (BUDGET_ALERT, GENERIC):
        assert purpose in SYSTEM_PURPOSES, f"{purpose} deve essere classificata di sistema"
        assert not is_paused(purpose, today=DURANTE), f"{purpose} non va soppressa"


def test_la_pausa_scade_da_sola():
    """Il giorno indicato è il PRIMO in cui le notifiche tornano: nessuno deve
    ricordarsi di riattivarle a mano."""
    assert is_paused(MORNING_BRIEF, today=DURANTE)
    assert not is_paused(MORNING_BRIEF, today=GIORNO_FINE)
    assert not is_paused(MORNING_BRIEF, today=DOPO)


def test_override_da_env(monkeypatch):
    monkeypatch.setenv("COACH_PAUSE_UNTIL", "2026-09-15")
    assert pause_until() == date(2026, 9, 15)
    assert is_paused(MORNING_BRIEF, today=date(2026, 9, 1))


def test_env_malformata_non_rompe_e_usa_il_default(monkeypatch):
    """Una data storta nell'env non deve far saltare l'invio: si ignora e si
    usa il default committato."""
    monkeypatch.setenv("COACH_PAUSE_UNTIL", "27 agosto")
    assert pause_until() == date(2026, 8, 27)  # default, env ignorata


def test_nessuna_pausa_se_disattivata(monkeypatch):
    import coach.utils.pause as mod
    monkeypatch.setattr(mod, "PAUSE_UNTIL", None)
    monkeypatch.delenv("COACH_PAUSE_UNTIL", raising=False)
    assert not is_paused(MORNING_BRIEF, today=DURANTE)
