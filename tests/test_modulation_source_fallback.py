"""Degradazione di `source` quando il CHECK del DB non è ancora stato allargato.

Le migration si applicano a mano sull'editor SQL di Supabase: fra il deploy
del codice e l'esecuzione della migration può passare tempo. In quella
finestra un INSERT con `source='test_scheduler'` fallisce con 23514 e
propaga fino a uccidere l'intero job domenicale — è esattamente quello che è
successo per 4 settimane. Qui si verifica che il fallback regga.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace


def _load_modulation(fake_sb):
    """Carica modulation.py con le dipendenze esterne stubbate."""
    for name in ["coach.utils.supabase_client", "coach.utils.budget"]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: fake_sb  # type: ignore
    if not hasattr(sys.modules["coach.utils.budget"], "BudgetExceededError"):
        class _BudgetExceededError(Exception):
            pass
        sys.modules["coach.utils.budget"].BudgetExceededError = _BudgetExceededError  # type: ignore
    import importlib.util as ilu
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    spec = ilu.spec_from_file_location(
        "modulation_under_test", root / "coach" / "coaching" / "modulation.py"
    )
    mod = ilu.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(mod)  # type: ignore
    return mod


class _RejectingTable:
    """Rifiuta il primo INSERT con l'errore del CHECK, accetta il secondo."""

    def __init__(self, store):
        self.store = store

    def insert(self, record):
        self.store["attempts"].append(record)
        if len(self.store["attempts"]) == 1:
            raise Exception(
                'new row for relation "plan_modulations" violates check '
                'constraint "plan_modulations_source_check"'
            )
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{"id": "new-id"}]))

    def execute(self):  # pragma: no cover - non usato in questo percorso
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, store):
        self.store = store

    def table(self, _name):
        return _RejectingTable(self.store)


def test_source_degrada_e_conserva_la_provenienza():
    store = {"attempts": []}
    mod = _load_modulation(_FakeSB(store))

    res = mod._insert_modulation(
        _FakeSB(store),
        {
            "trigger_event": "fitness_test_due",
            "trigger_data": {"analysis_excerpt": "Test bike scaduto"},
            "proposed_changes": [],
            "status": "proposed",
            "source": "test_scheduler",
        },
    )

    assert res.data == [{"id": "new-id"}]
    assert len(store["attempts"]) == 2, "doveva riprovare una volta sola"

    first, second = store["attempts"]
    assert first["source"] == "test_scheduler"
    # Il retry usa un valore ammesso, ma la provenienza non si perde.
    assert second["source"] == "auto"
    assert second["trigger_data"]["source_detail"] == "test_scheduler"
    assert second["trigger_data"]["analysis_excerpt"] == "Test bike scaduto"


def test_altri_errori_non_vengono_mascherati():
    """Solo il CHECK su `source` attiva il fallback: un errore diverso deve
    propagare, altrimenti si nasconderebbe un guasto reale."""
    class _AlwaysFailing:
        def table(self, _name):
            class _T:
                def insert(self, _r):
                    raise Exception("connection refused")
            return _T()

    mod = _load_modulation(_AlwaysFailing())
    try:
        mod._insert_modulation(_AlwaysFailing(), {"source": "test_scheduler"})
    except Exception as e:
        assert "connection refused" in str(e)
    else:  # pragma: no cover
        raise AssertionError("l'errore non-CHECK doveva propagare")
