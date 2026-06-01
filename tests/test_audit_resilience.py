"""Test di regressione per l'audit di resilienza 2026-06-01.

Ogni test referenzia un ID della tassonomia in docs/audit_resilience_2026-06-01.md
e fallirebbe senza il fix corrispondente.

Esecuzione: python -m pytest tests/test_audit_resilience.py -v
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ---------------------------------------------------------------------------
# Fake Supabase: dispatch per nome tabella, supporta la fluent chain usata da daily.py
# ---------------------------------------------------------------------------
class _FakeQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.upserted: list[dict] = []

    def select(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def eq(self, col, val):
        # filtro semplice per illness_flag
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def order(self, *a, **k):
        return self

    def upsert(self, data, **k):
        self.upserted.append(data)
        return self

    def execute(self):
        return types.SimpleNamespace(data=list(self._rows))


class _FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables
        self.last_upsert: dict | None = None

    def table(self, name):
        q = _FakeQuery(list(self._tables.get(name, [])))
        # cattura l'upsert su daily_metrics
        if name == "daily_metrics":
            orig = q.upsert

            def _capture(data, **k):
                self.last_upsert = data
                return orig(data, **k)

            q.upsert = _capture  # type: ignore
        return q


def _make_daily_module(supabase: _FakeSupabase):
    """Carica daily.py con dipendenze reali (pmc/readiness) e supabase fake."""
    # pmc e readiness reali
    _load("coach.analytics.pmc", "coach/analytics/pmc.py")
    _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    # stub utils
    for n in ["coach.utils.supabase_client", "coach.utils.health", "coach.utils.dt"]:
        if n not in sys.modules or not hasattr(sys.modules[n], "__stubbed__"):
            m = types.ModuleType(n)
            m.__stubbed__ = True  # type: ignore
            sys.modules[n] = m
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: supabase  # type: ignore
    sys.modules["coach.utils.health"].record_health = lambda *a, **k: None  # type: ignore
    sys.modules["coach.utils.dt"].today_rome = lambda: date(2026, 5, 30)  # type: ignore
    return _load("coach.analytics.daily", "coach/analytics/daily.py")


# ===========================================================================
# B1 — baseline HRV esclusa per VALORE rimuoveva ogni giorno con HRV == oggi
# ===========================================================================
def test_b1_baseline_not_filtered_by_value():
    """Con HRV stabile (molti giorni == valore di oggi), la baseline deve
    comunque includerli (esclusione per DATA, non per valore)."""
    day = date(2026, 5, 30)
    # 20 giorni storici tutti a 60 + oggi a 60 → baseline deve avere 20 punti, SD=0
    wellness = []
    for i in range(20, 0, -1):
        d = (day - timedelta(days=i)).isoformat()
        wellness.append({"date": d, "hrv_rmssd": 60.0, "sleep_score": 80,
                         "body_battery_max": 80, "resting_hr": 50})
    wellness.append({"date": day.isoformat(), "hrv_rmssd": 60.0, "sleep_score": 80,
                     "body_battery_max": 80, "resting_hr": 50})
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m is not None
    # baseline calcolata su 20 punti == 60 → media 60, SD 0
    assert m["hrv_baseline_28d"] == 60.0
    assert m["hrv_baseline_28d_sd"] == 0
    # z-score definito (0.0), non None (con il bug la baseline sarebbe vuota → z None)
    assert m["hrv_z_score"] == 0.0


# ===========================================================================
# B2 — fatigue_warning scattava dopo 1 giorno invece di 2 (oggi doppio-contato)
# ===========================================================================
def test_b2_single_low_day_does_not_warn():
    """Un solo giorno con HRV basso NON deve produrre fatigue_warning."""
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    history = [50, 51, 49, 52, 48, 50, 51] * 4  # SD realistica (~1.4)
    wellness = readiness.WellnessHistory(
        hrv_today=48,  # oggi in banda warning (-2 < z < -1)
        hrv_history_28d=history,
        hrv_recent_z_scores=[],  # nessun giorno precedente in warning
        sleep_score_today=80, sleep_avg_7d=80,
        body_battery_morning=80, resting_hr_today=50, resting_hr_baseline=50,
    )
    training = readiness.TrainingState(ctl=80, atl=82, tsb=-5, days_since_hard_session=2)
    subj = readiness.SubjectiveState(motivation=7, soreness=2, illness_flag=False, injury_flag=False)
    flags = readiness.compute_flags(wellness, training, subj)
    assert "fatigue_warning" not in flags, "1 giorno basso non deve allarmare"


def test_b2_two_consecutive_low_days_warn():
    """Due giorni consecutivi sotto -1σ → fatigue_warning."""
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    history = [50, 51, 49, 52, 48, 50, 51] * 4
    wellness = readiness.WellnessHistory(
        hrv_today=48,  # oggi in banda warning (-2 < z < -1)
        hrv_history_28d=history,
        hrv_recent_z_scores=[-1.3],  # ieri anche in warning
        sleep_score_today=80, sleep_avg_7d=80,
        body_battery_morning=80, resting_hr_today=50, resting_hr_baseline=50,
    )
    training = readiness.TrainingState(ctl=80, atl=82, tsb=-5, days_since_hard_session=2)
    subj = readiness.SubjectiveState(motivation=7, soreness=2, illness_flag=False, injury_flag=False)
    flags = readiness.compute_flags(wellness, training, subj)
    assert "fatigue_warning" in flags, "2 giorni consecutivi devono allarmare"


def test_b2_daily_excludes_today_from_recent_z():
    """daily.compute_for: recent_z_scores non deve includere oggi.
    Con solo oggi basso e storico stabile, NON deve esserci fatigue_warning."""
    day = date(2026, 5, 30)
    wellness = []
    for i in range(15, 0, -1):
        d = (day - timedelta(days=i)).isoformat()
        wellness.append({"date": d, "hrv_rmssd": 60.0 + (i % 3), "sleep_score": 80,
                         "body_battery_max": 80, "resting_hr": 50})
    # oggi crollo singolo
    wellness.append({"date": day.isoformat(), "hrv_rmssd": 35.0, "sleep_score": 80,
                     "body_battery_max": 80, "resting_hr": 50})
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    # crollo singolo molto basso → fatigue_critical possibile, ma NON fatigue_warning da 1 giorno
    assert "fatigue_warning" not in m["flags"]


# ===========================================================================
# B3 — PMC mancante passato come 0 (non None) → giorno cold-start segna TSB 100
# ===========================================================================
def test_b3_missing_pmc_does_not_score_tsb_optimal():
    """Senza dati PMC (nessuna attività), il TSB non deve risultare 'ottimale' (100).
    Deve usare il neutro 50."""
    day = date(2026, 5, 30)
    wellness = [{"date": day.isoformat(), "hrv_rmssd": 55.0, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50}]
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["ctl"] is None and m["tsb"] is None
    # factor TSB deve essere il neutro 50, non 100
    assert m["readiness_factors"]["tsb"] == 50


# ===========================================================================
# B11 — _score_sleep non clampava 0-100
# ===========================================================================
def test_b11_sleep_score_clamped():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    wh = readiness.WellnessHistory(
        hrv_today=None, hrv_history_28d=[], hrv_recent_z_scores=[],
        sleep_score_today=130, sleep_avg_7d=None,
        body_battery_morning=None, resting_hr_today=None, resting_hr_baseline=None,
    )
    assert readiness._score_sleep(wh) == 100
    wh2 = readiness.WellnessHistory(
        hrv_today=None, hrv_history_28d=[], hrv_recent_z_scores=[],
        sleep_score_today=-5, sleep_avg_7d=None,
        body_battery_morning=None, resting_hr_today=None, resting_hr_baseline=None,
    )
    assert readiness._score_sleep(wh2) == 0


# ===========================================================================
# I1 — hard cap mai applicato sulla spesa REALE (solo proiezione)
# ===========================================================================
def test_i1_actual_spend_over_cap_blocks_non_emergency():
    """Spesa reale già oltre $5.00 → blocco anche se la stima è minuscola."""
    from unittest.mock import patch
    from coach.utils.budget import check_budget_or_raise, BudgetExceededError
    with patch("coach.utils.budget.get_month_spend_usd", return_value=5.01), \
         patch("coach.utils.budget._send_budget_alert"):
        with pytest.raises(BudgetExceededError):
            # stima irrisoria: senza il fix su spesa-reale, projected=5.01+0.0001
            # > 4.80 bloccherebbe comunque; il caso critico è spend appena sotto
            # cap con stima che sottostima — vedi test successivo.
            check_budget_or_raise(0.0001, "session_analysis")


def test_i1_actual_spend_at_cap_blocks_even_if_projection_low():
    """Spend == cap esatto deve bloccare (>=), a prescindere dalla proiezione."""
    from unittest.mock import patch
    from coach.utils.budget import check_budget_or_raise, BudgetExceededError, BUDGET_HARD_CAP
    with patch("coach.utils.budget.get_month_spend_usd", return_value=BUDGET_HARD_CAP), \
         patch("coach.utils.budget._send_budget_alert"):
        with pytest.raises(BudgetExceededError):
            check_budget_or_raise(0.0, "session_analysis")


def test_i1_emergency_bypasses_hard_cap():
    from unittest.mock import patch
    from coach.utils.budget import check_budget_or_raise
    with patch("coach.utils.budget.get_month_spend_usd", return_value=5.50), \
         patch("coach.utils.budget._send_budget_alert"):
        # emergency non deve sollevare
        check_budget_or_raise(0.10, "emergency")


# ===========================================================================
# I2 — days_in_month errato per dicembre / aritmetica mese fragile
# ===========================================================================
def test_i2_days_in_month_correct_all_months():
    from unittest.mock import patch
    from datetime import datetime, timezone
    import coach.utils.budget as budget
    expected = {1: 31, 2: 28, 4: 30, 12: 31}
    for month, exp in expected.items():
        fake_now = datetime(2026, month, 15, tzinfo=timezone.utc)

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now

        with patch.object(budget, "datetime", _DT), \
             patch("coach.utils.budget.get_supabase") as mock_sb:
            mock_sb.return_value.table.return_value.select.return_value.gte.return_value.execute.return_value.data = []
            stats = budget.get_month_stats()
            # days_remaining = days_in_month - day(15)
            assert stats["days_remaining"] == exp - 15, f"month {month}"


# ===========================================================================
# I9 — alert budget su OGNI chiamata (spam) invece che all'attraversamento
# ===========================================================================
def test_i9_no_alert_when_already_above_threshold():
    """Se la spesa è GIÀ sopra la soglia warning, una nuova chiamata non
    deve rimandare l'alert (dedup anti-spam)."""
    from unittest.mock import patch
    from coach.utils.budget import check_budget_or_raise
    with patch("coach.utils.budget.get_month_spend_usd", return_value=4.20), \
         patch("coach.utils.budget._send_budget_alert") as mock_alert:
        # 4.20 già oltre 4.00: nessun nuovo attraversamento → niente alert
        check_budget_or_raise(0.05, "session_analysis")
        mock_alert.assert_not_called()


# ===========================================================================
# A4 — startTimeGMT naive (senza Z) → datetime naive, drift Rome/UTC
# E6 — activityName salvato in notes per la safety-net keyword
# ===========================================================================
def test_a4_naive_start_time_forced_utc():
    from coach.ingest.garmin import _normalize_activity
    raw = {
        "activityId": 123,
        "activityType": {"typeKey": "running"},
        "startTimeGMT": "2026-05-30 06:12:33",  # spazio, NO Z, NO offset
        "duration": 3600,
        "activityName": "Easy Run",
    }
    act = _normalize_activity(raw)
    assert act.started_at.tzinfo is not None, "started_at deve essere tz-aware"
    assert act.started_at.utcoffset().total_seconds() == 0, "deve essere UTC"


def test_e6_activity_name_stored_in_notes():
    from coach.ingest.garmin import _normalize_activity
    raw = {
        "activityId": 99,
        "activityType": {"typeKey": "cycling"},
        "startTimeGMT": "2026-06-15T07:00:00Z",
        "duration": 1800,
        "activityName": "FTP Test 20min",
    }
    act = _normalize_activity(raw)
    assert act.notes == "FTP Test 20min"


def test_a4_missing_start_time_raises_clear():
    from coach.ingest.garmin import _normalize_activity
    raw = {"activityId": 1, "activityType": {"typeKey": "running"}, "duration": 60}
    with pytest.raises(ValueError):
        _normalize_activity(raw)
