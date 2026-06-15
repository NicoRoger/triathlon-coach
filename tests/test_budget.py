"""Test budget cap system — Step 6.

Test obbligatori:
1. Budget cap simulato ($4.60) → declassa a Haiku
2. Budget exhausted ($4.85) → blocca non-emergency
3. Failover Sonnet → Haiku → blocked

Test VERIFY-06 (04-03):
4. select_model("sonnet", spend=4.00) → Haiku (soglia degrado esatta €4.00)
5. select_model("sonnet", spend=3.50) → Sonnet (sotto soglia, nessun declasso)
6. select_model("opus", spend=4.00) → Sonnet (opus→sonnet a soglia degrado)
7. check_budget_or_raise blocked per non-emergency; emergency passa
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

    def test_degraded_threshold_exact_at_4_00(self):
        """VERIFY-06: il degrado Sonnet→Haiku scatta ESATTAMENTE a €4.00 (soglia dichiarata in ROADMAP SC4)."""
        assert select_model("sonnet", spend=4.00) == MODEL_IDS["haiku"]

    def test_below_degraded_threshold_no_downgrade(self):
        """VERIFY-06: a €3.50 (sotto soglia degrado) Sonnet rimane Sonnet."""
        assert select_model("sonnet", spend=3.50) == MODEL_IDS["sonnet"]

    def test_degraded_downgrades_opus_to_sonnet(self):
        assert select_model("opus", spend=4.10) == MODEL_IDS["sonnet"]

    def test_degraded_threshold_exact_opus_to_sonnet(self):
        """VERIFY-06: opus→sonnet scatta esattamente a €4.00."""
        assert select_model("opus", spend=4.00) == MODEL_IDS["sonnet"]

    def test_degraded_zone_forces_haiku_for_sonnet(self):
        """$4.60 (zona DEGRADED ≥4.00, <4.80): sonnet→haiku, opus→sonnet (declasso graduale)."""
        assert select_model("sonnet", spend=4.60) == MODEL_IDS["haiku"]
        assert select_model("opus", spend=4.60) == MODEL_IDS["sonnet"]

    def test_blocked_forces_haiku_all(self):
        """$4.85 (>= BUDGET_BLOCKED=4.80) → tutto Haiku (check_budget_or_raise bloccherà per non-emergency)."""
        assert select_model("sonnet", spend=4.85) == MODEL_IDS["haiku"]
        assert select_model("opus", spend=4.85) == MODEL_IDS["haiku"]

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
        """$3.95 + $0.10 = $4.05 → BLOCKED_NON_CRITICAL (soglia degrado ora €4.00 = BUDGET_DEGRADED).
        Con BUDGET_DEGRADED=4.00, il ramo `projected > BUDGET_DEGRADED` precede `projected > BUDGET_WARNING`
        (stessa soglia), quindi si entra in BLOCKED_NON_CRITICAL, non DEGRADED. Alert inviato."""
        mock_spend.return_value = 3.95
        level = check_budget_or_raise(0.10, "session_analysis")
        assert level == "BLOCKED_NON_CRITICAL"
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

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_verify06_hard_block_non_emergency(self, mock_alert, mock_spend):
        """VERIFY-06 Test 5: proiettato > $4.80 + purpose non-emergency → BudgetExceededError."""
        mock_spend.return_value = 4.75
        with pytest.raises(BudgetExceededError):
            check_budget_or_raise(0.10, "session_analysis")  # 4.75+0.10 = 4.85 > 4.80
        mock_alert.assert_called_once()

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_verify06_hard_block_allows_emergency(self, mock_alert, mock_spend):
        """VERIFY-06 Test 5: blocco hard NON si applica a purpose emergency."""
        mock_spend.return_value = 4.75
        # purpose in EMERGENCY_PURPOSES → non solleva
        level = check_budget_or_raise(0.10, "emergency")
        assert level in ("OK", "WARNING", "DEGRADED", "BLOCKED_NON_CRITICAL")

    @patch("coach.utils.budget.get_month_spend_usd")
    @patch("coach.utils.budget._send_budget_alert")
    def test_verify06_hard_block_race_week_critical(self, mock_alert, mock_spend):
        """VERIFY-06: race_week_critical è emergency → passa anche oltre $4.80."""
        mock_spend.return_value = 4.85
        level = check_budget_or_raise(0.05, "race_week_critical")
        assert level in ("OK", "WARNING", "DEGRADED", "BLOCKED_NON_CRITICAL")
