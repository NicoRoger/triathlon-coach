"""Decision layer (Fase 4 Cognitive MVP).

Espone:
    priority_engine.resolve_decision(...)

Tutte le decisioni strutturali (modulation, weekly_review, mesocycle adaptation,
recovery intervention) DEVONO passare per il priority engine.
"""
from coach.decision.priority_engine import (
    DecisionContext,
    DecisionOutcome,
    Priority,
    PRIORITY_NAMES,
    resolve_decision,
)

__all__ = [
    "DecisionContext",
    "DecisionOutcome",
    "Priority",
    "PRIORITY_NAMES",
    "resolve_decision",
]
