"""LLM client wrapper con auto-fallback budget, policy e logging.

Step 6: ogni chiamata Anthropic passa da qui. Il client:
1. Verifica policy locale per purpose
2. Seleziona modello in base a budget corrente
3. Verifica budget prima della call
4. Fa la chiamata API
5. Logga costo su api_usage
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from coach.utils import budget
from coach.utils.budget import BudgetExceededError
from coach.utils.llm_policy import check_purpose_allowed

logger = logging.getLogger(__name__)


class LLMClient:
    """Client Anthropic con policy e selezione modello budget-aware."""

    def __init__(self):
        self.client = None

    def _get_anthropic_client(self):
        if self.client is not None:
            return self.client

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic — required for cloud LLM features") from exc

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        return self.client

    def call(
        self,
        purpose: str,
        system: str,
        messages: list[dict[str, str]],
        prefer_model: str = "sonnet",
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Chiama Anthropic con auto-fallback in base a policy e budget.

        Args:
            purpose: per logging e budget gating (es. 'session_analysis')
            system: system prompt
            messages: lista di messaggi [{"role": "user", "content": "..."}]
            prefer_model: 'sonnet'/'haiku'/'opus'
            max_tokens: max output tokens
            temperature: temperatura generazione

        Returns:
            dict con keys: text, model, input_tokens, output_tokens, cost_usd

        Raises:
            BudgetExceededError: se budget esaurito o purpose disabilitato
        """
        check_purpose_allowed(purpose)

        spend = budget.get_month_spend_usd()
        actual_model = budget.select_model(prefer_model, spend=spend)

        estimated_cost = budget.estimate_cost(actual_model, 3000, max_tokens)
        budget.check_budget_or_raise(estimated_cost, purpose)

        try:
            client = self._get_anthropic_client()
            response = client.messages.create(
                model=actual_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

            text = response.content[0].text if response.content else ""
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            cost = budget.log_api_call(
                model=actual_model,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                metadata={"prefer_model": prefer_model, "temperature": temperature},
            )

            logger.info(
                "LLM call OK: purpose=%s model=%s (prefer=%s) tokens=%d/%d cost=$%.4f",
                purpose, actual_model, prefer_model, input_tokens, output_tokens, cost,
            )

            return {
                "text": text,
                "model": actual_model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            }

        except BudgetExceededError:
            raise
        except Exception as exc:
            budget.log_api_call(
                model=actual_model,
                purpose=purpose,
                input_tokens=0,
                output_tokens=0,
                success=False,
                metadata={"error": str(exc), "prefer_model": prefer_model},
            )
            logger.exception("LLM call failed: purpose=%s model=%s", purpose, actual_model)
            raise


def get_client() -> LLMClient:
    """Factory per LLMClient (singleton-like)."""
    return LLMClient()
