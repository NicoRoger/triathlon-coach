"""Policy centralizzata per decidere quando usare chiamate LLM.

Obiettivo: mantenere qualità sulle interazioni ad alto valore, evitando consumo
API su automazioni ricorrenti non necessarie.
"""
from __future__ import annotations

import os

from coach.utils.budget import BudgetExceededError


class LLMDisabledError(BudgetExceededError):
    """Raised when an LLM purpose is disabled by local policy."""


CORE_PURPOSES = {
    "weekly_review",
    "weekly_interactive",
    "race_briefing",
    "race_week_critical",
    "emergency",
    "fatigue_critical",
}

QUALITY_PURPOSES = CORE_PURPOSES | {
    "pattern_extraction",
}

FULL_PURPOSES = QUALITY_PURPOSES | {
    "session_analysis",
    "modulation_proposal",
    "weekly_review_lesson",
}


def get_llm_mode() -> str:
    """Return active LLM automation mode."""
    return os.environ.get("COACH_LLM_MODE", "quality").strip().lower()


def get_allowed_purposes(mode: str | None = None) -> set[str]:
    """Return purpose allow-list for the selected mode."""
    mode = (mode or get_llm_mode()).strip().lower()

    if mode in {"off", "none", "disabled"}:
        allowed: set[str] = set()
    elif mode in {"minimal", "core"}:
        allowed = set(CORE_PURPOSES)
    elif mode in {"full", "all"}:
        allowed = set(FULL_PURPOSES)
    else:
        allowed = set(QUALITY_PURPOSES)

    extra = _split_env("COACH_LLM_ENABLED_PURPOSES")
    disabled = _split_env("COACH_LLM_DISABLED_PURPOSES")
    return (allowed | extra) - disabled


def is_purpose_allowed(purpose: str, mode: str | None = None) -> bool:
    """Return True when a purpose may call an LLM."""
    return purpose in get_allowed_purposes(mode)


def check_purpose_allowed(purpose: str) -> None:
    """Raise if the purpose is disabled by policy."""
    if not is_purpose_allowed(purpose):
        mode = get_llm_mode()
        raise LLMDisabledError(
            f"LLM purpose '{purpose}' disabled by COACH_LLM_MODE={mode}. "
            "Override with COACH_LLM_ENABLED_PURPOSES if needed."
        )


def _split_env(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}
