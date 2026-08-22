"""Contesto atleta e query con scope automatico.

Ogni job gira PER UN ATLETA: il contesto arriva da `ATHLETE_SLUG` (i workflow
diventano una matrix, un run per atleta). Non serve passare l'id a ogni
funzione — sarebbero ~290 firme da cambiare — ma serve rendere DIFFICILE
scrivere una query non filtrata, perché il modo in cui questo approccio
fallisce è il peggiore possibile: leggere o scrivere silenziosamente i dati
dell'atleta sbagliato.

Da qui in poi, per le tabelle con dati d'atleta si usa `aq()` invece di
`get_supabase().table()`:

    aq("activities").select("*").gte("started_at", since).execute()

`aq` applica da sé il filtro su athlete_id in lettura e lo inietta nei
payload di insert/upsert. Il test in tests/test_athlete_scoping.py impedisce
che nuove query non scopate entrino nel codice.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_supabase():
    """Risolve il client al MOMENTO DELLA CHIAMATA, non all'import.

    L'import è deliberatamente dentro la funzione: così passa ogni volta dalla
    macchina degli import, che consulta `sys.modules`. Legando il riferimento
    (o l'oggetto modulo) all'import, i test che sostituiscono
    `coach.utils.supabase_client` con un doppio non riuscirebbero a
    intercettare le query passate da `aq()` e fallirebbero tentando di
    contattare Supabase davvero — per un motivo che non c'entra nulla con ciò
    che verificano. Il costo è una lookup in un dict.
    """
    from coach.utils.supabase_client import get_supabase as _get_client
    return _get_client()

#: Tabelle con dati d'atleta: DEVONO essere filtrate. Deve restare allineata
#: alla migration 2026-08-09-multi-athlete-foundation.sql (un test lo verifica).
PER_ATHLETE_TABLES = frozenset({
    "activities", "daily_wellness", "daily_metrics", "subjective_log",
    "planned_sessions", "mesocycles", "races", "physiology_zones",
    "session_analyses", "plan_modulations", "beliefs", "beliefs_history",
    "active_constraints", "predictions", "outcomes", "recommendations",
    "hypothesis_tests", "decision_audit", "sent_reminders",
    "bot_messages", "pending_confirmations",
})

#: Tabelle di sistema: condivise, mai filtrate per atleta.
#: - health: i componenti per-atleta si distinguono per nome (garmin_sync
#:   vs strava_sync), vedi migration.
#: - api_usage: il cap di spesa è GLOBALE; athlete_id serve solo ad attribuire.
#: - athletes: è l'anagrafica stessa.
SYSTEM_TABLES = frozenset({"health", "api_usage", "athletes"})

DEFAULT_SLUG = "nicolo"


class UnknownAthleteError(RuntimeError):
    """Slug non presente in `athletes` (o tabella non ancora migrata)."""


@lru_cache(maxsize=4)
def get_athlete(slug: str) -> dict:
    """Riga `athletes` per slug. Cache per run (i job sono effimeri)."""
    res = get_supabase().table("athletes").select("*").eq("slug", slug).limit(1).execute()
    if not res.data:
        raise UnknownAthleteError(
            f"Nessun atleta con slug '{slug}'. Atleti disponibili: "
            f"{[a.get('slug') for a in (get_supabase().table('athletes').select('slug').execute().data or [])]}"
        )
    return res.data[0]


def current_slug() -> str:
    """Slug dell'atleta di questo run.

    Il default esiste per retro-compatibilità: i workflow non ancora
    convertiti a matrix continuano a girare sull'atleta storico invece di
    fallire. Va rimosso quando tutti passano ATHLETE_SLUG esplicito.
    """
    return os.environ.get("ATHLETE_SLUG") or DEFAULT_SLUG


def current_athlete() -> dict:
    return get_athlete(current_slug())


def current_athlete_id() -> str:
    """Id dell'atleta corrente.

    `ATHLETE_ID` corto-circuita la lettura di `athletes`: risparmia una query
    per ogni job (che è effimero e ne farebbe una a ogni run) e rende banale
    il contesto nei test, che non devono simulare l'anagrafica per esercitare
    tutt'altra logica.
    """
    explicit = os.environ.get("ATHLETE_ID")
    if explicit:
        return explicit
    return current_athlete()["id"]


def has_wellness_data() -> bool:
    """False per fonti senza HRV/sonno (Strava).

    Il readiness va ricalibrato su TSB + soggettivo: l'assenza di quei dati è
    una PROPRIETÀ della fonte, non un guasto, e va distinta da un sync rotto.
    """
    return bool(current_athlete().get("has_wellness_data", True))


def aq(table: str):
    """Query builder già filtrato sull'atleta corrente.

    Per le tabelle di sistema ritorna il builder nudo (non hanno athlete_id).
    Su una tabella sconosciuta solleva: meglio un errore esplicito che una
    query non filtrata che passa inosservata.
    """
    sb = get_supabase()
    if table in SYSTEM_TABLES:
        return sb.table(table)
    if table not in PER_ATHLETE_TABLES:
        raise ValueError(
            f"Tabella '{table}' non classificata. Aggiungila a PER_ATHLETE_TABLES "
            f"(se contiene dati d'atleta) o a SYSTEM_TABLES (se condivisa)."
        )
    return _ScopedTable(sb.table(table), current_athlete_id())


def with_athlete(payload: dict, athlete_id: Optional[str] = None) -> dict:
    """Inietta athlete_id in un payload, senza sovrascriverlo se già presente."""
    out = dict(payload)
    out.setdefault("athlete_id", athlete_id or current_athlete_id())
    return out


class _ScopedTable:
    """Wrapper sottile attorno al builder PostgREST.

    Le letture ricevono `.eq("athlete_id", ...)`; insert/upsert/update ricevono
    l'id nel payload. Tutto il resto passa inalterato al builder sottostante,
    così l'API resta quella nota e non serve reimparare nulla.
    """

    def __init__(self, table: Any, athlete_id: str):
        self._table = table
        self._athlete_id = athlete_id

    def select(self, *args: Any, **kwargs: Any):
        return self._table.select(*args, **kwargs).eq("athlete_id", self._athlete_id)

    def insert(self, payload: Any, **kwargs: Any):
        return self._table.insert(self._stamp(payload), **kwargs)

    def upsert(self, payload: Any, **kwargs: Any):
        return self._table.upsert(self._stamp(payload), **kwargs)

    def update(self, payload: Any, **kwargs: Any):
        # L'update NON stampa l'id nel payload (cambierebbe proprietario), ma
        # vincola le righe colpite a quelle dell'atleta corrente.
        return self._table.update(payload, **kwargs).eq("athlete_id", self._athlete_id)

    def delete(self, **kwargs: Any):
        return self._table.delete(**kwargs).eq("athlete_id", self._athlete_id)

    def _stamp(self, payload: Any) -> Any:
        if isinstance(payload, list):
            return [with_athlete(p, self._athlete_id) for p in payload]
        return with_athlete(payload, self._athlete_id)

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - passthrough
        return getattr(self._table, name)
