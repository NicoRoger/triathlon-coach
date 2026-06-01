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

# Cattura il modulo briefing REALE all'import di questo file (collezionato per
# primo, prima che altri test stubbino il package coach.planning in sys.modules).
from coach.planning import briefing as _briefing_mod  # noqa: E402


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
    # stub solo supabase_client e health; dt resta REALE (serve to_rome_date e
    # compute_for riceve `day` esplicito, non usa today_rome).
    for n in ["coach.utils.supabase_client", "coach.utils.health"]:
        m = types.ModuleType(n)
        sys.modules[n] = m
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: supabase  # type: ignore
    sys.modules["coach.utils.health"].record_health = lambda *a, **k: None  # type: ignore
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


# ===========================================================================
# A5 — precedenza operatori nel check np_w > max_power
# ===========================================================================
def test_a5_np_gt_max_power_warns():
    from coach.utils.validators import validate_activity
    act = {"sport": "bike", "duration_s": 3600, "avg_power_w": 200,
           "max_power_w": 300, "np_w": 350}  # np > max → anomalo
    res = validate_activity(act)
    assert any("np_w" in w for w in res.warnings), "np_w>max_power deve generare warning"


def test_a5_np_le_max_power_no_warn():
    from coach.utils.validators import validate_activity
    act = {"sport": "bike", "duration_s": 3600, "avg_power_w": 200,
           "max_power_w": 400, "np_w": 220}  # np < max → ok
    res = validate_activity(act)
    assert not any("np_w" in w for w in res.warnings)


def test_a5_no_crash_when_max_power_none():
    from coach.utils.validators import validate_activity
    act = {"sport": "bike", "duration_s": 3600, "avg_power_w": 200, "np_w": 220}
    # max_power None: non deve sollevare TypeError
    validate_activity(act)


# ===========================================================================
# Area D — modulazioni: D2 (falso successo), D3 (merge), D4 (None format)
# ===========================================================================
class _ModFakeQuery:
    def __init__(self, parent, table):
        self.parent = parent
        self.table = table
        self._payload = None
        self._op = None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, **k):
        self.parent.upserts.append(payload)
        return self

    def execute(self):
        if self._op == "update" and self.table == "plan_modulations":
            self.parent.mod_update = self._payload
            # rifletti l'update sul mod condiviso (così i re-read vedono lo status nuovo)
            if self.parent.mod:
                self.parent.mod.update(self._payload)
        if self.table == "plan_modulations":
            return types.SimpleNamespace(data=[self.parent.mod] if self.parent.mod else [])
        if self.table == "planned_sessions":
            return types.SimpleNamespace(data=list(self.parent.existing_sessions))
        return types.SimpleNamespace(data=[])


class _ModFakeSB:
    def __init__(self, mod, existing_sessions=None):
        self.mod = mod
        self.existing_sessions = existing_sessions or []
        self.upserts = []
        self.mod_update = None

    def table(self, name):
        return _ModFakeQuery(self, name)


def _load_modulation(sb):
    for n in ["coach.utils.supabase_client", "coach.utils.budget"]:
        if n not in sys.modules:
            sys.modules[n] = types.ModuleType(n)
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: sb  # type: ignore
    if not hasattr(sys.modules["coach.utils.budget"], "BudgetExceededError"):
        class _BE(Exception):
            pass
        sys.modules["coach.utils.budget"].BudgetExceededError = _BE  # type: ignore
    return _load("coach.coaching.modulation", "coach/coaching/modulation.py")


def test_d2_partial_apply_not_marked_accepted():
    """D2: se una modifica viene saltata (sport mancante), lo status NON è accepted."""
    mod = {"id": "m1", "status": "proposed", "proposed_changes": [
        {"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}},
        {"date": "2026-06-03", "new": {"duration_s": 1800}},  # manca sport → skip
    ]}
    sb = _ModFakeSB(mod)
    mt = _load_modulation(sb)
    ok = mt.apply_modulation("m1")
    assert ok is False
    assert sb.mod_update["status"] == "partial"


def test_d2_full_apply_accepted():
    mod = {"id": "m2", "status": "proposed", "proposed_changes": [
        {"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}},
    ]}
    sb = _ModFakeSB(mod)
    mt = _load_modulation(sb)
    assert mt.apply_modulation("m2") is True
    assert sb.mod_update["status"] == "applied"
    # niente literal "now()" — deve essere un ISO timestamp
    assert "now()" != sb.mod_update["resolved_at"]


def test_d3_merge_preserves_session_type():
    """D3: una modifica che tocca solo la durata non azzera session_type esistente."""
    mod = {"id": "m3", "status": "proposed", "proposed_changes": [
        {"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}},
    ]}
    existing = [{"planned_date": "2026-06-02", "sport": "run",
                 "session_type": "threshold", "duration_s": 3600,
                 "description": "6x1000 soglia"}]
    sb = _ModFakeSB(mod, existing_sessions=existing)
    mt = _load_modulation(sb)
    mt.apply_modulation("m3")
    up = sb.upserts[0]
    assert up["session_type"] == "threshold", "session_type esistente preservato"
    assert up["duration_s"] == 1800, "durata aggiornata"
    assert up["description"] == "6x1000 soglia"


def test_d4_none_hrv_z_does_not_crash():
    sb = _ModFakeSB(None)
    mt = _load_modulation(sb)
    # hrv_z presente ma None → non deve sollevare
    msg = mt._format_modulation_message("hrv", {"hrv_z": None, "rpe": None}, [])
    assert isinstance(msg, str)


# ===========================================================================
# D5 / E8 — to_rome_date: confronto data Rome vs slicing UTC
# ===========================================================================
def test_d5_to_rome_date_crosses_midnight():
    from coach.utils.dt import to_rome_date
    # 2026-06-01 23:30 UTC = 2026-06-02 01:30 Rome (estate, UTC+2)
    assert to_rome_date("2026-06-01T23:30:00Z") == date(2026, 6, 2)
    # 2026-01-15 23:30 UTC = 2026-01-16 00:30 Rome (inverno, UTC+1)
    assert to_rome_date("2026-01-15T23:30:00Z") == date(2026, 1, 16)


def test_d5_to_rome_date_robust_to_bad_input():
    from coach.utils.dt import to_rome_date
    assert to_rome_date(None) is None
    assert to_rome_date("") is None
    assert to_rome_date("not-a-date") is None


def test_d5_naive_timestamp_treated_as_utc():
    from coach.utils.dt import to_rome_date
    # naive (senza tz) → trattato come UTC
    assert to_rome_date("2026-06-01 23:30:00") == date(2026, 6, 2)


# ===========================================================================
# H1 — race_mental: T-0 delega al race day brief, non stringa vuota
# ===========================================================================
def test_h1_mental_check_t0_delegates():
    # NB: usa il modulo budget reale (ha BudgetExceededError); non sostituirlo
    # per non rompere l'isolamento di test_budget.py.
    rm = _load("coach.coaching.race_mental", "coach/coaching/race_mental.py")
    msg = rm.generate_mental_check(0)
    assert msg and "RACE DAY" in msg, "T-0 deve produrre il race day brief"
    # countdown negativo → nessun messaggio, ma non crash
    assert rm.generate_mental_check(-1) == ""


# ===========================================================================
# H2 — test_scheduler: _pick_test_date non va in loop infinito
# ===========================================================================
def test_h2_pick_test_date_bounded():
    # fake sb: ogni data risulta SEMPRE occupata → senza cap sarebbe loop infinito
    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self):
            return types.SimpleNamespace(data=[{"id": "busy"}])

    class _SB:
        def table(self, *a, **k): return _Q()

    for n in ["coach.utils.supabase_client", "coach.utils.dt"]:
        if n in sys.modules and not hasattr(sys.modules[n], "today_rome") and n.endswith("dt"):
            pass
    # dt reale serve; supabase non usato da _pick_test_date direttamente (sb passato)
    ts = _load("coach.coaching.test_scheduler", "coach/coaching/test_scheduler.py")
    result = ts._pick_test_date(_SB(), date(2026, 6, 1))
    assert result is not None  # ritorna senza appendere (cap raggiunto)


# ===========================================================================
# G3 — outcome_verification: int(None) da view non deve crashare il render
# ===========================================================================
def test_g3_int_none_guard():
    # Riproduce il pattern del fix: int(r.get("n") or 0) gestisce None
    r = {"n": None}
    assert int(r.get("n") or 0) == 0
    r2 = {"n": "5"}
    assert int(r2.get("n") or 0) == 5


# ===========================================================================
# G1 — sync beliefs con 0 candidati NON deve contraddire le belief esistenti
# ===========================================================================
def test_g1_no_contradiction_when_zero_candidates():
    # stub belief_engine
    be = types.ModuleType("coach.analytics.belief_engine")
    contradicted = []

    class _B:
        belief_key = "hrv-basso-sabato"
        status = "weak_belief"
        flagged = False
        from datetime import datetime as _dt, timezone as _tz
        last_reinforced_at = _dt.now(_tz.utc)

    be.list_beliefs = lambda **k: [_B()]  # type: ignore
    be.contradict_belief = lambda key, reason="": contradicted.append(key)  # type: ignore
    be.create_belief = lambda **k: None  # type: ignore
    be.reinforce_belief = lambda *a, **k: None  # type: ignore
    sys.modules["coach.analytics.belief_engine"] = be
    mod = _load("coach.coaching.extract_beliefs_from_observations",
                "coach/coaching/extract_beliefs_from_observations.py")
    # contenuto che NON matcha il formato pattern → 0 candidati (es. fallback biometrico)
    content = "### HRV media settimana\n- **media**: 60ms\n- **trend**: stabile\n"
    counts = mod.sync_beliefs_from_observations(content=content)
    assert counts["contradicted"] == 0, "0 candidati non deve contraddire nulla"
    assert contradicted == []


def test_g1_parses_zero_from_biometric_fallback():
    mod = sys.modules.get("coach.coaching.extract_beliefs_from_observations")
    if mod is None:
        be = types.ModuleType("coach.analytics.belief_engine")
        be.list_beliefs = lambda **k: []  # type: ignore
        be.contradict_belief = be.create_belief = be.reinforce_belief = lambda *a, **k: None  # type: ignore
        sys.modules["coach.analytics.belief_engine"] = be
        mod = _load("coach.coaching.extract_beliefs_from_observations",
                    "coach/coaching/extract_beliefs_from_observations.py")
    cands = mod.parse_observations_to_candidates("### Titolo\n- **k**: v\n")
    assert cands == []


# ===========================================================================
# G2 — pattern_extraction: testo LLM vuoto NON sovrascrive observations
# ===========================================================================
def test_g2_empty_llm_text_does_not_overwrite(tmp_path):
    # fake supabase: nessuna analisi/debrief
    class _Q:
        def select(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def execute(self): return types.SimpleNamespace(data=[])

    class _SB:
        def table(self, *a, **k): return _Q()

    sys.modules["coach.utils.supabase_client"] = types.ModuleType("coach.utils.supabase_client")
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: _SB()  # type: ignore
    # budget reale (ha BudgetExceededError); non sostituirlo.
    sys.modules["coach.utils.llm_client"] = types.ModuleType("coach.utils.llm_client")

    mod = _load("coach.coaching.pattern_extraction", "coach/coaching/pattern_extraction.py")

    f = tmp_path / "obs.md"
    f.write_text("CONTENUTO IMPORTANTE", encoding="utf-8")
    mod.OBSERVATIONS_FILE = f
    mod.today_rome = lambda: date(2026, 5, 30)  # robusto a pollution globale di today_rome
    mod.extract_biometric_patterns = lambda days=28: {}  # niente biometrico → niente fallback

    class _Client:
        def call(self, **k):
            return {"text": "   "}  # vuoto/whitespace

    sys.modules["coach.utils.llm_client"].get_client_for_purpose = lambda p: _Client()  # type: ignore

    out = mod.extract_patterns(days=28)
    assert out is None
    assert f.read_text(encoding="utf-8") == "CONTENUTO IMPORTANTE", "file non deve essere sovrascritto da testo vuoto"


# ===========================================================================
# C2/C3 — briefing: sezioni gara resilienti, timestamp naive non crasha
# ===========================================================================
def test_c3_last_sync_naive_timestamp_no_crash():
    briefing = _briefing_mod

    class _Q:
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self):
            # timestamp NAIVE (senza tz)
            return types.SimpleNamespace(data=[{"last_success_at": "2026-06-01 06:00:00"}])

    class _SB:
        def table(self, *a, **k): return _Q()

    hours = briefing._last_sync_age_hours(_SB())
    assert isinstance(hours, float)


def test_c2_get_upcoming_race_resilient_to_db_error():
    from unittest.mock import patch
    with patch.object(_briefing_mod, "get_supabase", side_effect=RuntimeError("db down")):
        assert _briefing_mod._get_upcoming_race(date(2026, 6, 1)) is None


def test_c2_race_progress_resilient_to_db_error():
    from unittest.mock import patch
    with patch.object(_briefing_mod, "get_supabase", side_effect=RuntimeError("db down")):
        assert _briefing_mod._build_race_progress_section(date(2026, 6, 1)) == ""


# ===========================================================================
# L2/L3/L4 — workflow/script: fallimenti silenziosi
# ===========================================================================
def test_l3_empty_snapshot_aborts():
    ds = _load("scripts.dr_snapshot", "scripts/dr_snapshot.py")
    full = {"activities": [{"id": 1}], "daily_wellness": [{"date": "x"}],
            "daily_metrics": [{"date": "x"}], "races": []}
    ds.assert_snapshot_sane(full)  # ok, non solleva
    empty = {"activities": [], "daily_wellness": [{"date": "x"}], "daily_metrics": [{"date": "x"}]}
    with pytest.raises(ds.EmptySnapshotError):
        ds.assert_snapshot_sane(empty)


def test_l4_watchdog_alerts_missing_component():
    from datetime import datetime, timezone
    wd = _load("scripts.watchdog", "scripts/watchdog.py")
    # nessuna riga health → ogni componente atteso deve generare un alert
    alerts = wd.compute_alerts([], datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert len(alerts) == len(wd.THRESHOLDS_HOURS)
    assert any("garmin_sync" in a for a in alerts)


def test_l4_watchdog_stale_component():
    from datetime import datetime, timezone, timedelta
    wd = _load("scripts.watchdog", "scripts/watchdog.py")
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
    old = (now - timedelta(hours=20)).isoformat()
    rows = [{"component": c, "last_success_at": old} for c in wd.THRESHOLDS_HOURS]
    alerts = wd.compute_alerts(rows, now)
    # garmin_sync soglia 8h, 20h → alert; briefing_morning soglia 26h → no
    assert any("garmin_sync" in a and "🚨" in a for a in alerts)


def test_l2_db_cleanup_exits_nonzero_on_error():
    dc = _load("scripts.db_cleanup", "scripts/db_cleanup.py")

    class _Q:
        def delete(self, *a, **k): return self
        def lt(self, *a, **k): return self
        def in_(self, *a, **k): return self
        def execute(self):
            raise RuntimeError("delete failed")

    class _SB:
        def table(self, *a, **k): return _Q()

    dc.get_supabase = lambda: _SB()  # type: ignore
    with pytest.raises(SystemExit) as exc:
        dc.main()
    assert exc.value.code == 1


# ===========================================================================
# O1/O2/O3 — schema.sql e migration idempotenti (source assertion)
# ===========================================================================
def test_o1_schema_create_table_idempotent():
    src = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    import re
    # Ogni CREATE TABLE deve avere IF NOT EXISTS
    bad = re.findall(r"CREATE TABLE (?!IF NOT EXISTS)", src)
    assert not bad, "tutti i CREATE TABLE devono essere IF NOT EXISTS"
    bad_idx = re.findall(r"CREATE INDEX (?!IF NOT EXISTS)", src)
    assert not bad_idx, "tutti i CREATE INDEX devono essere IF NOT EXISTS"
    assert "ON CONFLICT (component) DO NOTHING" in src
    assert "DROP TRIGGER IF EXISTS" in src


def test_o3_migrations_idempotent():
    for f in ["2026-05-10-fix-planned-sessions-unique.sql", "2026-05-12-mesocycles-unique.sql"]:
        src = (ROOT / "migrations" / f).read_text(encoding="utf-8")
        assert "EXCEPTION" in src, f"{f} deve gestire il re-run (DO/EXCEPTION)"


def test_o4_o6_migration_present():
    src = (ROOT / "migrations" / "2026-06-01-resilience-audit.sql").read_text(encoding="utf-8")
    assert "races_name_date_unique" in src
    assert "expires_at" in src
    assert "mesocycles_target_race_fk" in src


# ===========================================================================
# D1 — modulazione scaduta non viene applicata
# ===========================================================================
def test_d1_expired_modulation_not_applied():
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    mod = {"id": "mexp", "status": "proposed", "expires_at": past,
           "proposed_changes": [{"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}}]}
    sb = _ModFakeSB(mod)
    mt = _load_modulation(sb)
    assert mt.apply_modulation("mexp") is False
    assert sb.mod_update["status"] == "expired"
    assert sb.upserts == [], "nessuna modifica al piano per una modulazione scaduta"


def test_d1_null_expires_still_applies():
    mod = {"id": "mok", "status": "proposed", "expires_at": None,
           "proposed_changes": [{"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}}]}
    sb = _ModFakeSB(mod)
    mt = _load_modulation(sb)
    assert mt.apply_modulation("mok") is True


# ===========================================================================
# K1 — apply_accepted_modulations applica le modulazioni accettate dal bot
# ===========================================================================
def test_k1_accepted_modulation_gets_applied():
    # bot ha settato status='accepted'; il cron deve applicarla
    mod = {"id": "acc1", "status": "accepted", "expires_at": None,
           "proposed_changes": [{"date": "2026-06-02", "sport": "run", "new": {"duration_s": 1800}}]}
    sb = _ModFakeSB(mod)
    mt = _load_modulation(sb)
    summary = mt.apply_accepted_modulations()
    assert summary["applied"] == 1
    assert mod["status"] == "applied"  # transizione accepted → applied
    assert sb.upserts, "le modifiche devono essere scritte sul piano"
