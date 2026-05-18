"""Fase 4.3 — Uncertainty Framework.

Recommendation object standard usato da TUTTI i moduli che producono
recommendation (briefing, weekly_review consumer, modulation, priority_engine).

Confidence MAI arbitraria: deriva da sample size, recency, consistency,
sensor reliability, plausibility, outcome accuracy.

Hard rules:
- n < 3 → exploratory only (confidence ≤ 0.4, mai prescrittivo)
- n < 5 → confidence ceiling 0.5
- missing HRV > 40% → confidence penalty -0.15
- contradictory evidence → confidence decay (Bayesian, vedi belief_engine)
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Recommendation object standard
# ============================================================================

@dataclass
class Recommendation:
    """Standard object per qualsiasi recommendation del sistema (Fase 4.3)."""

    recommendation: str
    confidence: float                              # 0-1 (post hard-rules clamp)
    evidence_n: Optional[int] = None
    evidence_quality: str = "moderate"             # weak | moderate | strong
    data_coverage: Optional[float] = None          # 0-1, % feature presenti
    uncertainty_drivers: list[str] = field(default_factory=list)
    blind_spots: list[str] = field(default_factory=list)
    source_module: str = "unknown"
    beliefs_used: list[str] = field(default_factory=list)     # UUID stringhe
    citations: list[dict] = field(default_factory=list)        # [{source, topic}]
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Apply hard rules at construction time
        self.confidence = _clamp_confidence(self.confidence, self.evidence_n,
                                            self.data_coverage)
        # Coerenza evidence_quality con evidence_n
        if self.evidence_n is not None:
            if self.evidence_n < 3 and self.evidence_quality == "strong":
                logger.warning("evidence_quality=strong with n<3 → demoting to weak")
                self.evidence_quality = "weak"
            elif self.evidence_n < 5 and self.evidence_quality == "strong":
                self.evidence_quality = "moderate"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_brief_line(self, show_confidence: bool = True, show_blind_spots: bool = False) -> str:
        """Versione human-readable per brief Telegram."""
        parts = [self.recommendation]
        if show_confidence:
            pct = int(self.confidence * 100)
            parts.append(f"(confidence {pct}%)")
        if show_blind_spots and self.blind_spots:
            top = self.blind_spots[0]
            parts.append(f"⚠️ {top}")
        return " ".join(parts)


# ============================================================================
# Confidence hard rules (Fase 4.3)
# ============================================================================

CONFIDENCE_CEILING_LOW_N = 0.5
CONFIDENCE_CEILING_EXPLORATORY = 0.4
MIN_N_FOR_PRESCRIPTIVE = 5
MIN_N_FOR_HIGH_CONFIDENCE = 8
HRV_MISSING_PENALTY = 0.15
DATA_COVERAGE_PENALTY_THRESHOLD = 0.6
DATA_COVERAGE_PENALTY = 0.10


def _clamp_confidence(raw: float, n: Optional[int],
                      data_coverage: Optional[float]) -> float:
    """Applica hard rules su confidence raw → confidence reale post-clamp."""
    if raw is None:
        return 0.0
    c = max(0.0, min(1.0, raw))

    # n-based ceilings
    if n is not None:
        if n < 3:
            c = min(c, CONFIDENCE_CEILING_EXPLORATORY)
        elif n < MIN_N_FOR_PRESCRIPTIVE:
            c = min(c, CONFIDENCE_CEILING_LOW_N)

    # Data coverage penalty (es. HRV mancante)
    if data_coverage is not None and data_coverage < DATA_COVERAGE_PENALTY_THRESHOLD:
        c = max(0.0, c - DATA_COVERAGE_PENALTY)

    return round(c, 3)


# ============================================================================
# Confidence sources — funzioni helper per derivare confidence da dati reali
# ============================================================================

def confidence_from_evidence(
    n: int,
    consistency: Optional[float] = None,
    recency_days: Optional[int] = None,
    data_coverage: Optional[float] = None,
    base_confidence: float = 0.5,
) -> float:
    """Combina sample size + consistency + recency in confidence singolo.

    Args:
        n: number of supporting observations
        consistency: 0-1, 1 = osservazioni molto coerenti (low variance)
        recency_days: giorni dall'ultima evidenza (più recente = più alta conf)
        data_coverage: 0-1, frazione di feature disponibili
        base_confidence: punto di partenza prima di aggiustamenti

    Returns:
        Confidence finale clamped 0-1, con hard rules applicate.
    """
    c = base_confidence

    # Sample size gain (cresce sublineare, saturazione a n=20)
    if n >= 2:
        c += min(0.30, 0.06 * (n - 1) ** 0.6)

    # Consistency boost
    if consistency is not None:
        c += (consistency - 0.5) * 0.20  # ±0.10 da consistency 0-1

    # Recency decay (se >120gg, penalità)
    if recency_days is not None and recency_days > 120:
        decay_factor = 0.5 ** ((recency_days - 120) / 120)
        c *= max(0.5, decay_factor)

    return _clamp_confidence(c, n, data_coverage)


def compute_data_coverage(features_present: int, features_total: int) -> float:
    """Frazione feature disponibili (es. 5 HRV su 7 giorni → 0.71)."""
    if features_total == 0:
        return 0.0
    return round(features_present / features_total, 3)


def compute_consistency(values: list[float]) -> float:
    """0-1: 1 = bassa varianza relativa, 0 = alta varianza.

    Usa coefficient of variation (CV = stddev/mean) invertito.
    """
    if len(values) < 2:
        return 0.5
    mean = statistics.mean(values)
    if mean == 0:
        return 0.5
    stddev = statistics.stdev(values)
    cv = abs(stddev / mean)
    # CV 0.1 = molto consistente (consistency 0.9); CV >0.5 = poco consistente (0.2)
    consistency = max(0.0, min(1.0, 1.0 - cv * 1.5))
    return round(consistency, 3)


# ============================================================================
# Persistence
# ============================================================================

def record_recommendation(rec: Recommendation,
                          source_module: Optional[str] = None,
                          winning_priority: Optional[int] = None,
                          overridden_priorities: Optional[list[int]] = None,
                          priority_reason: Optional[str] = None,
                          tradeoffs: Optional[dict] = None,
                          related_prediction_ids: Optional[list[str]] = None) -> str:
    """Salva una Recommendation in DB. Ritorna id."""
    sb = get_supabase()
    if source_module:
        rec.source_module = source_module

    row = {
        "source_module": rec.source_module,
        "recommendation": rec.recommendation,
        "confidence": rec.confidence,
        "evidence_n": rec.evidence_n,
        "evidence_quality": rec.evidence_quality,
        "data_coverage": rec.data_coverage,
        "uncertainty_drivers": rec.uncertainty_drivers or None,
        "blind_spots": rec.blind_spots or None,
        "winning_priority": winning_priority,
        "overridden_priorities": overridden_priorities or [],
        "priority_reason": priority_reason,
        "tradeoffs": tradeoffs,
        "beliefs_used": rec.beliefs_used or [],
        "citations": rec.citations or None,
        "related_prediction_ids": related_prediction_ids or [],
        "metadata": rec.metadata or None,
    }
    row = {k: v for k, v in row.items() if v is not None}
    res = sb.table("recommendations").insert(row).execute()
    rid = res.data[0]["id"]
    logger.info("Recommendation logged: source=%s conf=%.2f id=%s",
                rec.source_module, rec.confidence, rid)
    return rid


# ============================================================================
# Recommendation builder helpers
# ============================================================================

def low_confidence_recommendation(
    text: str,
    reason: str,
    source_module: str,
    blind_spots: Optional[list[str]] = None,
) -> Recommendation:
    """Recommendation forced low-confidence (≤0.4): dati insufficienti."""
    return Recommendation(
        recommendation=text,
        confidence=0.3,
        evidence_n=0,
        evidence_quality="weak",
        uncertainty_drivers=[reason],
        blind_spots=blind_spots or [],
        source_module=source_module,
    )


def high_confidence_recommendation(
    text: str,
    n: int,
    citations: Optional[list[dict]] = None,
    source_module: str = "unknown",
    blind_spots: Optional[list[str]] = None,
) -> Recommendation:
    """Recommendation high-confidence: serve n>=8."""
    if n < MIN_N_FOR_HIGH_CONFIDENCE:
        logger.warning("high_confidence_recommendation called with n=%d (<%d)",
                       n, MIN_N_FOR_HIGH_CONFIDENCE)
    return Recommendation(
        recommendation=text,
        confidence=0.85,
        evidence_n=n,
        evidence_quality="strong",
        citations=citations or [],
        blind_spots=blind_spots or [],
        source_module=source_module,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Demo: produce 3 recommendation con confidence differenti
    r1 = Recommendation(
        recommendation="Riduci volume del 15% questa settimana",
        confidence=0.75,
        evidence_n=2,  # Forza ceiling
        source_module="demo",
    )
    print("Low-n auto-clamp:", r1.confidence)  # Dovrebbe essere 0.4
    print(json.dumps(r1.to_dict(), indent=2))


if __name__ == "__main__":
    main()
