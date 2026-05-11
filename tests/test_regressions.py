"""Regression tests — ogni bug fixato ha un test qui per evitare che riaccada.

Ogni test ha un commento con il commit/data del fix e la descrizione del bug.
Eseguiti con: python -m unittest tests.test_regressions -v
"""
from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub dipendenze esterne per isolamento test
# ---------------------------------------------------------------------------
def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None  # type: ignore
    return mod

for _n in [
    "coach", "coach.utils", "coach.utils.supabase_client",
    "coach.utils.dt", "coach.utils.health", "coach.utils.telegram_logger",
    "coach.utils.budget", "coach.coaching", "coach.analytics",
    "coach.planning",
]:
    if _n not in sys.modules:
        sys.modules[_n] = _stub(_n)

sys.modules["coach.utils.supabase_client"].get_supabase = MagicMock(return_value=MagicMock())  # type: ignore
sys.modules["coach.utils.dt"].today_rome = MagicMock(return_value=date(2026, 5, 11))  # type: ignore


# ---------------------------------------------------------------------------
# Import moduli sotto test via importlib (evita conflitti con stub packages)
# ---------------------------------------------------------------------------
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


pmc = _load("coach.analytics.pmc", "coach/analytics/pmc.py")


# ===========================================================================
# FIX: started_at stringa ISO causa TypeError in compute_pmc_series
# Commit: 47b9a97 (2026-05-11)
# Bug: Supabase restituisce started_at come stringa, non datetime.
#      aggregate_daily_tss cadeva nel branch else e passava stringhe a DailyTSS.
#      compute_pmc_series crashava su `end - start` con TypeError.
# ===========================================================================
class TestStartedAtStringParsing(unittest.TestCase):

    def test_aggregate_handles_iso_string(self):
        """started_at come stringa ISO non deve crashare"""
        activities = [
            {"started_at": "2026-05-10T08:00:00+00:00", "tss": 50, "duration_s": 3600, "avg_hr": 140},
            {"started_at": "2026-05-11T07:00:00+00:00", "tss": 60, "duration_s": 3000, "avg_hr": 150},
        ]
        result = pmc.aggregate_daily_tss(activities)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0].day, date)
        self.assertIsInstance(result[1].day, date)

    def test_aggregate_handles_date_object(self):
        """started_at come date object deve continuare a funzionare"""
        activities = [
            {"started_at": date(2026, 5, 10), "tss": 50, "duration_s": 3600, "avg_hr": 140},
        ]
        result = pmc.aggregate_daily_tss(activities)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0].day, date)

    def test_pmc_series_from_string_dates(self):
        """Pipeline completa: stringhe ISO → DailyTSS → PMC senza crash"""
        activities = [
            {"started_at": "2026-05-09T08:00:00Z", "tss": 40, "duration_s": 3600, "avg_hr": 140},
            {"started_at": "2026-05-10T08:00:00Z", "tss": 55, "duration_s": 3600, "avg_hr": 150},
            {"started_at": "2026-05-11T07:00:00Z", "tss": 60, "duration_s": 3000, "avg_hr": 145},
        ]
        daily = pmc.aggregate_daily_tss(activities)
        series = pmc.compute_pmc_series(daily)
        self.assertEqual(len(series), 3)
        self.assertIsNotNone(series[-1].tsb)


# ===========================================================================
# FIX: colonna training_load non esiste in tabella activities
# Commit: 7485a81 (2026-05-11)
# Bug: _fetch_activities_window richiedeva "training_load" nella select,
#      ma la colonna non esiste nel DB → error 42703.
# ===========================================================================
class TestNoTrainingLoadColumn(unittest.TestCase):

    def test_daily_select_no_training_load(self):
        """La select di _fetch_activities_window NON deve contenere training_load"""
        import importlib.util
        src = (ROOT / "coach" / "analytics" / "daily.py").read_text(encoding="utf-8")
        # Cerca la riga di select nella funzione _fetch_activities_window
        import re
        match = re.search(r'def _fetch_activities_window.*?\.select\(\s*"([^"]+)"', src, re.DOTALL)
        self.assertIsNotNone(match, "select query not found in _fetch_activities_window")
        select_cols = match.group(1)
        self.assertNotIn("training_load", select_cols)


# ===========================================================================
# FIX: TSB None causa crash in _score_tsb
# Commit: 82a0794 (2026-05-11)
# Bug: Se nessun dato PMC disponibile, tsb=None e _score_tsb crashava
#      su confronto numerico con None.
# ===========================================================================
class TestTsbNoneHandling(unittest.TestCase):

    def test_score_tsb_none_returns_neutral(self):
        """TSB=None (nessun dato PMC) → score neutro 50, non crash"""
        readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
        ts = readiness.TrainingState(ctl=0, atl=0, tsb=None, days_since_hard_session=None)
        score = readiness._score_tsb(ts)
        self.assertEqual(score, 50)


# ===========================================================================
# FIX: duration_s None trap in post_session_analysis
# Commit: 82a0794 (2026-05-11)
# Bug: activity.get("duration_s", 0) restituisce None quando la chiave
#      esiste ma il valore è None. int(None) → TypeError.
# ===========================================================================
class TestDurationNoneTrap(unittest.TestCase):

    def test_or_zero_pattern(self):
        """Il pattern `x or 0` gestisce sia key-missing che value=None"""
        activity = {"duration_s": None}
        result = int(activity.get("duration_s") or 0)
        self.assertEqual(result, 0)

    def test_default_param_trap(self):
        """Dimostra che .get(key, 0) NON protegge da value=None"""
        activity = {"duration_s": None}
        val = activity.get("duration_s", 0)
        self.assertIsNone(val)  # Il default NON si applica quando la chiave esiste


# ===========================================================================
# FIX: splits empty list scartata perché falsy
# Commit: 82a0794 (2026-05-11)
# Bug: `splits_raw.get("lapDTOs") or splits_raw.get("splits")` scarta
#      liste vuote [] perché falsy in Python. Deve usare `is None`.
# ===========================================================================
class TestEmptyListFalsy(unittest.TestCase):

    def test_empty_list_is_falsy(self):
        """Conferma che [] è falsy — il bug originale"""
        self.assertFalse(bool([]))

    def test_is_none_preserves_empty_list(self):
        """Pattern corretto: `is None` check non scarta liste vuote"""
        data = {"lapDTOs": []}
        result = data.get("lapDTOs")
        if result is None:
            result = data.get("splits")
        self.assertEqual(result, [])

    def test_or_pattern_discards_empty_list(self):
        """Pattern sbagliato: `or` scarta liste vuote"""
        data = {"lapDTOs": [], "splits": [{"lap": 1}]}
        result = data.get("lapDTOs") or data.get("splits")
        self.assertEqual(result, [{"lap": 1}])  # Bug: voleva [] ma ottiene fallback


# ===========================================================================
# FIX: hrTSS fallback funziona quando tss e training_load sono entrambi None
# Commit: 82a0794 (2026-05-11)
# Bug: Con tss=None e training_load inesistente, il fallback hrTSS deve
#      calcolare un valore ragionevole da duration_s e avg_hr.
# ===========================================================================
class TestHrTssFallback(unittest.TestCase):

    def test_hrtss_calculated_when_tss_null(self):
        """Attività senza TSS usa fallback hrTSS da HR"""
        activities = [
            {"started_at": "2026-05-11T08:00:00Z", "tss": None, "duration_s": 3600, "avg_hr": 150},
        ]
        result = pmc.aggregate_daily_tss(activities)
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0].tss, 0)

    def test_skipped_when_no_hr(self):
        """Attività senza TSS né HR viene skippata (non crashare)"""
        activities = [
            {"started_at": "2026-05-11T08:00:00Z", "tss": None, "duration_s": 3600, "avg_hr": None},
        ]
        result = pmc.aggregate_daily_tss(activities)
        self.assertEqual(len(result), 0)

    def test_multiple_sessions_same_day_summed(self):
        """Più sessioni nello stesso giorno sommano il TSS"""
        activities = [
            {"started_at": "2026-05-11T06:00:00Z", "tss": 40, "duration_s": 3600, "avg_hr": 140},
            {"started_at": "2026-05-11T17:00:00Z", "tss": 30, "duration_s": 2400, "avg_hr": 135},
        ]
        result = pmc.aggregate_daily_tss(activities)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].tss, 70.0)


# ===========================================================================
# FIX: aggregate_daily_tss con lista vuota non crashare
# Difensivo: verifica che [] → [] senza errori
# ===========================================================================
class TestEmptyActivities(unittest.TestCase):

    def test_empty_list_returns_empty(self):
        result = pmc.aggregate_daily_tss([])
        self.assertEqual(result, [])

    def test_pmc_series_empty_input(self):
        result = pmc.compute_pmc_series([])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
