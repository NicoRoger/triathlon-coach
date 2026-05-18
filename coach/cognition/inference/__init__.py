"""Inference layer: interpretazione pattern e beliefs.

Re-export:
- belief_engine: Bayesian belief storage + lifecycle
- belief_guardrails: anti-overfitting
- pattern_extraction: estrazione pattern longitudinali
- uncertainty: recommendation object standard
"""

from coach.analytics.belief_engine import (
    Belief,
    create_belief,
    reinforce_belief,
    contradict_belief,
    list_beliefs,
    get_actionable_beliefs,
    decay_old_beliefs,
)
from coach.analytics.belief_guardrails import (
    check_belief_admissible,
    is_belief_actionable_for_priority_engine,
)
from coach.analytics.uncertainty import (
    Recommendation,
    confidence_from_evidence,
    compute_data_coverage,
    compute_consistency,
    record_recommendation,
    low_confidence_recommendation,
    high_confidence_recommendation,
)

__all__ = [
    "Belief",
    "create_belief",
    "reinforce_belief",
    "contradict_belief",
    "list_beliefs",
    "get_actionable_beliefs",
    "decay_old_beliefs",
    "check_belief_admissible",
    "is_belief_actionable_for_priority_engine",
    "Recommendation",
    "confidence_from_evidence",
    "compute_data_coverage",
    "compute_consistency",
    "record_recommendation",
    "low_confidence_recommendation",
    "high_confidence_recommendation",
]
