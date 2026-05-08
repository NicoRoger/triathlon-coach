"""Test budget cap system — Step 6.

Test obbligatori:
1. Budget cap simulato ($4.60) → declassa a Haiku
2. Budget exhausted ($4.85) → blocca non-emergency
3. Failover Sonnet → Haiku → blocked
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from coach.utils.budget import (
    BUDGET_BLOCKED,
    BUDGET_DEGRADED,
    BUDGET_OK,
    BUDGET_WARNING,
    BudgetExceededError,
    MODEL_IDS,
    check_budget_or_raise,
    estimate_cost,
    select_model,
)


class TestEstimateCost:
    def test_sonnet_cost(self):
        # 1000 input + 500 output tokens with Sonnet
        cost = estimate_cost("claude-sonnet-4-6", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000  # $0.0105
        assert abs(cost - expected) < 0.0001

    def test_haiku_cheaper(self):
        cost_sonnet = estimate_cost("sonnet", 1000, 500)
        cost_haiku = estimate_cost("haiku", 1000, 500)
        assert cost_haiku < cost_sonnet

    def test_unknown_model_uses_sonnet_pricing(self):
        cost = estimate_cost("unknown-model", 1000, 500)
        cost_sonnet = estimate_cost("sonnet", 1000, 500)
        assert cost == cost_sonnet


class TestSelectModel:
    def test_low_spend_respects_preference(self):
        assert select_model("sonnet", spend=0.50) == MODEL_IDS["sonnet"]
        assert select_model("haiku", spend=0.50) == MODEL_IDS["haiku"]
        assert select_model("opus", spend=0.50) == MODEL_IDS["opus"]

    def test_warning_still_respects(self):
        assert select_model("sonnet", spend=3.50) == MODEL_IDS["sonnet"]

    def test_degraded_downgrades_sonnet_to_haiku(self):
        """Test budget cap simulato: $4.10 → Sonnet declassato a Haiku."""
        assert select_model("sonnet", spend=4.10) == MODEL_IDS["haiku"]

    def test_degraded_downgrades_opus_to_sonnet(self):
        assert select_model("opus", spend=4.10) == MODEL_IDS["sonnet"]

    def test_blocked_forces_haiku(self):
        """Test budget cap $4.60 → tutto Haiku."""
        assert select_model("sonnet", spend=4.60) == MODEL_IDS["haiku"]
        assert select_model("opus", spend=4.60) == MODEL_IDS["haiku"]

    def test_exhausted_still_returns_haiku(self):
        """$4.85 → Haiku returned (but check_budget_or_raise will block)."""
        assert select_model("sonnet", spend=4.85) == MODEL_IDS["haiku"]


class TestCheckBudget:
    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_ok_level(self, mock_alert, mock_spend):
        mock_spend.return_value = 1.00
        level = check_budget_or_raise(0.10, "session_analysis")
        assert level == "OK"
        mock_alert.assert_not_called()

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_warning_level(self, mock_alert, mock_spend):
        mock_spend.return_value = 3.50
        level = check_budget_or_raise(0.10, "session_analysis")
        assert level == "WARNING"

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_degraded_level(self, mock_alert, mock_spend):
        """$4.10 + $0.10 = $4.20 → DEGRADED, alert sent."""
        mock_spend.return_value = 4.10
        level = check_budget_or_raise(0.10, "session_analysis")
        assert level == "DEGRADED"
        mock_alert.assert_called_once()

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_blocked_non_critical(self, mock_alert, mock_spend):
        """$4.55 + $0.10 → blocked non-critical."""
        mock_spend.return_value = 4.55
        level = check_budget_or_raise(0.10, "session_analysis")
        assert level == "BLOCKED_NON_CRITICAL"

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_exhausted_blocks_non_emergency(self, mock_alert, mock_spend):
        """Test budget exhausted: $4.85 → blocca tutto tranne emergency."""
        mock_spend.return_value = 4.85
        with pytest.raises(BudgetExceededError):
            check_budget_or_raise(0.10, "session_analysis")
        mock_alert.assert_called_once()

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_exhausted_allows_emergency(self, mock_alert, mock_spend):
        """$4.85 ma purpose=emergency → procede."""
        mock_spend.return_value = 4.85
        # Non dovrebbe raisare per emergency
        level = check_budget_or_raise(0.10, "emergency")
        assert level in ("OK", "WARNING", "DEGRADED", "BLOCKED_NON_CRITICAL")

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_failover_sonnet_haiku_blocked(self, mock_alert, mock_spend):
        """Test failover completo: Sonnet → Haiku → blocked."""
        # Step 1: low budget → Sonnet
        assert select_model("sonnet", spend=1.00) == MODEL_IDS["sonnet"]

        # Step 2: mid budget → Haiku
        assert select_model("sonnet", spend=4.20) == MODEL_IDS["haiku"]

        # Step 3: exhausted → blocked
        mock_spend.return_value = 4.90
        with pytest.raises(BudgetExceededError):
            check_budget_or_raise(0.10, "session_analysis")
