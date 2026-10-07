"""Scheduler dei test fitness: rispetta il retest del mesociclo e i rifiuti.

Il 28/09 e il 05/10/2026 (domenica notte) lo scheduler ha proposto CSS,
soglia corsa e soglia bici in tre giorni consecutivi, nel mezzo del blocco
"Ricostruzione post-stop cardiologico" che prevede il retest in settimana 4.
"""
from __future__ import annotations

import importlib
import sys
from datetime import date
from types import SimpleNamespace

import pytest

TODAY = date(2026, 10, 4)  # domenica, come il cron di pattern-extraction

MESO_RICOSTRUZIONE = {
    "id": "m1", "name": "Ricostruzione post-stop cardiologico",
    "start_date": "2026-09-29", "end_date": "2026-10-25",
    "notes": "Tutto Z1-Z2 fino a S3; allunghi da S2. S4 scarico + retest zone "
             "(CSS, soglia corsa, LTHR bici) — valori attuali di giugno non più rappresentativi.",
    "progression_plan": {"week4": {"dates": "19/10-25/10", "notes": "Scarico + retest zone a fine settimana."}},
}


class _Q:
    def __init__(self, rows):
        self.rows, self.preds = list(rows), []

    def select(self, *a): return self
    def eq(self, k, v): self.preds.append(lambda r: r.get(k) == v); return self
    def gte(self, k, v): self.preds.append(lambda r: r.get(k) is not None and str(r[k]) >= v); return self
    def lte(self, k, v): self.preds.append(lambda r: r.get(k) is not None and str(r[k]) <= v); return self
    def in_(self, k, vs): self.preds.append(lambda r: r.get(k) in vs); return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def execute(self):
        return SimpleNamespace(data=[r for r in self.rows if all(p(r) for p in self.preds)])


def _is_project(name: str) -> bool:
    return name.split(".")[0] in ("coach", "scripts")


@pytest.fixture
def run(monkeypatch):
    saved = {k: v for k, v in sys.modules.items() if _is_project(k)}
    for k in saved:
        del sys.modules[k]
    try:
        ts = importlib.import_module("coach.coaching.test_scheduler")
        mod = importlib.import_module("coach.coaching.modulation")
        athlete = importlib.import_module("coach.utils.athlete")
        sbmod = importlib.import_module("coach.utils.supabase_client")
        monkeypatch.setattr(athlete, "legacy_single_athlete_mode", lambda: True)

        def _run(db: dict) -> list:
            client = SimpleNamespace(table=lambda name: _Q(db.get(name, [])))
            monkeypatch.setattr(sbmod, "get_supabase", lambda: client)
            monkeypatch.setattr(ts, "get_supabase", lambda: client)
            proposals = []
            monkeypatch.setattr(mod, "propose_modulation",
                                lambda **kw: proposals.append(kw) or f"mod{len(proposals)}")
            ts.schedule_overdue_tests(today=TODAY)
            return proposals

        yield _run
    finally:
        for k in [k for k in sys.modules if _is_project(k)]:
            del sys.modules[k]
        sys.modules.update(saved)


OLD_ZONES = [
    {"discipline": "swim", "valid_from": "2026-06-04"},
    {"discipline": "run", "valid_from": "2026-06-21"},
    {"discipline": "bike", "valid_from": "2026-05-26"},
]


def test_no_proposals_when_mesocycle_plans_the_retest(run):
    proposals = run({"physiology_zones": OLD_ZONES, "mesocycles": [MESO_RICOSTRUZIONE]})
    assert proposals == []


def test_without_mesocycle_tests_are_spaced_out(run):
    proposals = run({"physiology_zones": OLD_ZONES})
    dates = sorted(date.fromisoformat(p["proposed_changes"][0]["date"]) for p in proposals)
    assert len(dates) == 3
    assert all((b - a).days >= 2 for a, b in zip(dates, dates[1:])), dates


def test_rejected_test_is_not_proposed_again_for_three_weeks(run):
    rejected = {
        "source": "test_scheduler", "status": "rejected", "proposed_at": "2026-09-28T00:10:00+00:00",
        "proposed_changes": [{"date": "2026-10-06", "sport": "swim"}],
    }
    proposals = run({"physiology_zones": OLD_ZONES, "plan_modulations": [rejected]})
    sports = {p["proposed_changes"][0]["sport"] for p in proposals}
    assert "swim" not in sports
    assert sports == {"run", "bike"}


def test_mesocycle_without_retest_does_not_block(run):
    meso = {**MESO_RICOSTRUZIONE, "notes": "Base aerobica.", "progression_plan": {"week1": {"notes": "Z2"}}}
    proposals = run({"physiology_zones": OLD_ZONES, "mesocycles": [meso]})
    assert len(proposals) == 3
