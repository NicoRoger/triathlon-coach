"""Fase 2.5 — Probabilistic risk modeling.

Modelli rule-based (no LLM) per quantificare 3 rischi chiave:
- Overreaching (eccesso carico vs capacità)
- Injury (probabilità infortunio nel prossimo 7-14gg)
- Recovery deficit (recupero insufficiente)

Ogni modello ritorna `RiskScore`:
    {value: 0.0-1.0, level: 'low'|'moderate'|'high'|'critical', factors: [...]}

Output usato in briefing.py per warning proattivi e nella weekly review come
input al priority engine (Fase 4).

Approccio: combinazione lineare di feature normalizzate con pesi calibrati
sulle best practices (Gabbett ACWR, Seiler intensity distribution, ecc.).
La calibrazione fine viene affinata via outcome_verification + beliefs.

Soglie default (alert quando supera):
- LOW < 0.25
- MODERATE 0.25-0.5
- HIGH 0.5-0.75 -> alert proattivo Telegram + suggerisce modulation
- CRITICAL > 0.75 -> alert + recovery obbligatorio in brief
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Soglie e pesi
# ============================================================================

# Risk levels
LEVEL_LOW = 0.25
LEVEL_MODERATE = 0.50
LEVEL_HIGH = 0.75

# ACWR sweet spot (Gabbett 2016): 0.8-1.3 sicuro, > 1.5 zona rischio
ACWR_SAFE_LOW = 0.8
ACWR_SAFE_HIGH = 1.3
ACWR_DANGER = 1.5


@dataclass
class RiskScore:
    """Risultato di un risk model."""

    value: float           # 0.0 to 1.0
    level: str             # low / moderate / high / critical
    factors: list[str] = field(default_factory=list)
    raw_inputs: dict = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: float, factors: Optional[list[str]] = None,
                   raw_inputs: Optional[dict] = None) -> "RiskScore":
        v = max(0.0, min(1.0, value))
        return cls(
            value=round(v, 3),
            level=_classify(v),
            factors=factors or [],
            raw_inputs=raw_inputs or {},
        )

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "level": self.level,
            "factors": self.factors,
            "raw_inputs": self.raw_inputs,
        }


def _classify(v: float) -> str:
    if v < LEVEL_LOW:
        return "low"
    if v < LEVEL_MODERATE:
        return "moderate"
    if v < LEVEL_HIGH:
        return "high"
    return "critical"


# ============================================================================
# Data loaders
# ============================================================================

def _load_metrics(days: int = 28) -> list[dict]:
    sb = get_supabase()
    since = (today_rome() - timedelta(days=days)).isoformat()
    res = (
        sb.table("daily_metrics")
        .select("date,ctl,atl,tsb,daily_tss,hrv_z_score,readiness_score,flags")
        .gte("date", since)
        .order("date", desc=False)
        .execute()
    )
    return res.data or []


def _load_recent_activities(days: int = 7) -> list[dict]:
    sb = get_supabase()
    since = (today_rome() - timedelta(days=days)).isoformat()
    res = (
        sb.table("activities")
        .select("started_at,sport,tss,duration_s")
        .gte("started_at", f"{since}T00:00:00Z")
        .order("started_at", desc=True)
        .execute()
    )
    return res.data or []


def _load_recent_subjective(days: int = 14) -> list[dict]:
    sb = get_supabase()
    since = (today_rome() - timedelta(days=days)).isoformat()
    res = (
        sb.table("subjective_log")
        .select("logged_at,kind,rpe,soreness,injury_flag,illness_flag,severity")
        .gte("logged_at", since)
        .order("logged_at", desc=True)
        .execute()
    )
    return res.data or []


# ============================================================================
# Risk: overreaching
# ============================================================================

def compute_overreaching_risk() -> RiskScore:
    """Rischio overreaching basato su:

    - ACWR (acute:chronic workload ratio)
    - TSB profondamente negativo (< -25)
    - HRV trend in calo (z-score < -1 per 2+ giorni)
    - RPE medio recente > 7

    Pesi: 0.35 ACWR, 0.25 TSB, 0.25 HRV, 0.15 RPE.
    """
    metrics = _load_metrics(28)
    subjective = _load_recent_subjective(7)
    factors: list[str] = []
    raw: dict = {}

    if not metrics:
        return RiskScore.from_value(0.0, ["insufficient data"], {})

    # ACWR from daily_tss (acute 7gg / chronic 28gg)
    last_7 = metrics[-7:] if len(metrics) >= 7 else metrics
    last_28 = metrics
    acute_tss = sum((m.get("daily_tss") or 0) for m in last_7) / max(len(last_7), 1)
    chronic_tss = sum((m.get("daily_tss") or 0) for m in last_28) / max(len(last_28), 1)
    acwr = (acute_tss / chronic_tss) if chronic_tss > 0 else None
    raw["acwr"] = round(acwr, 2) if acwr is not None else None

    acwr_score = 0.0
    if acwr is not None:
        if acwr > ACWR_DANGER:
            acwr_score = 1.0
            factors.append(f"ACWR={acwr:.2f} > {ACWR_DANGER} (zona rischio)")
        elif acwr > ACWR_SAFE_HIGH:
            acwr_score = (acwr - ACWR_SAFE_HIGH) / (ACWR_DANGER - ACWR_SAFE_HIGH)
            factors.append(f"ACWR={acwr:.2f} elevato (sweet spot 0.8-1.3)")
        elif acwr < ACWR_SAFE_LOW:
            # Carico troppo basso: NON overreaching (è detraining)
            acwr_score = 0.0

    # TSB
    last_tsb = metrics[-1].get("tsb") if metrics else None
    tsb_score = 0.0
    raw["tsb"] = last_tsb
    if last_tsb is not None:
        if last_tsb < -40:
            tsb_score = 1.0
            factors.append(f"TSB={last_tsb} profondamente negativo")
        elif last_tsb < -25:
            tsb_score = (-(last_tsb) - 25) / 15
            factors.append(f"TSB={last_tsb} sotto -25")

    # HRV trend: media z-score ultimi 5gg
    hrv_recent = [m.get("hrv_z_score") for m in metrics[-5:] if m.get("hrv_z_score") is not None]
    hrv_score = 0.0
    if hrv_recent:
        avg_hrv = sum(hrv_recent) / len(hrv_recent)
        raw["hrv_z_avg_5d"] = round(avg_hrv, 2)
        if avg_hrv < -1.5:
            hrv_score = 1.0
            factors.append(f"HRV z-score medio {avg_hrv:.1f} (crash)")
        elif avg_hrv < -0.5:
            hrv_score = (-(avg_hrv) - 0.5) / 1.0
            factors.append(f"HRV z-score medio {avg_hrv:.1f} in calo")

    # RPE medio recente
    rpe_values = [s.get("rpe") for s in subjective if s.get("rpe")]
    rpe_score = 0.0
    if rpe_values:
        avg_rpe = sum(rpe_values) / len(rpe_values)
        raw["rpe_avg_7d"] = round(avg_rpe, 1)
        if avg_rpe > 8:
            rpe_score = 1.0
            factors.append(f"RPE medio {avg_rpe:.1f} elevato")
        elif avg_rpe > 7:
            rpe_score = (avg_rpe - 7) / 1.0
            factors.append(f"RPE medio {avg_rpe:.1f} sopra norma")

    value = 0.35 * acwr_score + 0.25 * tsb_score + 0.25 * hrv_score + 0.15 * rpe_score
    return RiskScore.from_value(value, factors, raw)


# ============================================================================
# Risk: injury
# ============================================================================

def compute_injury_risk() -> RiskScore:
    """Rischio infortunio basato su:

    - Volume jump > 10% settimana (Gabbett rule)
    - Injury flag/severity attivi
    - Soreness alta ricorrente
    - History infortuni recenti (60gg)

    Pesi: 0.35 volume jump, 0.30 injury active, 0.20 soreness, 0.15 history.
    """
    metrics = _load_metrics(28)
    activities = _load_recent_activities(14)
    subjective = _load_recent_subjective(60)
    factors: list[str] = []
    raw: dict = {}

    # Volume jump: this week vs last week (minuti totali)
    today = today_rome()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    this_week_min = sum(
        (a.get("duration_s") or 0) / 60 for a in activities
        if a.get("started_at", "")[:10] >= this_week_start.isoformat()
    )
    last_week_min = sum(
        (a.get("duration_s") or 0) / 60 for a in activities
        if last_week_start.isoformat() <= a.get("started_at", "")[:10] < this_week_start.isoformat()
    )
    raw["volume_this_week_min"] = round(this_week_min, 0)
    raw["volume_last_week_min"] = round(last_week_min, 0)

    volume_score = 0.0
    if last_week_min > 60:  # solo se settimana precedente significativa
        jump_pct = (this_week_min - last_week_min) / last_week_min * 100
        raw["volume_jump_pct"] = round(jump_pct, 1)
        if jump_pct > 25:
            volume_score = 1.0
            factors.append(f"Volume jump +{jump_pct:.0f}% vs settimana precedente")
        elif jump_pct > 10:
            volume_score = (jump_pct - 10) / 15
            factors.append(f"Volume jump +{jump_pct:.0f}% (sopra regola Gabbett 10%)")

    # Injury active (flag + severity)
    active_injuries = [s for s in subjective if s.get("injury_flag") and
                       _is_recent(s, days=14)]
    injury_active_score = 0.0
    if active_injuries:
        latest = active_injuries[0]
        sev = latest.get("severity")
        if sev == "severe":
            injury_active_score = 1.0
            factors.append("Infortunio severo attivo")
        elif sev == "moderate":
            injury_active_score = 0.7
            factors.append("Infortunio moderato attivo")
        elif sev == "mild":
            injury_active_score = 0.4
            factors.append("Fastidio lieve attivo")
        else:
            injury_active_score = 0.5
            factors.append("Flag infortunio attivo")
        raw["active_injury_severity"] = sev

    # Soreness alta (>=7) ricorrente
    high_soreness = [s for s in subjective if (s.get("soreness") or 0) >= 7 and _is_recent(s, days=14)]
    soreness_score = 0.0
    if len(high_soreness) >= 3:
        soreness_score = 1.0
        factors.append(f"Soreness alta ricorrente ({len(high_soreness)} episodi 14gg)")
    elif len(high_soreness) >= 1:
        soreness_score = 0.5
        factors.append(f"Soreness alta ({len(high_soreness)} episodi)")
    raw["high_soreness_n_14d"] = len(high_soreness)

    # History infortuni ultimi 60gg (atleta con storia recente = più cauto)
    history_injuries = [s for s in subjective if s.get("injury_flag")]
    history_score = min(len(history_injuries) / 5, 1.0)  # 5+ episodi = max
    raw["injury_history_60d"] = len(history_injuries)
    if history_injuries:
        factors.append(f"{len(history_injuries)} eventi infortunio ultimi 60gg")

    value = 0.35 * volume_score + 0.30 * injury_active_score + 0.20 * soreness_score + 0.15 * history_score
    return RiskScore.from_value(value, factors, raw)


# ============================================================================
# Risk: recovery deficit
# ============================================================================

def compute_recovery_risk() -> RiskScore:
    """Rischio recupero insufficiente basato su:

    - HRV deviation persistente (z < -1 per 3+ giorni)
    - Sleep score basso (< 70) ricorrente
    - TSB negativo senza scarico programmato
    - Readiness score basso

    Pesi: 0.30 HRV, 0.25 sleep, 0.25 TSB, 0.20 readiness.
    """
    metrics = _load_metrics(14)
    factors: list[str] = []
    raw: dict = {}

    if not metrics:
        return RiskScore.from_value(0.0, ["insufficient data"], {})

    # HRV deviation persistente
    hrv_last3 = [m.get("hrv_z_score") for m in metrics[-3:] if m.get("hrv_z_score") is not None]
    hrv_score = 0.0
    if len(hrv_last3) == 3:
        if all(v < -1 for v in hrv_last3):
            hrv_score = 1.0
            factors.append("HRV z<-1 per 3 giorni consecutivi")
        elif all(v < -0.5 for v in hrv_last3):
            hrv_score = 0.6
            factors.append("HRV in deviazione da 3 giorni")
        raw["hrv_z_last3"] = [round(v, 2) for v in hrv_last3]

    # Sleep: query daily_wellness
    sb = get_supabase()
    since = (today_rome() - timedelta(days=7)).isoformat()
    w_res = (
        sb.table("daily_wellness")
        .select("date,sleep_score")
        .gte("date", since)
        .order("date", desc=True)
        .execute()
    )
    sleep_scores = [w.get("sleep_score") for w in (w_res.data or []) if w.get("sleep_score") is not None]
    sleep_score_risk = 0.0
    if sleep_scores:
        avg_sleep = sum(sleep_scores) / len(sleep_scores)
        raw["sleep_score_avg_7d"] = round(avg_sleep, 1)
        if avg_sleep < 60:
            sleep_score_risk = 1.0
            factors.append(f"Sleep score medio {avg_sleep:.0f} basso")
        elif avg_sleep < 75:
            sleep_score_risk = (75 - avg_sleep) / 15
            factors.append(f"Sleep score medio {avg_sleep:.0f} subottimale")

    # TSB
    last_tsb = metrics[-1].get("tsb")
    tsb_score = 0.0
    if last_tsb is not None:
        if last_tsb < -30:
            tsb_score = 1.0
            factors.append(f"TSB={last_tsb} negativo profondo, recupero insufficiente")
        elif last_tsb < -15:
            tsb_score = (-(last_tsb) - 15) / 15
            factors.append(f"TSB={last_tsb} negativo")

    # Readiness
    last_readiness = metrics[-1].get("readiness_score")
    readiness_score_risk = 0.0
    if last_readiness is not None:
        raw["readiness_score"] = last_readiness
        if last_readiness < 40:
            readiness_score_risk = 1.0
            factors.append(f"Readiness {last_readiness}/100 critica")
        elif last_readiness < 60:
            readiness_score_risk = (60 - last_readiness) / 20
            factors.append(f"Readiness {last_readiness}/100 bassa")

    value = 0.30 * hrv_score + 0.25 * sleep_score_risk + 0.25 * tsb_score + 0.20 * readiness_score_risk
    return RiskScore.from_value(value, factors, raw)


# ============================================================================
# Public API
# ============================================================================

def compute_all_risks() -> dict[str, RiskScore]:
    """Calcola tutti i risk scores. Wrapper per briefing/weekly_review."""
    return {
        "overreaching": compute_overreaching_risk(),
        "injury": compute_injury_risk(),
        "recovery": compute_recovery_risk(),
    }


def risks_to_brief_lines(risks: dict[str, RiskScore], threshold: str = "high") -> list[str]:
    """Genera linee brief Telegram solo per i risk >= threshold (default 'high').

    Output esempio:
        '⚠️ Rischio overreaching: 62% (ACWR=1.42 elevato, RPE medio 7.4)'
    """
    threshold_value = {"low": LEVEL_LOW, "moderate": LEVEL_MODERATE, "high": LEVEL_HIGH}[threshold]
    icons = {"overreaching": "📈", "injury": "🩹", "recovery": "💤"}
    labels = {"overreaching": "overreaching", "injury": "infortunio", "recovery": "recupero insuff."}
    lines: list[str] = []
    for key, r in risks.items():
        if r.value >= threshold_value:
            top_factors = ", ".join(r.factors[:2]) if r.factors else "—"
            lines.append(
                f"{icons.get(key, '⚠️')} <b>Rischio {labels[key]}: {int(r.value*100)}%</b> ({r.level}). "
                f"{top_factors}."
            )
    return lines


# ============================================================================
# Helpers
# ============================================================================

def _is_recent(entry: dict, days: int) -> bool:
    """Checkk se logged_at è negli ultimi N giorni."""
    ts = entry.get("logged_at")
    if not ts:
        return False
    try:
        d = date.fromisoformat(ts[:10])
        return d >= (today_rome() - timedelta(days=days))
    except Exception:
        return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    risks = compute_all_risks()
    for key, r in risks.items():
        print(f"{key}: value={r.value} level={r.level}")
        for f in r.factors:
            print(f"  - {f}")
        print(f"  raw: {r.raw_inputs}")


if __name__ == "__main__":
    main()
