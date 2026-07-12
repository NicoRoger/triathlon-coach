"""LLM client wrapper con hybrid routing (Anthropic + Gemini) + budget tracking.

Routing strategy (Fase 1.1 del piano evoluzione):
- Gemini (free): task delegabili — descrittivi, semplici, ad alto volume
- Anthropic API (paid, parsimonioso): task critiche autonome
- Claude Pro (via Claude.ai web): workflow human-in-the-loop (NON gestiti qui)

Vedi PURPOSE_ROUTING per la mappa completa.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from coach.utils import budget
from coach.utils.budget import BudgetExceededError

logger = logging.getLogger(__name__)

# ============================================================================
# Routing strategy: purpose → provider
# ============================================================================
# Provider="gemini": usa GeminiClient (free tier)
# Provider="anthropic": usa LLMClient (con budget gating + caching)
# Provider="claude_pro": NON gestito qui (workflow su Claude.ai web)
PURPOSE_ROUTING: dict[str, str] = {
    # Gemini (free, alto volume, task descrittivi/educational)
    "session_analysis":       "gemini",
    "post_session_analysis":  "gemini",
    "pattern_extraction":     "gemini",
    "reminder_generation":    "gemini",
    "verification_citations": "gemini",
    "weekly_lesson":          "gemini",
    "proactive_question":     "gemini",
    "communication_text":     "gemini",
    # Anthropic API (critiche autonome, parsimonia)
    "modulation":             "anthropic",   # decisione critica autonoma
    "race_prediction":        "anthropic",   # precisione richiesta
    "post_race_analysis":     "anthropic",   # analisi profonda gara
    "race_briefing":          "anthropic",   # pre-gara critico (poche all'anno)
    "weekly_analysis":        "anthropic",   # narrative settimanale serve qualità
}

# Anthropic prefer_model per purpose (usato solo per provider='anthropic')
ANTHROPIC_PREFER_MODEL: dict[str, str] = {
    "modulation":         "haiku",
    "race_prediction":    "sonnet",
    "post_race_analysis": "sonnet",
    "race_briefing":      "sonnet",
    "weekly_analysis":    "sonnet",
}


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
        cache_system: bool = True,
    ) -> dict[str, Any]:
        """Chiama Anthropic con auto-fallback in base a budget + prompt caching.

        Args:
            purpose: per logging e budget gating (es. 'session_analysis')
            system: system prompt
            messages: lista di messaggi [{"role": "user", "content": "..."}]
            prefer_model: 'sonnet'/'haiku'/'opus'
            max_tokens: max output tokens
            temperature: temperatura generazione
            cache_system: se True (default), abilita prompt caching ephemeral sul system
                          (riduce input cost del ~90% sui retry entro 5min, 50% entro 1h).
                          Disabilita per system prompts molto brevi (<1024 tokens).

        Returns:
            dict con keys: text, model, input_tokens, output_tokens, cost_usd,
                          cache_creation_tokens, cache_read_tokens

        Raises:
            BudgetExceededError: se budget esaurito e purpose non emergency
        """
        # 1. Seleziona modello
        spend = budget.get_month_spend_usd()
        actual_model = budget.select_model(prefer_model, spend=spend)

        # 2. Pre-check budget (stima conservativa, no caching in stima)
        estimated_cost = budget.estimate_cost(actual_model, 3000, max_tokens)
        budget.check_budget_or_raise(estimated_cost, purpose)

        # 3. Prepara system con cache_control se abilitato
        # Caching richiede min ~1024 tokens; sotto soglia Anthropic ignora silenziosamente
        if cache_system and system:
            system_param: Any = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_param = system

        # 4. Chiamata API
        try:
            response = self.client.messages.create(
                model=actual_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_param,
                messages=messages,
            )

            text = response.content[0].text if response.content else ""
            usage = response.usage
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            # 5. Log — i token cache entrano nel COSTO (WP6), non solo nei
            # metadata: prima la spesa registrata li ignorava e il cap €5
            # sottostimava la fattura reale.
            cost = budget.log_api_call(
                model=actual_model,
                purpose=purpose,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                metadata={
                    "prefer_model": prefer_model,
                    "temperature": temperature,
                    "cache_creation_tokens": cache_creation,
                    "cache_read_tokens": cache_read,
                },
            )

            logger.info(
                "LLM call OK: purpose=%s model=%s (prefer=%s) tokens=%d/%d cache=%d/%d cost=$%.4f",
                purpose, actual_model, prefer_model, input_tokens, output_tokens,
                cache_creation, cache_read, cost,
            )

            return {
                "text": text,
                "model": actual_model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_tokens": cache_creation,
                "cache_read_tokens": cache_read,
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

    MODEL = "gemini-2.5-flash"

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
        # Bug fix audit I6: concatena TUTTI i messaggi (con ruolo), non solo
        # l'ultimo — altrimenti il contesto multi-turno viene perso silenziosamente.
        if messages:
            user_content = "\n\n".join(
                f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages
            )
        else:
            user_content = ""

        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=user_content,
                config=self._types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                    thinking_config=self._types.ThinkingConfig(thinking_budget=0),
                ),
            )
            # Bug fix audit I7: response.text può essere None (safety block /
            # MAX_TOKENS). Coercizione a "" per non propagare None ai consumer.
            text = response.text or ""
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
    """DEPRECATED — usa get_client_for_purpose('session_analysis').

    Mantenuto per retrocompatibilità. Ritorna GeminiClient se disponibile,
    altrimenti LLMClient (Anthropic).
    """
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiClient()
    return LLMClient()


class HybridClient:
    """Wrapper che instrada le call a Gemini o Anthropic in base al purpose.

    Implementa failover automatico:
    - Se purpose è routed su Gemini ma Gemini fallisce (quota / errore) → fallback Anthropic Haiku
    - Se purpose è routed su Anthropic ma budget esaurito → Haiku degrade (gestito da LLMClient)

    Mantiene la stessa interfaccia .call() di LLMClient / GeminiClient.
    """

    def __init__(self):
        self._anthropic: Optional[LLMClient] = None
        self._gemini: Optional[GeminiClient] = None

    def _get_anthropic(self) -> LLMClient:
        if self._anthropic is None:
            self._anthropic = LLMClient()
        return self._anthropic

    def _get_gemini(self) -> Optional[GeminiClient]:
        if self._gemini is None:
            try:
                self._gemini = GeminiClient()
            except (ImportError, RuntimeError) as e:
                logger.warning("Gemini client unavailable: %s", e)
                self._gemini = None
        return self._gemini

    def call(
        self,
        purpose: str,
        system: str,
        messages: list[dict[str, str]],
        prefer_model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        cache_system: bool = True,
    ) -> dict[str, Any]:
        """Instrada la call al provider corretto in base a PURPOSE_ROUTING.

        Failover: se Gemini fallisce (es. quota) → Anthropic Haiku.
        """
        provider = PURPOSE_ROUTING.get(purpose, "anthropic")

        # Provider Gemini
        if provider == "gemini":
            gemini = self._get_gemini()
            if gemini is not None:
                try:
                    return gemini.call(
                        purpose=purpose,
                        system=system,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                except Exception as e:
                    # Failover ad Anthropic Haiku
                    logger.warning(
                        "Gemini failed for purpose=%s, fallback to Anthropic Haiku: %s",
                        purpose, e,
                    )
                    _alert_provider_fallback(purpose, str(e))
            else:
                logger.warning("Gemini not configured, fallback to Anthropic for purpose=%s", purpose)

            # Failover
            return self._get_anthropic().call(
                purpose=purpose,
                system=system,
                messages=messages,
                prefer_model="haiku",
                max_tokens=max_tokens,
                temperature=temperature,
                cache_system=cache_system,
            )

        # Provider Anthropic (default)
        effective_prefer = prefer_model or ANTHROPIC_PREFER_MODEL.get(purpose, "sonnet")
        return self._get_anthropic().call(
            purpose=purpose,
            system=system,
            messages=messages,
            prefer_model=effective_prefer,
            max_tokens=max_tokens,
            temperature=temperature,
            cache_system=cache_system,
        )


_hybrid_instance: Optional[HybridClient] = None


def get_client_for_purpose(purpose: str) -> HybridClient:
    """Factory principale: ritorna HybridClient con routing automatico per purpose.

    Esempio:
        client = get_client_for_purpose("session_analysis")  # → Gemini
        result = client.call(purpose="session_analysis", system="...", messages=[...])

    Il purpose va passato sia qui che a call() per consistenza nel logging.
    """
    global _hybrid_instance
    if _hybrid_instance is None:
        _hybrid_instance = HybridClient()
    return _hybrid_instance


def _alert_provider_fallback(purpose: str, error: str) -> None:
    """Manda alert Telegram quando Gemini fallisce e fallback Anthropic si attiva."""
    try:
        from coach.planning.briefing import send_to_telegram
        send_to_telegram(
            f"⚠️ Gemini fallita per `{purpose}` → fallback Anthropic Haiku. "
            f"Errore: {error[:120]}"
        )
    except Exception:
        logger.warning("Failed to send provider fallback alert via Telegram")
