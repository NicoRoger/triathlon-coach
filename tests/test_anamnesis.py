"""WP1 — scripts/generate_anamnesis.py: vista generata dal DB.

Verifica che build_anamnesis produca le sezioni attese da dati fake e che
generate_anamnesis sia idempotente (stesso contenuto → nessuna riscrittura).

NB: niente stub in sys.modules (questo file è alfabeticamente primo nella
suite: stub dei package roots rompono la collection degli altri test).
Si monkeypatchano gli attributi dei moduli REALI — il generatore importa
get_supabase/today_rome dentro le funzioni, quindi il patch a runtime regge.
"""
from __future__ import annotations

import types
from datetime import date

import pytest

# ---------------------------------------------------------------------------
# Fake Supabase: risponde per tabella, ignora i filtri (dataset già filtrato)
# ---------------------------------------------------------------------------
TABLES = {
    "physiology_zones": [
        {"discipline": "run", "valid_from": "2026-06-21", "valid_to": None,
         "ftp_w": None, "threshold_pace_s_per_km": 260, "css_pace_s_per_100m": None,
         "lthr": 172, "hr_max": 194, "method": "manual_heat_corrected"},
        {"discipline": "swim", "valid_from": "2026-06-04", "valid_to": None,
         "ftp_w": None, "threshold_pace_s_per_km": None, "css_pace_s_per_100m": 80,
         "lthr": None, "hr_max": None, "method": "CSS Test 400-200. Dettagli lunghi."},
        {"discipline": "run", "valid_from": "2026-05-30", "valid_to": "2026-06-21",
         "ftp_w": None, "threshold_pace_s_per_km": 275, "css_pace_s_per_100m": None,
         "lthr": 183, "hr_max": None, "method": "threshold_run_30min"},
    ],
    "active_constraints": [
        {"type": "injury", "discipline": "swim", "severity": "low",
         "symptom_status": "recovering", "note": "via libera fisio",
         "description": "spalla dx: carichi liberi", "created_at": "2026-06-08", "resolved_at": None},
    ],
    "mesocycles": [
        {"name": "Specific — Lavarone", "phase": "specific",
         "start_date": "2026-06-30", "end_date": "2026-08-03",
         "progression_plan": {"weekly_tss_target": {"week1": 340, "week2": 390}}},
    ],
    "daily_metrics": [
        {"date": "2026-07-07", "ctl": 39.6, "atl": 41.6, "tsb": -2.0,
         "readiness_score": 75, "readiness_label": "ready"},
    ],
    "races": [
        {"name": "Lavarone Cross Sprint", "race_date": "2026-08-29",
         "priority": "A", "location": "Lavarone"},
    ],
    "beliefs": [
        {"belief_text": "Tendenza a spingere oltre Z2", "status": "weak_belief",
         "confidence": 0.72, "evidence_n": 6},
    ],
    "daily_wellness": [
        {"resting_hr": 47, "hrv_rmssd": 85},
        {"resting_hr": 44, "hrv_rmssd": 102},
        {"resting_hr": 50, "hrv_rmssd": 67},
    ],
}


class _Q:
    def __init__(self, rows):
        self._rows = rows

    def __getattr__(self, _name):
        # select/eq/gte/lte/is_/neq/in_/order/limit → chainable no-op
        return lambda *a, **k: self

    def execute(self):
        return types.SimpleNamespace(data=self._rows)


class _SB:
    def table(self, name):
        return _Q(TABLES.get(name, []))


@pytest.fixture()
def gen(monkeypatch):
    import coach.utils.supabase_client as sbmod
    import coach.utils.dt as dtmod
    from scripts import generate_anamnesis as gen_mod

    monkeypatch.setattr(sbmod, "get_supabase", lambda: _SB())
    monkeypatch.setattr(dtmod, "today_rome", lambda: date(2026, 7, 7))
    return gen_mod


def test_build_anamnesis_sections(gen):
    content = gen.build_anamnesis()
    # Zone correnti: solo le righe attive (valid_to null), non la storica run 05-30
    assert "LTHR 172 bpm" in content
    assert "CSS 1:20/100m" in content
    assert "manual_heat_corrected" in content
    # Vincoli con stato tradotto
    assert "in recupero" in content and "spalla dx: carichi liberi" in content
    # Mesociclo: 2026-07-07 è settimana 2 di 5
    assert "settimana 2 di 5" in content
    assert "weekly_tss_target: 390" in content
    # PMC + gara + belief + baseline
    assert "CTL 39.6" in content
    assert "Lavarone Cross Sprint" in content
    assert "weak_belief n=6" in content
    assert "HR riposo: 47" in content
    # Storico test include anche la riga chiusa
    assert "2026-05-30" in content
    # Header anti-modifica
    assert "GENERATO AUTOMATICAMENTE" in content


def test_generate_anamnesis_idempotent(gen, tmp_path, monkeypatch):
    target = tmp_path / "athlete_anamnesis.md"
    monkeypatch.setattr(gen, "ANAMNESIS_PATH", target)
    assert gen.generate_anamnesis() is True   # prima scrittura
    assert gen.generate_anamnesis() is False  # contenuto identico → no-op
    assert "Anamnesi Atleta" in target.read_text(encoding="utf-8")
