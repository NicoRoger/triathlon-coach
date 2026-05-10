from __future__ import annotations

import pytest

from coach.utils.llm_policy import (
    LLMDisabledError,
    check_purpose_allowed,
    get_allowed_purposes,
    is_purpose_allowed,
)


def test_quality_mode_keeps_high_value_purposes(monkeypatch):
    monkeypatch.delenv("COACH_LLM_MODE", raising=False)
    monkeypatch.delenv("COACH_LLM_ENABLED_PURPOSES", raising=False)
    monkeypatch.delenv("COACH_LLM_DISABLED_PURPOSES", raising=False)

    assert is_purpose_allowed("weekly_review")
    assert is_purpose_allowed("race_briefing")
    assert is_purpose_allowed("pattern_extraction")
    assert not is_purpose_allowed("session_analysis")
    assert not is_purpose_allowed("modulation_proposal")
    assert not is_purpose_allowed("weekly_review_lesson")


def test_full_mode_allows_automation_purposes(monkeypatch):
    monkeypatch.setenv("COACH_LLM_MODE", "full")
    assert is_purpose_allowed("session_analysis")
    assert is_purpose_allowed("modulation_proposal")
    assert is_purpose_allowed("weekly_review_lesson")


def test_minimal_mode_disables_pattern_extraction(monkeypatch):
    monkeypatch.setenv("COACH_LLM_MODE", "minimal")
    assert is_purpose_allowed("weekly_review")
    assert not is_purpose_allowed("pattern_extraction")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("COACH_LLM_MODE", "minimal")
    monkeypatch.setenv("COACH_LLM_ENABLED_PURPOSES", "session_analysis")
    monkeypatch.setenv("COACH_LLM_DISABLED_PURPOSES", "weekly_review")

    allowed = get_allowed_purposes()
    assert "session_analysis" in allowed
    assert "weekly_review" not in allowed


def test_check_purpose_allowed_raises(monkeypatch):
    monkeypatch.setenv("COACH_LLM_MODE", "quality")
    with pytest.raises(LLMDisabledError):
        check_purpose_allowed("session_analysis")


def test_disabled_purpose_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("COACH_LLM_MODE", "quality")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from coach.utils.llm_client import get_client

    with pytest.raises(LLMDisabledError):
        get_client().call(
            purpose="session_analysis",
            system="test",
            messages=[{"role": "user", "content": "test"}],
        )
