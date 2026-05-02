"""Test PMC EWMA — validazione contro numeri di riferimento."""
from datetime import date, timedelta

from coach.analytics.pmc import (
    DailyTSS,
    compute_pmc_series,
    estimate_tss_run,
    estimate_tss_bike_from_np,
    ewma_factor,
)


def test_ewma_factor_known_values():
    # Coggan reference: τ=42 → ~0.0235, τ=7 → ~0.1331
    assert abs(ewma_factor(42) - 0.0235) < 0.001
    assert abs(ewma_factor(7) - 0.1331) < 0.001


def test_pmc_zero_input():
    assert compute_pmc_series([]) == []


def test_pmc_single_day():
    series = compute_pmc_series([DailyTSS(date(2025, 1, 1), 100)])
    assert len(series) == 1
    p = series[0]
    # CTL incremento: 100 * 0.0235 ≈ 2.35
    assert abs(p.ctl - 2.35) < 0.01
    # ATL incremento: 100 * 0.1331 ≈ 13.31
    assert abs(p.atl - 13.31) < 0.01
    assert p.tsb < 0  # ATL > CTL


def test_pmc_steady_state_50_tss_per_day():
    """Atleta che fa 50 TSS/giorno costanti per 200 giorni → CTL e ATL tendono a 50."""
    start = date(2025, 1, 1)
    days = [DailyTSS(start + timedelta(days=i), 50) for i in range(200)]
    series = compute_pmc_series(days)
    last = series[-1]
    assert abs(last.ctl - 50) < 1
    assert abs(last.atl - 50) < 0.1
    assert abs(last.tsb) < 1


def test_pmc_fills_missing_days():
    """Buco di 5 giorni → la serie li riempie a TSS=0."""
    start = date(2025, 1, 1)
    days = [DailyTSS(start, 100), DailyTSS(start + timedelta(days=10), 100)]
    series = compute_pmc_series(days)
    assert len(series) == 11  # 0..10 inclusive
    # Giorno 5 (in mezzo) ha TSS=0
    assert series[5].daily_tss == 0


def test_estimate_tss_run():
    # 1h a IF=1.0 = 100 TSS (definizione)
    assert abs(estimate_tss_run(3600, 1.0) - 100) < 0.01
    # 1h a IF=0.85 ≈ 72 TSS
    assert abs(estimate_tss_run(3600, 0.85) - 72.25) < 0.5


def test_estimate_tss_bike_from_np():
    # NP=200, FTP=250, 1h → IF=0.8 → 64 TSS
    tss = estimate_tss_bike_from_np(3600, 200, 250)
    assert abs(tss - 64) < 0.5


def test_estimate_tss_bike_invalid_ftp():
    import pytest
    with pytest.raises(ValueError):
        estimate_tss_bike_from_np(3600, 200, 0)
