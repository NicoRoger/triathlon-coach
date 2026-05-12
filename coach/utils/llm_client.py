"""LLM client wrapper con auto-fallback budget e logging.

Step 6: ogni chiamata Anthropic passa da qui. Il client:
1. Seleziona modello in base a budget corrente
2. Verifica budget prima della call
3. Fa la chiamata con retry
4. Logga costo su api_usage
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from coach.utils import budget
from coach.utils.budget import BudgetExceededError

logger = logging.getLogger(__name__)


class LLMClient:
    """Client Anthropic con budget-aware model selection."""

    def __init__(self):
        try:
            import anthropic
        except ImportError:
            raise ImportError("pip install anthropic — required for Step 6 coaching features")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=api_key)

    def call(
        self,
        purpose: str,
        system: str,
        messages: list[dict[str, str]],
        prefer_model: str = "sonnet",
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Chiama Anthropic con auto-fallback in base a budget.

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
            BudgetExceededError: se budget esaurito e purpose non emergency
        """
        # 1. Seleziona modello
        spend = budget.get_month_spend_usd()
        actual_model = budget.select_model(prefer_model, spend=spend)

        # 2. Pre-check budget (stima conservativa)
        estimated_cost = budget.estimate_cost(actual_model, 3000, max_tokens)
        budget.check_budget_or_raise(estimated_cost, purpose)

        # 3. Chiamata API
        try:
            response = self.client.messages.create(
                model=actual_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
            )

            text = response.content[0].text if response.content else ""
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # 4. Log
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
        except Exception as e:
            # Log failed call (stima token)
            budget.log_api_call(
                model=actual_model,
                purpose=purpose,
                input_tokens=0,
                output_tokens=0,
                success=False,
                metadata={"error": str(e), "prefer_model": prefer_model},
            )
            logger.exception("LLM call failed: purpose=%s model=%s", purpose, actual_model)
            raise


def get_client() -> LLMClient:
    """Factory per LLMClient (singleton-like)."""
    return LLMClient()


class GeminiClient:
    """Google Gemini client via google-genai SDK. Same interface as LLMClient."""

    MODEL = "gemini-2.0-flash"

    def __init__(self):
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError("pip install google-genai — required for Gemini support")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self._client = genai.Client(api_key=api_key)
        self._types = genai_types

    def call(
        self,
        purpose: str,
        system: str,
        messages: list[dict[str, str]],
        prefer_model: str = "gemini-2.0-flash",
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> dict:
        """Chiama Gemini. Stessa interfaccia di LLMClient.call()."""
        user_content = messages[-1]["content"] if messages else ""

        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=user_content,
                config=self._types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            text = response.text
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0

            budget.log_api_call(
                model=self.MODEL,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                metadata={"temperature": temperature},
                provider="gemini",
            )

            logger.info(
                "Gemini call OK: purpose=%s tokens=%d/%d",
                purpose, input_tokens, output_tokens,
            )

            return {
                "text": text,
                "model": self.MODEL,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": 0.0,
            }

        except Exception as e:
            budget.log_api_call(
                model=self.MODEL,
                purpose=purpose,
                input_tokens=0,
                output_tokens=0,
                success=False,
                metadata={"error": str(e)},
                provider="gemini",
            )
            logger.exception("Gemini call failed: purpose=%s", purpose)
            raise


def get_gemini_client() -> GeminiClient:
    """Factory per GeminiClient."""
    return GeminiClient()


def get_analysis_client():
    """Ritorna GeminiClient se GEMINI_API_KEY è disponibile, altrimenti LLMClient (Haiku fallback)."""
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiClient()
    return LLMClient()
