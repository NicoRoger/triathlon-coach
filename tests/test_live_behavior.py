"""Test di comportamento live — Plan 04-02.

Blocca regressioni su:
  VERIFY-04: routing LLM session_analysis → gemini-2.5-flash + guard E7 (testo vuoto)
  VERIFY-05/DEPLOY-04: flusso accepted→applied + upsert planned_sessions

Esecuzione: PYTHONPATH=. python -m pytest tests/test_live_behavior.py -v
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helper: carica un modulo da path relativo (stesso pattern di test_audit_resilience)
# ---------------------------------------------------------------------------
def _load(mod_name: str, rel_path: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ===========================================================================
# Test 1 (VERIFY-04 routing): session_analysis → provider gemini → model gemini-2.5-flash
# ===========================================================================
def test_verify04_session_analysis_routes_to_gemini():
    """PURPOSE_ROUTING mappa 'session_analysis' su provider 'gemini'.
    GeminiClient.MODEL deve essere 'gemini-2.5-flash'.

    Non effettua chiamate di rete: ispeziona le costanti statiche in llm_client.py.
    """
    from coach.utils.llm_client import PURPOSE_ROUTING, GeminiClient

    # Il purpose deve essere routed su Gemini
    provider = PURPOSE_ROUTING.get("session_analysis")
    assert provider == "gemini", (
        f"Expected 'gemini', got '{provider}'. "
        "session_analysis deve usare Gemini (tier free, alto volume)."
    )

    # Il modello Gemini deve essere gemini-2.5-flash
    assert "gemini-2.5-flash" in GeminiClient.MODEL, (
        f"GeminiClient.MODEL={GeminiClient.MODEL!r} non contiene 'gemini-2.5-flash'."
    )


# ===========================================================================
# Test 2 (VERIFY-04 guard E7): testo vuoto → nessun insert in session_analyses
# ===========================================================================

class _EmptyTextFakeClient:
    """Fake client LLM che ritorna sempre testo vuoto (simula Gemini safety-block)."""

    def call(self, purpose, system, messages, **kwargs):
        return {"text": "", "model": "gemini-2.5-flash", "cost_usd": 0.0}


class _TrackingFakeQuery:
    """Fake query Supabase che traccia insert su session_analyses."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.inserts: list[dict] = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        filtered = [r for r in self._rows if r.get(col) == val]
        clone = _TrackingFakeQuery(filtered)
        clone.inserts = self.inserts
        return clone

    def neq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def gt(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def insert(self, data, **k):
        self.inserts.append(data)
        return self

    def upsert(self, data, **k):
        return self

    def update(self, data, **k):
        return self

    def execute(self):
        return types.SimpleNamespace(data=list(self._rows))


class _TrackingFakeSB:
    """Fake Supabase che espone session_analyses con insert tracking."""

    def __init__(self):
        self._session_analyses_query = _TrackingFakeQuery([])
        self._activity_row = {
            "external_id": "act_test_001",
            "sport": "run",
            "started_at": "2026-06-05T08:00:00Z",
            "duration_s": 3600,
            "distance_m": 10000,
            "avg_hr": 145,
            "max_hr": 165,
            "avg_pace_s_per_km": 360,
            "avg_power_w": None,
            "tss": 55,
            "splits": None,
            "hr_zones_s": None,
        }

    def table(self, name: str) -> _TrackingFakeQuery:
        if name == "session_analyses":
            return self._session_analyses_query
        if name == "activities":
            # Ritorna l'attività per external_id lookup, vuoto per il check duplicati
            return _TrackingFakeQuery([self._activity_row])
        # Tutte le altre tabelle: vuote
        return _TrackingFakeQuery([])


def test_verify04_empty_llm_text_skips_insert(monkeypatch):
    """Guard E7: se il client LLM ritorna testo vuoto, analyze_session NON deve
    inserire nulla in session_analyses (né inviare Telegram).

    Usa un fake Supabase e un fake LLM client che ritorna ''.
    """
    # Stub dei moduli con side-effect (Telegram, budget, health, dt)
    for mod_name in [
        "coach.utils.health",
        "coach.planning.briefing",
        "coach.utils.telegram_logger",
        "coach.utils.budget",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    # BudgetExceededError deve esistere nel modulo budget
    if not hasattr(sys.modules["coach.utils.budget"], "BudgetExceededError"):
        class _BE(Exception):
            pass
        sys.modules["coach.utils.budget"].BudgetExceededError = _BE  # type: ignore

    # dt reale (serve to_rome_date)
    if "coach.utils.dt" not in sys.modules:
        _load("coach.utils.dt", "coach/utils/dt.py")

    # Fake Supabase
    fake_sb = _TrackingFakeSB()

    # Stub get_supabase e get_client_for_purpose
    monkeypatch.setattr("coach.utils.supabase_client.get_supabase", lambda: fake_sb)

    # Carica post_session_analysis con dipendenze stubbed
    for n in ["coach.utils.supabase_client"]:
        sys.modules[n].get_supabase = lambda: fake_sb  # type: ignore

    # Stub il modulo llm_client per iniettare il fake client
    fake_llm_mod = types.ModuleType("coach.utils.llm_client")
    empty_client = _EmptyTextFakeClient()
    fake_llm_mod.get_client_for_purpose = lambda purpose: empty_client  # type: ignore
    monkeypatch.setitem(sys.modules, "coach.utils.llm_client", fake_llm_mod)

    # Stub Telegram per non fare chiamate HTTP
    sys.modules["coach.planning.briefing"].send_to_telegram = lambda *a, **k: None  # type: ignore
    sys.modules["coach.utils.telegram_logger"].send_and_log_message = lambda *a, **k: None  # type: ignore

    # Carica il modulo (ricarica fresca per prendere gli stub)
    if "coach.coaching.post_session_analysis" in sys.modules:
        del sys.modules["coach.coaching.post_session_analysis"]
    psa = _load(
        "coach.coaching.post_session_analysis",
        "coach/coaching/post_session_analysis.py",
    )

    result = psa.analyze_session("act_test_001")

    # Deve ritornare None (skip)
    assert result is None, (
        "analyze_session deve ritornare None quando il testo LLM è vuoto"
    )
    # Non deve aver inserito nulla in session_analyses
    assert len(fake_sb._session_analyses_query.inserts) == 0, (
        f"Nessun insert atteso su session_analyses con testo vuoto, "
        f"trovati: {fake_sb._session_analyses_query.inserts}"
    )


# ===========================================================================
# Test 3 (VERIFY-05/DEPLOY-04): accepted → applied + upsert planned_sessions
# ===========================================================================

class _AcceptedModFakeSB:
    """Fake Supabase con una modulazione status='accepted' e tabella planned_sessions."""

    def __init__(self, mod: dict):
        self._mod = mod          # riga in plan_modulations
        self.upserts: list[dict] = []
        self.mod_updates: list[dict] = []

    def table(self, name: str):
        return _AcceptedModFakeQuery(self, name)


class _AcceptedModFakeQuery:
    """Fake query per _AcceptedModFakeSB."""

    def __init__(self, parent: "_AcceptedModFakeSB", table_name: str):
        self._p = parent
        self._table = table_name
        self._filter_id: str | None = None
        self._filter_status: str | None = None

    def select(self, *a, **k):
        return self

    def eq(self, col: str, val: str):
        clone = _AcceptedModFakeQuery(self._p, self._table)
        clone._filter_id = self._filter_id
        clone._filter_status = self._filter_status
        if col == "id":
            clone._filter_id = val
        if col == "status":
            clone._filter_status = val
        return clone

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        mod = self._p._mod
        if self._table == "plan_modulations":
            if self._filter_id is not None:
                rows = [mod] if mod.get("id") == self._filter_id else []
            elif self._filter_status is not None:
                rows = [mod] if mod.get("status") == self._filter_status else []
            else:
                rows = [mod]
            return types.SimpleNamespace(data=rows)
        # planned_sessions: sempre vuoto (nessuna sessione pre-esistente)
        return types.SimpleNamespace(data=[])

    def insert(self, data, **k):
        return self

    def update(self, data, **k):
        # Applica l'aggiornamento alla riga mod in-place (simula comportamento DB)
        if self._table == "plan_modulations":
            self._p._mod.update(data)
            self._p.mod_updates.append(dict(data))
        return self

    def upsert(self, data, **k):
        if self._table == "planned_sessions":
            self._p.upserts.append(dict(data))
        return self


def test_verify05_accepted_modulation_applies_and_updates_planned_sessions():
    """VERIFY-05/DEPLOY-04: una riga plan_modulations con status='accepted'
    e proposed_changes valido deve:
      1. Transire a status='applied' via apply_accepted_modulations()
      2. Produrre almeno un upsert su planned_sessions
      3. Il summary deve riportare {"applied": 1, ...}

    Non effettua chiamate di rete: usa fake Supabase in-memory.
    """
    mod = {
        "id": "mod_live_test_001",
        "status": "accepted",
        "expires_at": None,
        "proposed_changes": [
            {
                "date": "2026-06-10",
                "sport": "run",
                "old_description": "Z2 lungo 70min",
                "new": {
                    "session_type": "recovery",
                    "duration_s": 3600,
                    "description": "Z2 recupero — modulazione HRV",
                },
            }
        ],
    }
    fake_sb = _AcceptedModFakeSB(mod)

    # Stub dipendenze di modulation.py
    for mod_name in ["coach.utils.supabase_client", "coach.utils.budget"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: fake_sb  # type: ignore

    if not hasattr(sys.modules["coach.utils.budget"], "BudgetExceededError"):
        class _BE(Exception):
            pass
        sys.modules["coach.utils.budget"].BudgetExceededError = _BE  # type: ignore

    # Carica modulation fresco
    if "coach.coaching.modulation" in sys.modules:
        del sys.modules["coach.coaching.modulation"]
    mt = _load("coach.coaching.modulation", "coach/coaching/modulation.py")

    summary = mt.apply_accepted_modulations()

    # 1. Summary deve riportare applied=1
    assert summary["applied"] == 1, (
        f"Expected applied=1, got: {summary}"
    )

    # 2. La riga plan_modulations deve essere 'applied'
    assert mod["status"] == "applied", (
        f"plan_modulations.status deve essere 'applied' dopo apply_accepted, "
        f"trovato: {mod['status']!r}"
    )

    # 3. Deve esserci almeno un upsert su planned_sessions
    assert len(fake_sb.upserts) >= 1, (
        "apply_accepted_modulations deve produrre almeno un upsert su planned_sessions"
    )

    # 4. Il payload dell'upsert deve riflettere i nuovi valori
    up = fake_sb.upserts[0]
    assert up["planned_date"] == "2026-06-10"
    assert up["sport"] == "run"
    assert up["session_type"] == "recovery"
    assert up["duration_s"] == 3600
