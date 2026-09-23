"""Modalità legacy: il codice deve reggere a migration non ancora applicata.

Incidente reale: il codice che dipende dalla tabella `athletes` è andato in
produzione il 22/08, la migration non era stata eseguita, e dal 23/08
l'analytics giornaliero è crashato a ogni run con PGRST205 — 32 giorni senza
`daily_metrics`, mentre il Garmin sync continuava a funzionare e i dati grezzi
arrivavano regolarmente. Il guasto si è manifestato come una mail "Run failed"
ogni 3 ore.

Le migration si applicano a mano: il codice DEVE degradare, non morire.
"""
from __future__ import annotations

import pytest

import coach.utils.athlete as athlete_mod


class _TableMissing(Exception):
    """Errore PostgREST per tabella assente dallo schema."""

    def __str__(self) -> str:
        return (
            "{'message': \"Could not find the table 'public.athletes' in the "
            "schema cache\", 'code': 'PGRST205'}"
        )


class _FakeQuery:
    def __init__(self, raise_missing: bool):
        self._raise = raise_missing

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        if self._raise:
            raise _TableMissing()
        import types
        return types.SimpleNamespace(data=[{"id": "abc", "slug": "nicolo"}])


class _FakeSB:
    def __init__(self, athletes_missing: bool):
        self._missing = athletes_missing
        self.tables_requested: list[str] = []

    def table(self, name: str):
        self.tables_requested.append(name)
        return _FakeQuery(self._missing and name == "athletes")


#: La conftest sostituisce `legacy_single_athlete_mode` con una lambda per
#: tutta la suite (evita che la sonda colpisca i doppi degli altri test). Qui
#: serve invece la funzione VERA: la si cattura all'import, prima del patch.
_REAL_LEGACY_CHECK = athlete_mod.legacy_single_athlete_mode


@pytest.fixture(autouse=True)
def _real_probe(monkeypatch):
    monkeypatch.setattr(athlete_mod, "legacy_single_athlete_mode", _REAL_LEGACY_CHECK)
    _REAL_LEGACY_CHECK.cache_clear()
    athlete_mod.get_athlete.cache_clear()
    yield
    _REAL_LEGACY_CHECK.cache_clear()
    athlete_mod.get_athlete.cache_clear()


def test_rileva_la_tabella_mancante(monkeypatch):
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=True))
    assert athlete_mod.legacy_single_athlete_mode() is True


def test_aq_non_filtra_in_modalita_legacy(monkeypatch):
    """Senza tabella `athletes` non esiste un secondo atleta e la colonna
    athlete_id non esiste: filtrare darebbe errore, non filtrare è corretto."""
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=True))
    builder = athlete_mod.aq("activities")
    assert not isinstance(builder, athlete_mod._ScopedTable), (
        "in legacy il builder deve essere quello nudo, senza filtro athlete_id"
    )


def test_aq_filtra_quando_la_migration_e_applicata(monkeypatch):
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=False))
    monkeypatch.delenv("ATHLETE_ID", raising=False)
    builder = athlete_mod.aq("activities")
    assert isinstance(builder, athlete_mod._ScopedTable), (
        "con la tabella presente il filtro per atleta deve tornare attivo da solo"
    )


def test_altri_errori_non_vengono_scambiati_per_migration_mancante(monkeypatch):
    """Un guasto reale (rete, permessi) non deve far passare il sistema in
    legacy: nasconderebbe il problema invece di segnalarlo."""
    class _Boom:
        def table(self, _n):
            class _Q:
                def select(self, *a, **k): return self
                def limit(self, *a, **k): return self
                def execute(self): raise RuntimeError("connection refused")
            return _Q()

    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _Boom())
    with pytest.raises(RuntimeError, match="connection refused"):
        athlete_mod.legacy_single_athlete_mode()


def test_wellness_assunto_presente_in_legacy(monkeypatch):
    """Pre-migration l'unico atleta è su Garmin: has_wellness_data deve
    rispondere senza interrogare un'anagrafica che non esiste."""
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=True))
    assert athlete_mod.has_wellness_data() is True


def test_conflict_key_segue_lo_stato_dello_schema(monkeypatch):
    """La migration rinomina i vincoli UNIQUE aggiungendovi athlete_id. Un
    on_conflict hardcoded al valore vecchio fallirebbe con 42P10 il giorno in
    cui la migration viene applicata — rompendo sync wellness, metriche, test
    fitness e modulazioni, cioè un secondo guasto innescato proprio dal gesto
    che doveva completare la feature."""
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=True))
    assert athlete_mod.conflict_key("daily_wellness") == "date"
    assert athlete_mod.conflict_key("planned_sessions") == "planned_date,sport,session_type"

    athlete_mod.legacy_single_athlete_mode.cache_clear()
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=False))
    assert athlete_mod.conflict_key("daily_wellness") == "athlete_id,date"
    assert athlete_mod.conflict_key("planned_sessions") == "athlete_id,planned_date,sport,session_type"


def test_conflict_key_rifiuta_tabelle_non_dichiarate(monkeypatch):
    """Meglio un errore esplicito che una chiave inventata: `activities` e
    `bot_messages` hanno vincoli globali che la migration NON tocca, e
    aggiungervi athlete_id li romperebbe."""
    monkeypatch.setattr(athlete_mod, "get_supabase", lambda: _FakeSB(athletes_missing=True))
    with pytest.raises(ValueError, match="activities"):
        athlete_mod.conflict_key("activities")
