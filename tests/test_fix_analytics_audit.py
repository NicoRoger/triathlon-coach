"""Test di regressione per i fix dell'audit analytics 2026-07-02.

Copre i fix essenziali:
- Fix 1: compute_for estrapola il PMC a TSS=0 nei giorni senza attività
         (prima: ctl/atl/tsb NULL ogni rest day / ogni mattina).
- Fix 3: fatigue_warning solo per 2 giorni di calendario CONSECUTIVI
         (oggi E ieri sotto -1σ); un valore basso di 3 giorni fa con gap
         non deve contare come "ieri".
- Fix 5: hr drift / pace drop leggono anche gli split lapDTO Garmin
         camelCase (averageHR, averageSpeed, averagePower).
- Fix 10: decay_old_beliefs resetta last_reinforced_at (niente decay composto).

Esecuzione: python -m pytest tests/test_fix_analytics_audit.py -v
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ---------------------------------------------------------------------------
# Fake Supabase (stesso pattern di test_audit_resilience.py)
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
        filtered = [r for r in self._rows if r.get(col) == val]
        clone = _FakeQuery(filtered)
        clone.upserted = self.upserted
        return clone

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
        if name == "daily_metrics":
            orig = q.upsert

            def _capture(data, **k):
                self.last_upsert = data
                return orig(data, **k)

            q.upsert = _capture  # type: ignore
        return q


def _make_daily_module(supabase: _FakeSupabase):
    _load("coach.analytics.pmc", "coach/analytics/pmc.py")
    _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    for n in ["coach.utils.supabase_client", "coach.utils.health"]:
        m = types.ModuleType(n)
        sys.modules[n] = m
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: supabase  # type: ignore
    sys.modules["coach.utils.health"].record_health = lambda *a, **k: None  # type: ignore
    return _load("coach.analytics.daily", "coach/analytics/daily.py")


# ===========================================================================
# Fix 1 — PMC estrapolato nei giorni senza attività (mai NULL)
# ===========================================================================
def test_fix1_pmc_extrapolated_on_rest_day():
    """Ultima attività 10 giorni fa → per `day` il PMC deve comunque essere
    valorizzato (decay a TSS=0), non NULL."""
    day = date(2026, 6, 30)
    activities = [{
        "id": "a1",
        "started_at": (day - timedelta(days=10)).isoformat() + "T08:00:00+00:00",
        "sport": "run", "tss": 100, "duration_s": 3600, "avg_hr": 150,
    }]
    sb = _FakeSupabase({"activities": activities, "daily_wellness": [], "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m is not None
    assert m["ctl"] is not None and m["ctl"] > 0, "CTL deve essere estrapolato, non NULL"
    assert m["atl"] is not None
    assert m["tsb"] is not None
    assert m["daily_tss"] == 0.0, "rest day → daily_tss 0, non NULL"
    # decay: CTL del rest day deve essere < CTL post-attività (2.35)
    assert m["ctl"] < 2.35


def test_fix1_no_data_still_null():
    """Nessuna attività e nessun seed → PMC resta NULL (honest signal)."""
    day = date(2026, 6, 30)
    sb = _FakeSupabase({"activities": [], "daily_wellness": [], "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["ctl"] is None and m["tsb"] is None


def test_fix7_pmc_seeded_from_previous_metrics():
    """CTL/ATL del giorno prima della finestra seedano la serie (non si riparte da 0)."""
    day = date(2026, 6, 30)
    window_start = day - timedelta(days=90)
    seed_day = (window_start - timedelta(days=1)).isoformat()
    sb = _FakeSupabase({
        "activities": [],
        "daily_wellness": [],
        "subjective_log": [],
        "daily_metrics": [{"date": seed_day, "ctl": 40.0, "atl": 40.0}],
    })
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    # 90 giorni di decay da CTL=40: 40 * (1-0.0235)^91 ≈ 4.6 — comunque > 0, non NULL
    assert m["ctl"] is not None and 0 < m["ctl"] < 40.0


# ===========================================================================
# Fix 3 — fatigue_warning richiede giorni CONSECUTIVI di calendario
# ===========================================================================
def _wellness_rows(day: date, low_offset_days: int, with_gap: bool) -> list[dict]:
    """Storico stabile (60/61 alternati) + un giorno basso (59.7) + oggi basso (59.8).

    with_gap=True: il giorno basso è a day-3 e mancano day-1/day-2 (gap).
    with_gap=False: il giorno basso è ieri (day-1), catena consecutiva.
    """
    rows = []
    stable_days = range(14, 1, -1) if not with_gap else range(14, 3, -1)
    for i in stable_days:
        d = (day - timedelta(days=i)).isoformat()
        rows.append({"date": d, "hrv_rmssd": 60.0 if i % 2 == 0 else 61.0,
                     "sleep_score": 80, "body_battery_max": 80, "resting_hr": 50})
    low_d = (day - timedelta(days=low_offset_days)).isoformat()
    rows.append({"date": low_d, "hrv_rmssd": 59.7, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50})
    rows.append({"date": day.isoformat(), "hrv_rmssd": 59.8, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50})
    return sorted(rows, key=lambda r: r["date"])


def test_fix3_consecutive_low_days_warn():
    """Oggi E ieri sotto -1σ (consecutivi) → fatigue_warning."""
    day = date(2026, 6, 30)
    wellness = _wellness_rows(day, low_offset_days=1, with_gap=False)
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert "fatigue_critical" not in m["flags"], "setup errato: z oggi deve essere in banda warning"
    assert "fatigue_warning" in m["flags"], "2 giorni consecutivi sotto -1σ devono allarmare"


def test_fix3_gap_day_not_treated_as_yesterday():
    """Giorno basso 3 giorni fa con GAP (ieri senza dati): l'ultima riga wellness
    NON è ieri → niente fatigue_warning (non sono giorni consecutivi)."""
    day = date(2026, 6, 30)
    wellness = _wellness_rows(day, low_offset_days=3, with_gap=True)
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert "fatigue_critical" not in m["flags"], "setup errato: z oggi deve essere in banda warning"
    assert "fatigue_warning" not in m["flags"], (
        "un giorno basso non consecutivo (gap ieri) non deve contare come 'ieri'"
    )


def test_fix3_readiness_yesterday_element_is_checked():
    """Unit: compute_flags guarda SOLO l'elemento [-1] (ieri) di hrv_recent_z_scores."""
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    history = [50, 51, 49, 52, 48, 50, 51] * 4
    base = dict(
        hrv_today=48,  # banda warning
        hrv_history_28d=history,
        sleep_score_today=80, sleep_avg_7d=80,
        body_battery_morning=80, resting_hr_today=50, resting_hr_baseline=50,
    )
    training = readiness.TrainingState(ctl=80, atl=82, tsb=-5, days_since_hard_session=2)
    subj = readiness.SubjectiveState(motivation=7, soreness=2, illness_flag=False, injury_flag=False)

    # ieri ([-1]) basso → warning
    w1 = readiness.WellnessHistory(hrv_recent_z_scores=[0.2, -1.3], **base)
    assert "fatigue_warning" in readiness.compute_flags(w1, training, subj)
    # basso 2 giorni fa ma ieri OK → NIENTE warning (con il bug scattava)
    w2 = readiness.WellnessHistory(hrv_recent_z_scores=[-1.3, 0.2], **base)
    assert "fatigue_warning" not in readiness.compute_flags(w2, training, subj)


# ===========================================================================
# Fix 5 — splits lapDTO Garmin camelCase
# ===========================================================================
def test_fix5_hr_drift_camelcase():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    splits = [{"averageHR": 140}, {"averageHR": 140},
              {"averageHR": 155}, {"averageHR": 155}]
    drift = readiness._compute_hr_drift({}, splits)
    assert drift is not None, "averageHR camelCase deve essere letto"
    assert abs(drift - 15.0) < 0.01


def test_fix5_pace_drop_run_from_average_speed():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    # run: pace derivato da averageSpeed (1000/v). 3.5 m/s → 285.7 s/km; 3.2 → 312.5
    splits = [{"averageSpeed": 3.5}, {"averageSpeed": 3.5},
              {"averageSpeed": 3.2}, {"averageSpeed": 3.2}]
    drop = readiness._compute_pace_drop("run", splits)
    assert drop is not None, "pace run deve derivare da averageSpeed"
    assert drop > 0.05  # ~9.4% di degradazione


def test_fix5_pace_drop_swim_from_average_speed():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    # swim: 100/v. 1.25 m/s → 80 s/100m; 1.15 → 87 s/100m
    splits = [{"averageSpeed": 1.25}, {"averageSpeed": 1.25},
              {"averageSpeed": 1.15}, {"averageSpeed": 1.15}]
    drop = readiness._compute_pace_drop("swim", splits)
    assert drop is not None and drop > 0.05


def test_fix5_power_drop_bike_camelcase():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    splits = [{"averagePower": 200}, {"averagePower": 200},
              {"averagePower": 180}, {"averagePower": 180}]
    drop = readiness._compute_pace_drop("bike", splits)
    assert drop is not None
    assert abs(drop - 0.10) < 0.001


def test_fix5_classify_fatigue_end_to_end_camelcase():
    """Prima del fix: splits lapDTO camelCase → segnali sempre None → feature inerte."""
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    activity = {"sport": "run", "duration_s": 3600}
    # HR stabile, pace degrada >5% via averageSpeed, RPE 8 → muscular
    splits = [{"averageHR": 150, "averageSpeed": 3.8}, {"averageHR": 150, "averageSpeed": 3.8},
              {"averageHR": 152, "averageSpeed": 3.4}, {"averageHR": 152, "averageSpeed": 3.4}]
    result = readiness.classify_fatigue_type(activity, splits, debrief_rpe=8)
    assert result.failure_type == "muscular", (
        f"atteso 'muscular' con splits camelCase, ottenuto {result.failure_type}"
    )
    assert result.signal_used == "hr_drift+pace"


def test_fix5_snake_case_still_works():
    readiness = _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    splits = [{"avg_hr": 145, "avg_pace_s_per_km": 280}, {"avg_hr": 145, "avg_pace_s_per_km": 280},
              {"avg_hr": 160, "avg_pace_s_per_km": 282}, {"avg_hr": 160, "avg_pace_s_per_km": 282}]
    drift = readiness._compute_hr_drift({}, splits)
    assert drift is not None and abs(drift - 15.0) < 0.01
    drop = readiness._compute_pace_drop("run", splits)
    assert drop is not None and 0 < drop < 0.05


# ===========================================================================
# Fix 10 — decay_old_beliefs resetta last_reinforced_at (no decay composto)
# ===========================================================================
def test_fix10_decay_resets_last_reinforced_at():
    sys.modules.pop("coach.analytics.belief_engine", None)
    # Assicura che supabase_client sia importabile anche se un altro test l'ha stubbato
    if "coach.utils.supabase_client" in sys.modules and not hasattr(
        sys.modules["coach.utils.supabase_client"], "get_supabase"
    ):
        sys.modules.pop("coach.utils.supabase_client")
    import coach.analytics.belief_engine as be

    today = datetime(2026, 7, 2, tzinfo=timezone.utc)
    row = {
        "id": "b1", "belief_key": "k", "belief_text": "x",
        "confidence": 0.8, "evidence_n": 10, "status": "validated_belief",
        "evidence_decay_half_life_days": 120,
        "last_reinforced_at": (today - timedelta(days=60)).isoformat(),
        "first_observed_at": (today - timedelta(days=200)).isoformat(),
        "flagged": False,
    }

    update_payloads: list[dict] = []

    def table_side_effect(name):
        t = MagicMock()
        if name == "beliefs":
            t.select.return_value.not_.eq.return_value.execute.return_value = \
                types.SimpleNamespace(data=[dict(row)])

            def _update(payload):
                update_payloads.append(payload)
                chain = MagicMock()
                chain.eq.return_value.execute.return_value = types.SimpleNamespace(data=[])
                return chain

            t.update.side_effect = _update
        else:  # beliefs_history
            t.insert.return_value.execute.return_value = types.SimpleNamespace(data=[])
        return t

    sb = MagicMock()
    sb.table.side_effect = table_side_effect
    be.get_supabase = lambda: sb

    n = be.decay_old_beliefs(today=today)
    assert n == 1
    assert len(update_payloads) == 1
    payload = update_payloads[0]
    # decay applicato: 0.8 * 0.5^(60/120) ≈ 0.566
    assert abs(payload["confidence"] - 0.8 * 0.5 ** 0.5) < 0.005
    # il punto del fix: last_reinforced_at riallineato a oggi, altrimenti il
    # prossimo cron ricalcola il decay dal timestamp vecchio (decay composto)
    assert payload.get("last_reinforced_at") == today.isoformat(), (
        "decay deve resettare last_reinforced_at per non comporre il decay"
    )


def test_fix11_reinforce_skips_retired():
    sys.modules.pop("coach.analytics.belief_engine", None)
    if "coach.utils.supabase_client" in sys.modules and not hasattr(
        sys.modules["coach.utils.supabase_client"], "get_supabase"
    ):
        sys.modules.pop("coach.utils.supabase_client")
    import coach.analytics.belief_engine as be

    retired_row = {
        "id": "b2", "belief_key": "k2", "belief_text": "x", "confidence": 0.08,
        "evidence_n": 7, "status": "retired", "flagged": False,
    }
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        types.SimpleNamespace(data=[retired_row])
    be.get_supabase = lambda: sb

    result = be.reinforce_belief("k2", reason="post-session")
    assert result is not None and result.status == "retired"
    assert not sb.table.return_value.update.called, \
        "una belief retired non deve essere resuscitata da reinforce"


def test_fix11_reinforce_returns_post_update_values():
    sys.modules.pop("coach.analytics.belief_engine", None)
    if "coach.utils.supabase_client" in sys.modules and not hasattr(
        sys.modules["coach.utils.supabase_client"], "get_supabase"
    ):
        sys.modules.pop("coach.utils.supabase_client")
    import coach.analytics.belief_engine as be

    row = {
        "id": "b3", "belief_key": "k3", "belief_text": "x", "confidence": 0.6,
        "evidence_n": 5, "status": "weak_belief", "flagged": False,
    }

    def table_side_effect(name):
        t = MagicMock()
        if name == "beliefs":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                types.SimpleNamespace(data=[dict(row)])
            t.update.return_value.eq.return_value.execute.return_value = \
                types.SimpleNamespace(data=[])
        else:
            t.insert.return_value.execute.return_value = types.SimpleNamespace(data=[])
        return t

    sb = MagicMock()
    sb.table.side_effect = table_side_effect
    be.get_supabase = lambda: sb

    result = be.reinforce_belief("k3")
    assert result is not None
    assert result.evidence_n == 6, "deve ritornare n POST-update (5+1)"
    assert result.confidence > 0.6, "deve ritornare confidence POST-update"
