"""Outlier validation per activities e wellness data.

Fase 1.4 del piano cognitive evolution. Prima di inserire dati nel DB,
verifica che siano biologicamente plausibili e cross-field consistent.

Ogni validator ritorna `ValidationResult` con:
- ok: bool (True = passa, False = reject)
- warnings: list[str] (non bloccanti, da loggare)
- errors: list[str] (bloccanti, reject record)

Pattern:
    result = validate_activity(act_dict)
    if not result.ok:
        logger.warning("Activity rejected: %s", result.errors)
        return
    if result.warnings:
        logger.warning("Activity warnings: %s", result.warnings)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ============================================================================
# Soglie biologiche / fisiologiche
# ============================================================================
# Heart rate
HR_MIN = 30          # bradicardia estrema (atleti elite a riposo possono avvicinarsi)
HR_MAX = 230         # 220 - età approssimato; > 230 impossibile

# Pace (s/km)
PACE_MIN_S_PER_KM = 130   # 2:10/km — record mondiale uomo è ~2:50/km su pista
PACE_MAX_S_PER_KM = 1200  # 20:00/km — più lento è camminata/passo

# Durata sessione (secondi)
DURATION_MIN_S = 60         # 1 minuto — sotto è probabile errore Garmin
DURATION_MAX_S = 18 * 3600  # 18 ore — ultra endurance estremo

# Distanza
DISTANCE_MIN_M = 100        # 100m — sotto è errore
DISTANCE_MAX_M = 500_000    # 500km — ultra estremo

# Power (W) — solo bici
POWER_MIN_W = 0
POWER_MAX_W = 2500   # sprint elite ~2000W picco

# TSS plausibile per singola sessione
TSS_MIN = 0
TSS_MAX = 600        # gara Ironman ~350-450 TSS

# Wellness
SLEEP_SCORE_MIN = 0
SLEEP_SCORE_MAX = 100
HRV_RMSSD_MIN = 5    # ms — molto basso ma non impossibile
HRV_RMSSD_MAX = 200  # ms — atleti elite parasimpatici
RESTING_HR_MIN = 25
RESTING_HR_MAX = 120


@dataclass
class ValidationResult:
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def reject(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)


# ============================================================================
# Activity validation
# ============================================================================

def validate_activity(act: dict[str, Any]) -> ValidationResult:
    """Verifica plausibility di una activity prima dell'insert.

    Reject bloccanti:
    - duration < 60s o > 18h
    - distance < 100m (per sport endurance) o > 500km
    - HR > 230 o HR < 30
    - avg_hr > max_hr (cross-field)
    - power > 2500W

    Warning non bloccanti:
    - pace impossibile o estremamente lento
    - TSS > 600
    - missing critical fields
    """
    r = ValidationResult()
    sport = act.get("sport", "unknown")

    # Duration
    duration_s = act.get("duration_s")
    if duration_s is None:
        r.warn("duration_s missing")
    elif duration_s < DURATION_MIN_S:
        r.reject(f"duration_s={duration_s}s troppo bassa (< {DURATION_MIN_S}s)")
    elif duration_s > DURATION_MAX_S:
        r.reject(f"duration_s={duration_s}s impossibile (> {DURATION_MAX_S}s)")

    # Distance (solo per endurance — strength può non averla)
    distance_m = act.get("distance_m")
    if sport in {"run", "bike", "swim", "brick"} and distance_m is not None:
        if distance_m < DISTANCE_MIN_M:
            r.reject(f"distance_m={distance_m}m troppo bassa per {sport}")
        elif distance_m > DISTANCE_MAX_M:
            r.reject(f"distance_m={distance_m}m impossibile (> {DISTANCE_MAX_M}m)")

    # Heart rate
    avg_hr = act.get("avg_hr")
    max_hr = act.get("max_hr")
    if avg_hr is not None:
        if avg_hr < HR_MIN or avg_hr > HR_MAX:
            r.reject(f"avg_hr={avg_hr} fuori range [{HR_MIN}, {HR_MAX}]")
    if max_hr is not None:
        if max_hr < HR_MIN or max_hr > HR_MAX:
            r.reject(f"max_hr={max_hr} fuori range [{HR_MIN}, {HR_MAX}]")

    # Cross-field: avg_hr <= max_hr
    if avg_hr is not None and max_hr is not None and avg_hr > max_hr:
        r.reject(f"avg_hr={avg_hr} > max_hr={max_hr} (incoerente)")

    # Pace (s/km) — solo run e brick parte run
    pace = act.get("avg_pace_s_per_km")
    if pace is not None and sport in {"run", "brick"}:
        if pace < PACE_MIN_S_PER_KM:
            r.warn(f"avg_pace_s_per_km={pace} super-umano (<{PACE_MIN_S_PER_KM}s/km)")
        elif pace > PACE_MAX_S_PER_KM:
            r.warn(f"avg_pace_s_per_km={pace} estremamente lento (>{PACE_MAX_S_PER_KM}s/km)")

    # Power
    avg_power = act.get("avg_power_w")
    max_power = act.get("max_power_w")
    np_w = act.get("np_w")
    if avg_power is not None and avg_power > POWER_MAX_W:
        r.reject(f"avg_power_w={avg_power} impossibile (> {POWER_MAX_W}W)")
    if max_power is not None and max_power > POWER_MAX_W:
        r.reject(f"max_power_w={max_power} impossibile (> {POWER_MAX_W}W)")
    if avg_power is not None and max_power is not None and avg_power > max_power:
        r.reject(f"avg_power_w={avg_power} > max_power_w={max_power} (incoerente)")
    if np_w is not None and avg_power is not None and np_w > max_power if max_power else False:
        r.warn(f"np_w={np_w} > max_power_w={max_power} (anomalo)")

    # TSS
    tss = act.get("tss")
    if tss is not None and (tss < TSS_MIN or tss > TSS_MAX):
        r.warn(f"tss={tss} fuori range plausibile [{TSS_MIN}, {TSS_MAX}]")

    return r


# ============================================================================
# Wellness validation
# ============================================================================

def validate_wellness(w: dict[str, Any]) -> ValidationResult:
    """Verifica plausibility di una daily_wellness row prima dell'insert."""
    r = ValidationResult()

    sleep_score = w.get("sleep_score")
    if sleep_score is not None and (sleep_score < SLEEP_SCORE_MIN or sleep_score > SLEEP_SCORE_MAX):
        r.reject(f"sleep_score={sleep_score} fuori range [0, 100]")

    hrv = w.get("hrv_rmssd")
    if hrv is not None and (hrv < HRV_RMSSD_MIN or hrv > HRV_RMSSD_MAX):
        r.warn(f"hrv_rmssd={hrv} fuori range plausibile [{HRV_RMSSD_MIN}, {HRV_RMSSD_MAX}]")

    rhr = w.get("resting_hr")
    if rhr is not None and (rhr < RESTING_HR_MIN or rhr > RESTING_HR_MAX):
        r.warn(f"resting_hr={rhr} fuori range plausibile [{RESTING_HR_MIN}, {RESTING_HR_MAX}]")

    sleep_total = w.get("sleep_total_s")
    if sleep_total is not None:
        if sleep_total < 0:
            r.reject(f"sleep_total_s={sleep_total} negativo")
        elif sleep_total > 16 * 3600:
            r.warn(f"sleep_total_s={sleep_total} > 16h (anomalo)")

    return r
