"""Readiness score composito + flag deterministici.

Tutto codificato qui, MAI giudizio LLM. L'agente legge l'output di queste funzioni
e le comunica, non le ricalcola.

Filosofia:
- Score 0-100 composto da fattori pesati (HRV, sonno, soggettivo, TSB)
- Flag binari per condizioni di sicurezza (fatigue, illness, injury)
- Output deterministico → testabile → affidabile
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


# Soglie codificate (rispecchiano CLAUDE.md §5)
HRV_WARNING_Z = -1.0
HRV_CRITICAL_Z = -2.0
HRV_WARNING_CONSECUTIVE_DAYS = 2
TSB_DEEP_NEGATIVE = -25.0
SLEEP_LOW_SCORE = 60


@dataclass
class WellnessHistory:
    """Storia recente per calcolo readiness."""
    hrv_today: Optional[float]
    hrv_history_28d: list[float]  # ordinato cronologicamente, può avere None? No: già filtrato
    hrv_recent_z_scores: list[float]  # ultimi N giorni di z-score per detect consecutive
    sleep_score_today: Optional[int]
    sleep_avg_7d: Optional[float]
    body_battery_morning: Optional[int]
    resting_hr_today: Optional[int]
    resting_hr_baseline: Optional[float]


@dataclass
class TrainingState:
    ctl: float
    atl: float
    tsb: float
    days_since_hard_session: Optional[int]


@dataclass
class SubjectiveState:
    motivation: Optional[int]   # 1-10
    soreness: Optional[int]      # 0-10
    illness_flag: bool
    injury_flag: bool
    illness_recent_days: int = 0  # giorni dall'ultimo flag malattia


@dataclass
class ReadinessReport:
    score: int                       # 0-100
    label: str                       # ready / caution / rest
    factors: dict[str, int]          # contributo per fattore
    flags: list[str]
    rationale: str                   # spiegazione human-readable per brief


# ============================================================================
# HRV z-score
# ============================================================================
def hrv_z_score(hrv_today: float, history: list[float]) -> Optional[float]:
    """Z-score di HRV oggi vs baseline rolling.

    Richiede almeno 7 valori storici per essere significativo.
    """
    if len(history) < 7 or hrv_today is None:
        return None
    mean = statistics.fmean(history)
    sd = statistics.pstdev(history) if len(history) > 1 else 0.0
    if sd == 0:
        return 0.0
    return (hrv_today - mean) / sd


# ============================================================================
# Flag deterministici
# ============================================================================
def compute_flags(
    wellness: WellnessHistory,
    training: TrainingState,
    subjective: SubjectiveState,
) -> list[str]:
    """Applica regole §5 di CLAUDE.md."""
    flags: list[str] = []

    # HRV
    if wellness.hrv_today is not None and wellness.hrv_history_28d:
        z = hrv_z_score(wellness.hrv_today, wellness.hrv_history_28d)
        if z is not None:
            if z <= HRV_CRITICAL_Z:
                flags.append("fatigue_critical")
            elif z <= HRV_WARNING_Z:
                # Consecutive check
                consecutive = sum(
                    1 for past_z in wellness.hrv_recent_z_scores[-HRV_WARNING_CONSECUTIVE_DAYS:]
                    if past_z is not None and past_z <= HRV_WARNING_Z
                )
                if consecutive >= HRV_WARNING_CONSECUTIVE_DAYS - 1:  # -1 perché oggi non è in history
                    flags.append("fatigue_warning")

        # Trend negativo: media 7d sotto baseline 28d > 5%
        if len(wellness.hrv_history_28d) >= 28:
            recent_7 = wellness.hrv_history_28d[-7:]
            baseline_28 = statistics.fmean(wellness.hrv_history_28d)
            if statistics.fmean(recent_7) < baseline_28 * 0.95:
                flags.append("trend_negative")

    # TSB profondo + trend negativo → anticipa scarico
    if "trend_negative" in flags and training.tsb < TSB_DEEP_NEGATIVE:
        flags.append("anticipate_recovery_week")

    # Soggettivo
    if subjective.illness_flag:
        flags.append("illness_flag")
    if subjective.injury_flag:
        flags.append("injury_flag")
    if subjective.soreness is not None and subjective.soreness >= 7:
        flags.append("high_soreness")
    if subjective.motivation is not None and subjective.motivation <= 3:
        flags.append("low_motivation")

    # Recovery debt: malato da poco
    if subjective.illness_recent_days > 0 and subjective.illness_recent_days < 3:
        flags.append("post_illness_caution")

    return flags


# ============================================================================
# Readiness score
# ============================================================================
def _score_hrv(wellness: WellnessHistory) -> int:
    """0-100 da z-score HRV. Z=0 → 70, Z>+1 → 100, Z<-2 → 20."""
    if wellness.hrv_today is None or not wellness.hrv_history_28d:
        return 50  # neutral
    z = hrv_z_score(wellness.hrv_today, wellness.hrv_history_28d)
    if z is None:
        return 50
    # Mapping lineare clamped
    score = 70 + int(z * 15)
    return max(0, min(100, score))


def _score_sleep(wellness: WellnessHistory) -> int:
    if wellness.sleep_score_today is not None:
        return wellness.sleep_score_today
    return 50


def _score_tsb(training: TrainingState) -> int:
    """TSB ottimale per allenarsi: -10 a +5 (carico ma non distrutto).
    Troppo positivo = decondizionato; troppo negativo = sovraccarico.
    """
    tsb = training.tsb
    if tsb is None:
        return 50  # neutral: nessun dato PMC disponibile
    if -10 <= tsb <= 5:
        return 100
    elif -20 <= tsb < -10:
        return 80 - int(abs(tsb + 10) * 3)  # 80 → 50
    elif tsb < -20:
        return max(0, 50 - int(abs(tsb + 20) * 2))
    elif 5 < tsb <= 15:
        return 90 - int((tsb - 5) * 2)
    else:  # tsb > 15
        return max(40, 70 - int((tsb - 15)))


def _score_subjective(subjective: SubjectiveState) -> int:
    factors = []
    if subjective.motivation is not None:
        factors.append(subjective.motivation * 10)
    if subjective.soreness is not None:
        factors.append(100 - subjective.soreness * 10)
    if not factors:
        return 70  # default neutral-positive
    return int(statistics.fmean(factors))


def compute_readiness(
    wellness: WellnessHistory,
    training: TrainingState,
    subjective: SubjectiveState,
) -> ReadinessReport:
    """Score composito + label + flags + rationale."""
    flags = compute_flags(wellness, training, subjective)

    # Hard overrides
    if "fatigue_critical" in flags or "illness_flag" in flags or "injury_flag" in flags:
        return ReadinessReport(
            score=15,
            label="rest",
            factors={"override": 0},
            flags=flags,
            rationale=_build_rationale(flags, override="rest"),
        )

    if "fatigue_warning" in flags or "post_illness_caution" in flags:
        # Cap massimo a 60
        cap = 60
    else:
        cap = 100

    factors = {
        "hrv": _score_hrv(wellness),
        "sleep": _score_sleep(wellness),
        "tsb": _score_tsb(training),
        "subjective": _score_subjective(subjective),
    }

    # Pesi: HRV pesa di più, soggettivo è correttivo
    weights = {"hrv": 0.35, "sleep": 0.25, "tsb": 0.20, "subjective": 0.20}
    score = sum(factors[k] * weights[k] for k in factors)
    score = min(cap, int(round(score)))

    if score >= 75:
        label = "ready"
    elif score >= 50:
        label = "caution"
    else:
        label = "rest"

    return ReadinessReport(
        score=score,
        label=label,
        factors=factors,
        flags=flags,
        rationale=_build_rationale(flags, factors=factors, score=score),
    )


def _build_rationale(
    flags: list[str],
    factors: Optional[dict[str, int]] = None,
    score: Optional[int] = None,
    override: Optional[str] = None,
) -> str:
    parts = []
    if override == "rest":
        if "fatigue_critical" in flags:
            parts.append("HRV crash (z<-2): recovery oggi.")
        if "illness_flag" in flags:
            parts.append("Flag malattia attivo: stop intensità.")
        if "injury_flag" in flags:
            parts.append("Flag infortunio attivo: stop disciplina coinvolta.")
        return " ".join(parts) or "Override sicurezza."

    if factors:
        weakest = min(factors, key=factors.get)
        if factors[weakest] < 60:
            labels = {"hrv": "HRV bassa", "sleep": "sonno povero", "tsb": "TSB stressante", "subjective": "soggettivo basso"}
            parts.append(f"Limite: {labels.get(weakest, weakest)} ({factors[weakest]}).")

    if "fatigue_warning" in flags:
        parts.append("HRV in calo da 2 giorni: rimodulare oggi.")
    if "trend_negative" in flags:
        parts.append("Trend HRV 7d sotto baseline 28d.")
    if "anticipate_recovery_week" in flags:
        parts.append("Suggerito anticipo settimana di scarico.")

    if not parts and score is not None and score >= 75:
        parts.append("Tutti gli indicatori OK: green light.")

    return " ".join(parts) or f"Score {score}."
