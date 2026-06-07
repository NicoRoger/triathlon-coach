"""Test zone nel brief — Plan 04-01.

Task 1 (test 1-4): `derive_zones_for_discipline` come funzione modulo-livello
Task 2 (test 5-8): `_format_session_zones` e integrazione briefing.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub dipendenze esterne per fitness_test_processor
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

# Load fitness_test_processor
_ftp_spec = _ilu.spec_from_file_location(
    "coach.coaching.fitness_test_processor",
    Path(__file__).resolve().parent.parent / "coach" / "coaching" / "fitness_test_processor.py",
)
_ftp_mod = _ilu.module_from_spec(_ftp_spec)  # type: ignore
sys.modules["coach.coaching.fitness_test_processor"] = _ftp_mod
_ftp_spec.loader.exec_module(_ftp_mod)  # type: ignore

derive_zones_for_discipline = _ftp_mod.derive_zones_for_discipline


# ---------------------------------------------------------------------------
# Task 1 — test 1-4: derive_zones_for_discipline
# ---------------------------------------------------------------------------

def test_derive_run_zones_contains_z2_endurance():
    """Test 1: run con threshold 263s/km -> Z2_endurance contiene '/km' e range."""
    result = derive_zones_for_discipline("run", threshold_pace_s_per_km=263)
    assert isinstance(result, dict), "Deve ritornare un dict"
    assert "Z2_endurance" in result, f"Chiave Z2_endurance attesa, trovato: {list(result.keys())}"
    z2 = result["Z2_endurance"]
    assert "/km" in z2, f"Il valore Z2_endurance deve contenere '/km', trovato: {z2!r}"
    # threshold 263 * 1.15 = 302.45s ~ 5:02, threshold * 1.25 = 328.75s ~ 5:28
    assert "5:" in z2, f"Atteso pace intorno a 5min/km, trovato: {z2!r}"


def test_derive_swim_zones_contains_css():
    """Test 2: swim con CSS 80s/100m -> chiave CSS nel dict."""
    result = derive_zones_for_discipline("swim", css_pace_s_per_100m=80)
    assert isinstance(result, dict), "Deve ritornare un dict"
    assert "CSS" in result, f"Chiave CSS attesa, trovato: {list(result.keys())}"
    assert "/100m" in result["CSS"], f"Il valore CSS deve contenere '/100m', trovato: {result['CSS']!r}"


def test_derive_bike_zones_contains_z2_endurance():
    """Test 3: bike con FTP 240W -> Z2_endurance con watt."""
    result = derive_zones_for_discipline("bike", ftp_w=240)
    assert isinstance(result, dict), "Deve ritornare un dict"
    assert "Z2_endurance" in result, f"Chiave Z2_endurance attesa, trovato: {list(result.keys())}"
    z2 = result["Z2_endurance"]
    assert "W" in z2, f"Il valore Z2_endurance deve contenere 'W', trovato: {z2!r}"
    # 240*0.56=134W, 240*0.75=180W
    assert "134" in z2 or "135" in z2, f"Atteso ~134W come lower bound, trovato: {z2!r}"


def test_derive_bike_ftp_none_returns_empty():
    """Test 4: bike con ftp_w=None -> {} (nessun crash)."""
    result = derive_zones_for_discipline("bike", ftp_w=None)
    assert result == {}, f"Atteso dict vuoto, trovato: {result!r}"


# ---------------------------------------------------------------------------
# Stub dipendenze extra per briefing.py (Task 2)
# ---------------------------------------------------------------------------

# Stub per briefing.py - evita connessioni DB e import pesanti
for _name in [
    "coach.utils.health",
    "coach.planning",
    "coach.planning.personalized_insert",
    "coach.analytics",
    "coach.analytics.belief_engine",
    "coach.analytics.risk",
    "coach.coaching.modulation",
]:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

sys.modules["coach.utils.health"].record_health = MagicMock()  # type: ignore

# Mock requests per evitare import errors in briefing
if "requests" not in sys.modules:
    sys.modules["requests"] = MagicMock()

# Load briefing.py
_br_spec = _ilu.spec_from_file_location(
    "coach.planning.briefing",
    Path(__file__).resolve().parent.parent / "coach" / "planning" / "briefing.py",
)
_br_mod = _ilu.module_from_spec(_br_spec)  # type: ignore
sys.modules["coach.planning.briefing"] = _br_mod
_br_spec.loader.exec_module(_br_mod)  # type: ignore

_format_session_zones = _br_mod._format_session_zones


# ---------------------------------------------------------------------------
# Task 2 — test 5-8: _format_session_zones
# ---------------------------------------------------------------------------

def test_format_session_zones_run_contains_pace():
    """Test 5: run con threshold 263s/km -> stringa non vuota con '/km'."""
    result = _format_session_zones("run", {"run": {"threshold_pace_s_per_km": 263}})
    assert result is not None and result != "", "Deve ritornare stringa non vuota per run"
    assert "/km" in result, f"Deve contenere '/km', trovato: {result!r}"
    assert "4:" in result or "5:" in result, f"Atteso pace intorno a 4-5 min/km, trovato: {result!r}"


def test_format_session_zones_swim_contains_per100m():
    """Test 6: swim con CSS 80s/100m -> stringa con '/100m'."""
    result = _format_session_zones("swim", {"swim": {"css_pace_s_per_100m": 80}})
    assert result is not None and result != "", "Deve ritornare stringa non vuota per nuoto"
    assert "/100m" in result, f"Deve contenere '/100m', trovato: {result!r}"


def test_format_session_zones_bike_ftp_none_placeholder():
    """Test 7: bike con ftp_w=None -> placeholder con 'FTP' e 'non'."""
    result = _format_session_zones("bike", {"bike": {"ftp_w": None}})
    assert result is not None, "Non deve ritornare None per bici senza FTP"
    assert "FTP" in result, f"Deve contenere 'FTP', trovato: {result!r}"
    assert "non" in result.lower(), f"Deve contenere 'non', trovato: {result!r}"


def test_format_session_zones_bike_no_data_no_crash():
    """Test 8: bike con dict vuoto -> None o stringa vuota, nessun crash."""
    try:
        result = _format_session_zones("bike", {})
        assert result is None or result == "", f"Atteso None o stringa vuota, trovato: {result!r}"
    except Exception as e:
        raise AssertionError(f"Non deve sollevare eccezione, trovato: {e}") from e
