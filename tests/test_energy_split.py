"""Split energia al risveglio dal brief delle 5:00.

Body Battery e readiness Garmin escono dal brief mattutino (la notifica
delle 5 interrompe il sonno e falsa proprio quei due valori) e vanno in un
messaggio separato, mandato più tardi (build_energy_update / main_energy).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None  # type: ignore
    return mod


for _name in [
    "coach", "coach.utils", "coach.utils.supabase_client",
    "coach.utils.dt", "coach.utils.health",
    "coach.utils.telegram_logger",
    "coach.coaching",
    "coach.planning",
    "coach.planning.personalized_insert",
    "coach.coaching.modulation",
]:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

sys.modules["coach.utils.supabase_client"].get_supabase = MagicMock(return_value=MagicMock())  # type: ignore
sys.modules["coach.utils.dt"].today_rome = MagicMock(return_value="2026-07-07")  # type: ignore
sys.modules["coach.utils.telegram_logger"].send_and_log_message = MagicMock(return_value=123)  # type: ignore
sys.modules["coach.utils.health"].record_health = MagicMock()  # type: ignore

if "requests" not in sys.modules:
    sys.modules["requests"] = MagicMock()

import importlib.util as _ilu

_br_spec = _ilu.spec_from_file_location(
    "coach.planning.briefing",
    Path(__file__).resolve().parent.parent / "coach" / "planning" / "briefing.py",
)
briefing = _ilu.module_from_spec(_br_spec)  # type: ignore
sys.modules["coach.planning.briefing"] = briefing
_br_spec.loader.exec_module(briefing)  # type: ignore


WELLNESS = {"sleep_score": 80, "body_battery_max": 40, "training_readiness_score": 30}
METRICS = {"hrv_z_score": 0.2, "readiness_score": 75, "garmin_training_readiness": 30}


def test_wellness_section_excludes_energy():
    """Il brief delle 5:00 non deve più contenere Body Battery/readiness Garmin."""
    section = briefing._build_wellness_section(WELLNESS, METRICS)
    assert "Energia al risveglio" not in section
    assert "Garmin" not in section
    assert "Sonno stanotte" in section  # sleep/HRV restano nel brief


def test_energy_section_contains_body_battery_and_discrepancy():
    """Il messaggio energia separato contiene Body Battery e lo scarto readiness."""
    section = briefing._build_energy_section(WELLNESS, METRICS)
    assert "Energia al risveglio" in section
    assert "40/100" in section
    # |75-30| = 45 > 15 → nota di discrepanza presente
    assert "Garmin" in section and "Δ45" in section


def test_energy_section_empty_without_data():
    assert briefing._build_energy_section({}, {}) == ""


def test_main_energy_floor_gate_skips_before_7am(monkeypatch):
    """Prima delle 07:00 Rome, main_energy non deve inviare nulla."""
    import datetime as _dt
    from zoneinfo import ZoneInfo

    class _FixedDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 7, 7, 6, 30, tzinfo=tz or ZoneInfo("Europe/Rome"))

    monkeypatch.setattr(briefing, "datetime", _FixedDatetime)
    monkeypatch.delenv("FORCE_SEND", raising=False)
    sent = MagicMock()
    monkeypatch.setattr(briefing, "send_to_telegram", sent)

    briefing.main_energy()

    sent.assert_not_called()
