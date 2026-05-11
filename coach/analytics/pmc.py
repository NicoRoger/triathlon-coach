"""Performance Management Chart — CTL/ATL/TSB con EWMA.

Modulo deterministico, testabile, mai chiamato dall'LLM. La verità numerica del
sistema. Tutti i calcoli qui sono validati contro i numeri TrainingPeaks/
Intervals.icu di riferimento.

Riferimenti metodologici:
- Coggan, "Training and Racing with a Power Meter" (TSS/IF/CTL/ATL)
- Friel, "Triathlete's Training Bible"
- Skiba, "Scientific Training for Endurance Athletes" (varianti EWMA)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

# Costanti standard PMC
CTL_TIME_CONSTANT = 42  # giorni — chronic, "fitness"
ATL_TIME_CONSTANT = 7   # giorni — acute, "fatigue"


@dataclass(frozen=True)
class DailyTSS:
    """TSS aggregato per giorno (somma di tutte le sessioni)."""
    day: date
    tss: float


@dataclass(frozen=True)
class PMCPoint:
    day: date
    ctl: float
    atl: float
    tsb: float
    daily_tss: float


def ewma_factor(time_constant_days: int) -> float:
    """Calcola il fattore lambda per EWMA discreto giornaliero.

    Formula standard PMC: factor = 1 - exp(-1/τ)
    Per τ=42 → ~0.0235, per τ=7 → ~0.1331
    """
    import math
    return 1.0 - math.exp(-1.0 / time_constant_days)


def compute_pmc_series(
    daily_tss: Iterable[DailyTSS],
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
    fill_missing_days: bool = True,
) -> list[PMCPoint]:
    """Calcola serie PMC giornaliera completa.

    Args:
        daily_tss: serie ordinata di DailyTSS (può essere sparsa)
        initial_ctl: CTL al giorno *prima* del primo punto (per riprese a metà storia)
        initial_atl: ATL al giorno prima del primo punto
        fill_missing_days: se True, inserisce giorni a TSS=0 nei buchi (corretto)

    Returns:
        Lista PMCPoint contigua giorno per giorno.
    """
    points = sorted(daily_tss, key=lambda x: x.day)
    if not points:
        return []

    # Normalizza in dict per accesso O(1)
    tss_by_day = {p.day: p.tss for p in points}

    # Range completo
    start = points[0].day
    end = points[-1].day

    if fill_missing_days:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    else:
        days = sorted(tss_by_day.keys())

    ctl_lambda = ewma_factor(CTL_TIME_CONSTANT)
    atl_lambda = ewma_factor(ATL_TIME_CONSTANT)

    ctl = initial_ctl
    atl = initial_atl
    out: list[PMCPoint] = []

    for d in days:
        tss = tss_by_day.get(d, 0.0)
        # Forma incrementale EWMA: new = old + λ*(tss - old)
        ctl = ctl + ctl_lambda * (tss - ctl)
        atl = atl + atl_lambda * (tss - atl)
        out.append(PMCPoint(day=d, ctl=ctl, atl=atl, tsb=ctl - atl, daily_tss=tss))

    return out


def compute_pmc_for_today(
    daily_tss: Iterable[DailyTSS],
    today: Optional[date] = None,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> Optional[PMCPoint]:
    """Restituisce il punto PMC per oggi, estrapolando se necessario."""
    today = today or date.today()
    series = compute_pmc_series(daily_tss, initial_ctl, initial_atl)
    if not series:
        return None

    # Se l'ultimo punto è oggi, restituiscilo
    last = series[-1]
    if last.day == today:
        return last

    # Estendi a TSS=0 fino a oggi
    ctl, atl = last.ctl, last.atl
    ctl_lambda = ewma_factor(CTL_TIME_CONSTANT)
    atl_lambda = ewma_factor(ATL_TIME_CONSTANT)
    cur = last.day + timedelta(days=1)
    while cur <= today:
        ctl = ctl + ctl_lambda * (0.0 - ctl)
        atl = atl + atl_lambda * (0.0 - atl)
        cur += timedelta(days=1)

    return PMCPoint(day=today, ctl=ctl, atl=atl, tsb=ctl - atl, daily_tss=0.0)


# ============================================================================
# TSS estimation per sport (quando il device non lo fornisce)
# ============================================================================
def estimate_tss_run(duration_s: int, intensity_factor: float) -> float:
    """TSS standard: (duration_s × IF² × 100) / 3600."""
    return (duration_s * intensity_factor**2 * 100.0) / 3600.0


def estimate_tss_bike_from_np(
    duration_s: int, np_w: float, ftp_w: float
) -> float:
    """TSS bici da Normalized Power."""
    if ftp_w <= 0:
        raise ValueError("FTP must be positive")
    if_value = np_w / ftp_w
    return estimate_tss_run(duration_s, if_value)


def estimate_tss_swim_from_pace(
    duration_s: int, avg_pace_s_per_100m: float, css_pace_s_per_100m: float
) -> float:
    """TSS nuoto da pace e CSS (Critical Swim Speed).

    Approssimazione: IF = css_pace / actual_pace (più veloce = IF maggiore).
    """
    if avg_pace_s_per_100m <= 0 or css_pace_s_per_100m <= 0:
        raise ValueError("Pace values must be positive")
    if_value = css_pace_s_per_100m / avg_pace_s_per_100m
    return estimate_tss_run(duration_s, if_value)


def estimate_tss_from_hr(
    duration_s: int, avg_hr: int, lthr: int, alpha: float = 1.0
) -> float:
    """TSS fallback da HR quando potenza/passo non disponibili.

    Meno preciso ma robusto. hrTSS = (duration × (avgHR/LTHR)²) × alpha × 100/3600.
    Da usare con consapevolezza: HR drift, caldo, idratazione lo distorcono.
    """
    if lthr <= 0:
        raise ValueError("LTHR must be positive")
    ratio = avg_hr / lthr
    return (duration_s * ratio**2 * alpha * 100.0) / 3600.0


# ============================================================================
# Helper per aggregazione da activities
# ============================================================================
def aggregate_daily_tss(activities: list[dict]) -> list[DailyTSS]:
    """Da lista di activity dict (con `started_at` e `tss`) → DailyTSS sommati per giorno.

    Fallback chain se `tss` è null:
    1. `training_load` Garmin (scala simile al TSS)
    2. hrTSS stimato da `duration_s` + `avg_hr` con LTHR da env ATHLETE_LTHR (default 160)
    """
    import os
    from collections import defaultdict

    bucket: dict[date, float] = defaultdict(float)
    for a in activities:
        tss = a.get("tss")

        if tss is None:
            tss = a.get("training_load")  # fallback 1: Garmin proprietary load

        if tss is None:
            dur = a.get("duration_s")
            avg_hr = a.get("avg_hr")
            if dur and avg_hr:
                lthr = int(os.environ.get("ATHLETE_LTHR", "160"))
                try:
                    tss = estimate_tss_from_hr(int(dur), int(avg_hr), lthr)
                except (ValueError, ZeroDivisionError):
                    pass

        if tss is None:
            continue

        d = a["started_at"].date() if hasattr(a["started_at"], "date") else a["started_at"]
        bucket[d] += float(tss)
    return [DailyTSS(day=d, tss=v) for d, v in sorted(bucket.items())]
