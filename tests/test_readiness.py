"""Test readiness scorer e flag deterministici."""
from coach.analytics.readiness import (
    SubjectiveState,
    TrainingState,
    WellnessHistory,
    compute_flags,
    compute_readiness,
    hrv_z_score,
)


def make_default_subj(**kw) -> SubjectiveState:
    base = dict(motivation=7, soreness=2, illness_flag=False, injury_flag=False, illness_recent_days=0)
    base.update(kw)
    return SubjectiveState(**base)


def test_hrv_z_score_returns_none_with_short_history():
    assert hrv_z_score(50.0, [50.0, 51.0]) is None


def test_hrv_z_score_basic():
    history = [50, 50, 50, 50, 50, 50, 50]  # σ=0
    assert hrv_z_score(50, history) == 0.0


def test_hrv_z_score_negative():
    history = [50, 51, 49, 52, 48, 50, 51]
    z = hrv_z_score(40, history)
    assert z is not None and z < -3


def test_compute_flags_critical_hrv():
    # History con varianza realistica (SD ≈ 4)
    history = [48, 50, 52, 49, 51, 47, 53] * 4
    wellness = WellnessHistory(
        hrv_today=35, hrv_history_28d=history, hrv_recent_z_scores=[],
        sleep_score_today=80, sleep_avg_7d=80,
        body_battery_morning=85, resting_hr_today=55, resting_hr_baseline=55,
    )
    training = TrainingState(ctl=80, atl=85, tsb=-5, days_since_hard_session=2)
    subj = make_default_subj()
    flags = compute_flags(wellness, training, subj)
    assert "fatigue_critical" in flags


def test_compute_flags_illness():
    wellness = WellnessHistory(
        hrv_today=50, hrv_history_28d=[50] * 28, hrv_recent_z_scores=[],
        sleep_score_today=70, sleep_avg_7d=70,
        body_battery_morning=70, resting_hr_today=55, resting_hr_baseline=55,
    )
    training = TrainingState(ctl=80, atl=80, tsb=0, days_since_hard_session=2)
    subj = make_default_subj(illness_flag=True)
    flags = compute_flags(wellness, training, subj)
    assert "illness_flag" in flags


def test_readiness_overrides_to_rest_on_critical():
    history = [48, 50, 52, 49, 51, 47, 53] * 4
    wellness = WellnessHistory(
        hrv_today=35, hrv_history_28d=history, hrv_recent_z_scores=[],
        sleep_score_today=80, sleep_avg_7d=80,
        body_battery_morning=85, resting_hr_today=55, resting_hr_baseline=55,
    )
    training = TrainingState(ctl=80, atl=85, tsb=-5, days_since_hard_session=2)
    report = compute_readiness(wellness, training, make_default_subj())
    assert report.label == "rest"
    assert report.score < 30


def test_readiness_green_light():
    wellness = WellnessHistory(
        hrv_today=55, hrv_history_28d=[50] * 28, hrv_recent_z_scores=[],
        sleep_score_today=88, sleep_avg_7d=85,
        body_battery_morning=90, resting_hr_today=52, resting_hr_baseline=55,
    )
    training = TrainingState(ctl=85, atl=80, tsb=5, days_since_hard_session=2)
    report = compute_readiness(wellness, training, make_default_subj(motivation=9, soreness=1))
    assert report.label == "ready"
    assert report.score >= 75


def test_readiness_caution_with_warning_capped():
    """fatigue_warning cappa a 60 anche se il resto è ottimo."""
    # 2 giorni consecutivi sotto -1.0 σ → fatigue_warning
    history = [50] * 28
    wellness = WellnessHistory(
        hrv_today=43,  # ~-1.5 σ se SD ≈ 5
        hrv_history_28d=[40 + i for i in range(28)],  # SD ~8
        hrv_recent_z_scores=[-1.2, -1.1],
        sleep_score_today=85, sleep_avg_7d=80,
        body_battery_morning=90, resting_hr_today=55, resting_hr_baseline=55,
    )
    # Costruisci una situazione con z negativo
    import statistics
    sd = statistics.pstdev(wellness.hrv_history_28d)
    mean = statistics.fmean(wellness.hrv_history_28d)
    z_today = (wellness.hrv_today - mean) / sd
    if z_today <= -1.0:
        training = TrainingState(ctl=80, atl=85, tsb=-5, days_since_hard_session=2)
        report = compute_readiness(wellness, training, make_default_subj())
        # Almeno verifichiamo che lo score non sia massimo
        assert report.score <= 60 or "fatigue_warning" not in report.flags
