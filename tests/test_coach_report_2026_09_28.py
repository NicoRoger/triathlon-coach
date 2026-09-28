"""Regressioni dai bug segnalati dal coach il 28/09/2026.

1. Energia al risveglio 11/100 con risveglio reale a 52: il massimo del
   giorno letto prima che l'orologio sincronizzasse la notte.
2. Analisi post-seduta che leggeva 7:35/km come "più veloce" di 5:40-6:15.
3. Sedute pianificate mai collegate all'attività svolta.
4. Watchdog: weekly_analysis (on-demand) sempre "mai eseguito?".
5. Belief confutata a mano sbloccata dal reconcile domenicale.
"""
from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def _is_project_module(name: str) -> bool:
    return name.split(".")[0] in ("coach", "scripts")


@pytest.fixture(scope="module")
def m():
    """Moduli REALI del progetto. Altri test registrano stub parziali in
    sys.modules (es. coach.utils.dt con il solo today_rome): li mettiamo da
    parte per la durata di questo file e li ripristiniamo dopo, così né noi
    vediamo i loro stub né loro vedono i nostri moduli reali."""
    saved = {k: v for k, v in sys.modules.items() if _is_project_module(k)}
    for k in saved:
        del sys.modules[k]
    try:
        yield SimpleNamespace(
            psa=importlib.import_module("coach.coaching.post_session_analysis"),
            briefing=importlib.import_module("coach.planning.briefing"),
            matching=importlib.import_module("coach.planning.session_matching"),
            watchdog=importlib.import_module("scripts.watchdog"),
            beliefs=importlib.import_module("coach.analytics.belief_engine"),
            athlete=importlib.import_module("coach.utils.athlete"),
            supabase_client=importlib.import_module("coach.utils.supabase_client"),
        )
    finally:
        for k in [k for k in sys.modules if _is_project_module(k)]:
            del sys.modules[k]
        sys.modules.update(saved)


# --- 1. Body Battery al risveglio -------------------------------------------

def _wellness(bb_max, sleep_end=None, at_wake=None, sleep_score=None):
    raw = {"bodyBatteryHighestValue": bb_max, "sleep": {"dailySleepDTO": {}}}
    if sleep_end:
        raw["sleep"]["dailySleepDTO"]["sleepEndTimestampGMT"] = sleep_end
    if at_wake is not None:
        raw["bodyBatteryAtWakeTime"] = at_wake
    return {"body_battery_max": bb_max, "sleep_score": sleep_score, "raw_payload": raw}


def test_night_not_synced_gives_no_body_battery(m):
    """Notte non ancora caricata: il max del giorno è il valore di mezzanotte."""
    w = _wellness(11)
    assert m.briefing._wake_body_battery(w) is None
    assert "11/100" not in m.briefing._build_energy_section(w, {})


def test_night_synced_uses_day_max(m):
    w = _wellness(52, sleep_end=1790000000000, sleep_score=68)
    assert m.briefing._wake_body_battery(w) == 52
    assert "52/100" in m.briefing._build_energy_section(w, {})


def test_explicit_wake_value_wins(m):
    w = _wellness(60, sleep_end=1790000000000, at_wake=52)
    assert m.briefing._wake_body_battery(w) == 52


def test_build_energy_update_defers_until_night_synced(m, monkeypatch):
    """Notte non sincronizzata → messaggio vuoto (main_energy non registra
    l'invio, il prossimo ingest riprova), anche se c'è il readiness."""

    class _Res:
        def __init__(self, data):
            self.data = data

    class _Q:
        def __init__(self, data):
            self._data = data

        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self): return _Res(self._data)

    class _SB:
        def table(self, name):
            if name == "daily_wellness":
                return _Q([_wellness(11)])
            return _Q([{"readiness_score": 72, "garmin_training_readiness": 30}])

    monkeypatch.setattr(m.briefing, "get_supabase", lambda: _SB())
    assert m.briefing.build_energy_update() == ""


# --- 2. Pace corsa vs piano --------------------------------------------------

PLANNED_RUN = {
    "description": "Corsa continua 30' in Z1/Z2 basso. Target FC 135-148 bpm. "
                   "Pace atteso 5:40-6:15/km ma il pace NON è il vincolo.",
    "structured": {
        "steps": [{"target": "HR 135-148 (cap 148, alert 150)"}],
        # Definizioni di zona: NON sono il target della seduta.
        "zones_derived": {"zones": {"z2": {"pace_range": "5:25/km–4:59/km"}}},
    },
}


def test_slower_pace_is_reported_as_slower(m):
    ctx = m.psa._run_pace_context({"avg_pace_s_per_km": 455.79, "avg_hr": 144}, PLANNED_RUN)
    assert "7:36/km" in ctx
    assert "5:40–6:15/km" in ctx
    assert "più LENTO del range di 1:21" in ctx
    assert "VELOCE" not in ctx
    assert "cap RISPETTATO" in ctx


def test_faster_pace_and_hr_over_cap(m):
    ctx = m.psa._run_pace_context({"avg_pace_s_per_km": 320, "avg_hr": 152}, PLANNED_RUN)
    assert "più VELOCE del range di 0:20" in ctx
    assert "cap SUPERATO di 4 bpm" in ctx


def test_pace_context_without_plan(m):
    ctx = m.psa._run_pace_context({"avg_pace_s_per_km": 360, "avg_hr": 140}, None)
    assert ctx.startswith("Pace media eseguita: 6:00/km")
    assert "range" not in ctx


def test_prompt_never_carries_raw_pace_seconds(m):
    out = m.psa._clean_for_prompt({"avg_pace_s_per_km": 455.79, "raw_payload": {}})
    assert out == {"avg_pace": "7:36/km"}


# --- 3. Matching seduta ↔ attività --------------------------------------------

def _p(pid, day, sport, duration=None, session_type="endurance"):
    return {"id": pid, "planned_date": day, "sport": sport,
            "duration_s": duration, "session_type": session_type}


def _a(aid, started_at, sport, duration):
    return {"id": aid, "started_at": started_at, "sport": sport, "duration_s": duration}


def test_matches_same_rome_day_and_sport(m):
    planned = [_p("p-run", "2026-09-21", "run", 2400), _p("p-swim", "2026-09-22", "swim", 1800)]
    acts = [
        _a("a-run", "2026-09-21T17:02:33+00:00", "run", 1995),
        _a("a-swim", "2026-09-22T16:41:21+00:00", "swim", 1860),
    ]
    assert sorted(m.matching.match_sessions(planned, acts)) == [("p-run", "a-run"), ("p-swim", "a-swim")]


def test_uses_rome_date_not_utc(m):
    """Attività alle 23:30 UTC del 21 = 01:30 Rome del 22."""
    planned = [_p("p", "2026-09-22", "run", 1800)]
    acts = [_a("a", "2026-09-21T23:30:00+00:00", "run", 1800)]
    assert m.matching.match_sessions(planned, acts) == [("p", "a")]


def test_no_match_on_other_sport_or_day(m):
    planned = [_p("p", "2026-09-21", "run", 1800)]
    acts = [_a("a1", "2026-09-21T17:00:00+00:00", "bike", 1800),
            _a("a2", "2026-09-20T17:00:00+00:00", "run", 1800)]
    assert m.matching.match_sessions(planned, acts) == []


def test_double_session_picks_closest_duration_and_never_reuses(m):
    planned = [_p("p-long", "2026-09-21", "run", 3600), _p("p-short", "2026-09-21", "run", 1200)]
    acts = [_a("a-short", "2026-09-21T06:00:00+00:00", "run", 1300),
            _a("a-long", "2026-09-21T17:00:00+00:00", "run", 3500)]
    assert sorted(m.matching.match_sessions(planned, acts)) == [("p-long", "a-long"), ("p-short", "a-short")]


def test_fitness_test_day_is_left_to_the_test_processor(m):
    planned = [_p("p-test", "2026-09-21", "run", 1800, session_type="fitness_test"),
               _p("p-easy", "2026-09-21", "run", 1800)]
    acts = [_a("a", "2026-09-21T17:00:00+00:00", "run", 1800)]
    assert m.matching.match_sessions(planned, acts) == []


# --- 4. Watchdog / proactive check-in -----------------------------------------

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


def test_on_demand_component_never_missing_or_stale(m):
    assert "weekly_analysis" in m.watchdog.ON_DEMAND_COMPONENTS
    assert "weekly_analysis" not in m.watchdog.CADENCE_THRESHOLDS_HOURS
    missing = m.watchdog.compute_alerts([], NOW)
    old = m.watchdog.compute_alerts([{"component": "weekly_analysis",
                           "last_success_at": (NOW - timedelta(days=60)).isoformat()}], NOW)
    assert not any("weekly_analysis" in a for a in missing + old)


def test_on_demand_component_alerts_on_last_run_failed(m):
    row = {"component": "weekly_analysis",
           "last_success_at": (NOW - timedelta(days=10)).isoformat(),
           "last_failure_at": (NOW - timedelta(hours=1)).isoformat(),
           "last_error": "boom"}
    assert any("weekly_analysis" in a and "fallito" in a for a in m.watchdog.compute_alerts([row], NOW))
    row["last_success_at"] = NOW.isoformat()
    assert not any("weekly_analysis" in a for a in m.watchdog.compute_alerts([row], NOW))


def test_proactive_gate_is_catch_up_not_exact_hour(m):
    """I cron arrivano alle 20-22 Rome: il gate "ora == 18" li skippava tutti."""
    wf = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "proactive-check-in.yml"
    text = wf.read_text(encoding="utf-8")
    assert '-lt 18' in text
    assert '!= "18"' not in text


# --- 5. Belief confutata a mano -----------------------------------------------

class _FakeTable:
    """Query builder minimale: filtri eq/neq su colonne presenti nella riga
    (athlete_id, aggiunto da aq(), viene ignorato: le righe finte non ce l'hanno)."""

    def __init__(self, db, name):
        self.db, self.name, self.filters, self.patch = db, name, [], None

    def select(self, *a, **k): return self
    def eq(self, col, val): self.filters.append((col, lambda v, x=val: v == x)); return self
    def neq(self, col, val): self.filters.append((col, lambda v, x=val: v != x)); return self
    def update(self, patch): self.patch = patch; return self
    def insert(self, row): self.db.setdefault(self.name, []).append(row); return self

    def execute(self):
        rows = [r for r in self.db.get(self.name, [])
                if all(col not in r or ok(r[col]) for col, ok in self.filters)]
        if self.patch is not None:
            for r in rows:
                r.update(self.patch)
        return SimpleNamespace(data=rows)


def test_manually_refuted_belief_stays_flagged(m, monkeypatch):
    common = {"status": "validated_belief", "confidence": 0.8, "evidence_n": 15, "prescription": None}
    db = {
        "athletes": [{"id": "a1"}],
        "beliefs": [
            {"id": "refuted", "belief_text": "Superamento zone in sessioni recupero", "flagged": True, **common},
            {"id": "old_bug", "belief_text": "HRV più alta dopo giorni di riposo", "flagged": True, **common},
        ],
        "beliefs_history": [{"belief_id": "refuted", "change_type": "refuted"}],
    }
    fake = SimpleNamespace(table=lambda name: _FakeTable(db, name))
    monkeypatch.setattr(m.beliefs, "get_supabase", lambda: fake)
    monkeypatch.setattr(m.supabase_client, "get_supabase", lambda: fake)
    monkeypatch.setattr(m.athlete, "legacy_single_athlete_mode", lambda: True)  # come in prod

    assert m.beliefs.reconcile_flagged_beliefs() == 1
    by_id = {b["id"]: b for b in db["beliefs"]}
    assert by_id["refuted"]["flagged"] is True      # decisione del coach: resta
    assert by_id["old_bug"]["flagged"] is False     # flag da vecchio bug: sbloccata


# --- 6. Nuoto: pace vs CSS ------------------------------------------------------

def test_swim_css_context_uses_per_100m_pace_written_by_ingest(m):
    """L'ingest Garmin scrive per il nuoto solo avg_pace_s_per_100m."""
    ctx = m.psa._swim_pace_context({"avg_pace_s_per_100m": 77.0, "avg_pace_s_per_km": None}, 80)
    assert "CSS: 1:20/100m" in ctx and "Pace media: 1:17/100m" in ctx
    assert "non disponibile" not in ctx
    slow = m.psa._swim_pace_context({"avg_pace_s_per_100m": 100.0}, 80)
    assert "più LENTO del CSS" in slow
