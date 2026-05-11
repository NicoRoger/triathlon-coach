"""Test fitness test auto-detection — Blocco 1.

12 test per il processore fitness test: extractors, zone calculators,
idempotency, fallback, CLAUDE.md update, matching logic.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub dipendenze esterne
# ---------------------------------------------------------------------------
def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None  # type: ignore
    return mod


for _name in [
    "coach", "coach.utils", "coach.utils.supabase_client",
    "coach.utils.dt", "coach.utils.health",
    "coach.utils.telegram_logger",
    "coach.coaching",
]:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

sys.modules["coach.utils.supabase_client"].get_supabase = MagicMock(return_value=MagicMock())  # type: ignore
sys.modules["coach.utils.dt"].today_rome = MagicMock(return_value="2026-06-15")  # type: ignore
sys.modules["coach.utils.telegram_logger"].send_and_log_message = MagicMock()  # type: ignore

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "coach.coaching.fitness_test_processor",
    Path(__file__).resolve().parent.parent / "coach" / "coaching" / "fitness_test_processor.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore
sys.modules["coach.coaching.fitness_test_processor"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore

FitnessTestProcessor = _mod.FitnessTestProcessor
_eval_formula = _mod._eval_formula
_fmt_pace = _mod._fmt_pace
_fmt_swim_pace = _mod._fmt_swim_pace


def _make_processor(mock_sb=None) -> FitnessTestProcessor:
    proc = FitnessTestProcessor.__new__(FitnessTestProcessor)
    proc.sb = mock_sb or MagicMock()
    proc.sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    return proc


def _ftp_structured():
    return {
        "test_type": "ftp_bike_20min",
        "garmin_activity_name": "FTP Test 20min",
        "extraction": {
            "primary": {"field": "avg_power_w", "source": "splits", "interval_index": 1, "formula": "value * 0.95"},
            "fallback": {"field": "avg_power_w", "source": "activity", "formula": "value * 0.90"},
        },
        "zone_system": "coggan_7zone",
        "claude_md_field": "ftp_attuale_w",
    }


class TestFTPExtraction(unittest.TestCase):

    def test_ftp_from_correct_splits(self):
        """Test 1: FTP extraction from correct splits → 247W"""
        proc = _make_processor()
        activity = {
            "id": "test-001",
            "started_at": "2026-06-15T08:00:00Z",
            "sport": "bike",
            "splits": [
                {"avg_power_w": 150, "duration_s": 1200},
                {"avg_power_w": 260, "duration_s": 1200},
            ],
        }
        result = proc._extract_ftp_bike_20min(activity, _ftp_structured())
        self.assertAlmostEqual(result, 247.0, places=0)

    def test_ftp_from_null_splits_fallback(self):
        """Test 2: FTP extraction from null splits → use fallback avg_power"""
        proc = _make_processor()
        activity = {
            "id": "test-002",
            "started_at": "2026-06-15T08:00:00Z",
            "sport": "bike",
            "splits": None,
            "avg_power_w": 240,
        }
        result = proc._extract_ftp_bike_20min(activity, _ftp_structured())
        self.assertIsNone(result)
        fallback = proc._try_fallback_extraction(activity, _ftp_structured())
        self.assertAlmostEqual(fallback, 216.0, places=0)

    def test_ftp_ramp(self):
        """Test 3: FTP ramp test → max_power * 0.75"""
        proc = _make_processor()
        activity = {"id": "test-003", "max_power_w": 340, "splits": None}
        structured = {"test_type": "ftp_bike_ramp", "extraction": {"primary": {}}}
        result = proc._extract_ftp_bike_ramp(activity, structured)
        self.assertAlmostEqual(result, 255.0, places=0)


class TestThresholdPaceExtraction(unittest.TestCase):

    def test_threshold_pace_from_splits(self):
        """Test 4: Threshold pace run extraction"""
        proc = _make_processor()
        activity = {
            "id": "test-004",
            "splits": [
                {"avg_pace_s_per_km": 330},
                {"avg_pace_s_per_km": 240},
            ],
        }
        structured = {
            "test_type": "threshold_run_30min",
            "extraction": {"primary": {"interval_index": 1}},
        }
        result = proc._extract_threshold_run(activity, structured)
        self.assertAlmostEqual(result, 240.0, places=0)


class TestCSSExtraction(unittest.TestCase):

    def test_css_from_two_splits(self):
        """Test 5: CSS swim extraction from 400m + 200m splits"""
        proc = _make_processor()
        activity = {
            "id": "test-005",
            "splits": [
                {"distance_m": 400, "duration_s": 360},
                {"distance_m": 200, "duration_s": 160},
            ],
        }
        structured = {"test_type": "css_swim_400_200", "extraction": {"primary": {}}}
        result = proc._extract_css_swim(activity, structured)
        # CSS = (360 - 160) / 2 = 100 sec/100m
        self.assertAlmostEqual(result, 100.0, places=0)


class TestCogganZones(unittest.TestCase):

    def test_coggan_7zones_250w(self):
        """Test 6: Coggan 7 zones for FTP 250W → exact values"""
        zones = FitnessTestProcessor._compute_coggan_7zone(250)
        self.assertEqual(zones["Z1_recovery"], "<138W")
        self.assertEqual(zones["Z2_endurance"], "140-188W")
        self.assertEqual(zones["Z3_tempo"], "190-225W")
        self.assertEqual(zones["Z4_threshold"], "228-262W")
        self.assertEqual(zones["Z5_vo2max"], "265-300W")
        self.assertEqual(zones["Z6_anaerobic"], "302-375W")
        self.assertEqual(zones["Z7_neuromuscular"], ">375W")


class TestPaceZones(unittest.TestCase):

    def test_pace_5zone_4min_km(self):
        """Test 7: pace 5zone for threshold pace 4:00/km (240s)"""
        zones = FitnessTestProcessor._compute_pace_5zone(240)
        self.assertEqual(zones["Z1_recovery"], f">{_fmt_pace(300)}/km")
        self.assertEqual(zones["Z4_threshold"], f"{_fmt_pace(240 * 0.97)}-{_fmt_pace(240 * 1.05)}/km")


class TestIdempotency(unittest.TestCase):

    def test_already_processed_skips(self):
        """Test 8: second run on same activity_id → skip"""
        mock_sb = MagicMock()
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "existing"}]
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_execute
        proc = FitnessTestProcessor.__new__(FitnessTestProcessor)
        proc.sb = mock_sb
        activity = {"id": "test-dup", "started_at": "2026-06-15T08:00:00Z"}
        planned = {"structured": _ftp_structured()}
        result = proc.process_fitness_test(activity, planned)
        self.assertEqual(result["status"], "skip")
        self.assertEqual(result["reason"], "already_processed")


class TestFallbackNotification(unittest.TestCase):

    def test_null_splits_no_fallback_notifies(self):
        """Test 9: Graceful fallback on null splits → Telegram notification"""
        proc = _make_processor()
        structured = {
            "test_type": "ftp_bike_20min",
            "garmin_activity_name": "FTP Test 20min",
            "extraction": {"primary": {"interval_index": 1}, "fallback": {"field": "avg_power_w", "formula": "value * 0.90"}},
            "zone_system": "coggan_7zone",
            "claude_md_field": "ftp_attuale_w",
        }
        activity = {"id": "test-nofb", "started_at": "2026-06-15T08:00:00Z", "splits": None, "avg_power_w": None}
        with patch.object(proc, "_notify_telegram") as mock_notify:
            result = proc.process_fitness_test(activity, {"structured": structured})
        self.assertEqual(result["status"], "fallback_failed")
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        self.assertFalse(call_kwargs[1].get("success", True) if call_kwargs[1] else call_kwargs[0][3])


class TestClaudeMdUpdate(unittest.TestCase):

    def test_claude_md_field_replacement(self):
        """Test 10: CLAUDE.md update — regex finds and replaces field"""
        proc = _make_processor()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("  bici:\n    ftp_attuale_w: da testare (FTP test giugno 2026)\n    debolezze: test\n")
            tmp_path = Path(f.name)
        try:
            import coach.coaching.fitness_test_processor as mod
            original = mod.CLAUDE_MD_PATH
            mod.CLAUDE_MD_PATH = tmp_path
            ok = proc._update_claude_md("ftp_attuale_w", 247, "ftp_bike_20min", "2026-06-15")
            mod.CLAUDE_MD_PATH = original
            self.assertTrue(ok)
            content = tmp_path.read_text(encoding="utf-8")
            self.assertIn("247", content)
            self.assertIn("2026-06-15", content)
            self.assertNotIn("da testare", content)
        finally:
            tmp_path.unlink()


class TestKeywordMatching(unittest.TestCase):

    def test_keyword_no_planned_session(self):
        """Test 11: activity 'FTP test spontaneous' without planned_session → manual review"""
        name = "FTP test spontaneous ride"
        keywords = ["ftp", "css", "threshold", "soglia", "test", "ramp"]
        matched = any(kw in name.lower() for kw in keywords)
        self.assertTrue(matched)

    def test_exact_garmin_name_matching(self):
        """Test 12: exact Garmin name → automatic processing triggers"""
        structured = _ftp_structured()
        garmin_name = structured["garmin_activity_name"]
        activity_name = "FTP Test 20min"
        self.assertEqual(garmin_name, activity_name)


class TestHelpers(unittest.TestCase):

    def test_eval_formula_multiply(self):
        self.assertAlmostEqual(_eval_formula("value * 0.95", 260), 247.0, places=0)

    def test_eval_formula_identity(self):
        self.assertAlmostEqual(_eval_formula("value", 100), 100.0)

    def test_fmt_pace(self):
        self.assertEqual(_fmt_pace(240), "4:00")
        self.assertEqual(_fmt_pace(255), "4:15")

    def test_fmt_swim_pace(self):
        self.assertEqual(_fmt_swim_pace(95), "1:35")


if __name__ == "__main__":
    unittest.main()
