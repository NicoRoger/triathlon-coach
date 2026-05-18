"""Prescription layer: azioni concrete del coach.

Re-export:
- priority_engine: arbitration gerarchica decisioni
- modulation: mid-week adjustments
- adaptive_planner: compliance + auto-adjustments
"""

from coach.decision.priority_engine import (
    DecisionContext,
    DecisionOutcome,
    Priority,
    PRIORITY_NAMES,
    resolve_decision,
)

try:
    from coach.coaching.modulation import (
        should_trigger_modulation,
        generate_modulation_proposal,
        propose_modulation,
    )
except ImportError:
    pass

try:
    from coach.coaching.adaptive_planner import generate_adjustments
except ImportError:
    pass

__all__ = [
    "DecisionContext",
    "DecisionOutcome",
    "Priority",
    "PRIORITY_NAMES",
    "resolve_decision",
    "should_trigger_modulation",
    "generate_modulation_proposal",
    "propose_modulation",
    "generate_adjustments",
]
