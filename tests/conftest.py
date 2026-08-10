"""Configurazione condivisa della suite.

I test esercitano la logica di coaching con client Supabase finti. Da quando
le query sono scopate per atleta (`coach/utils/athlete.aq`), serve anche un
contesto atleta: senza, ogni query tenterebbe di leggere l'anagrafica dal
client stubbato e fallirebbe per un motivo che non c'entra nulla con ciò che
il test verifica.

`ATHLETE_ID` corto-circuita quella lettura, quindi basta impostarlo una volta
per tutta la suite.
"""
from __future__ import annotations

import os

import pytest

TEST_ATHLETE_ID = "00000000-0000-0000-0000-0000000000a1"


@pytest.fixture(autouse=True, scope="session")
def _athlete_context() -> None:
    os.environ.setdefault("ATHLETE_ID", TEST_ATHLETE_ID)
    os.environ.setdefault("ATHLETE_SLUG", "test-athlete")
