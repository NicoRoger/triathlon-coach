"""Budget tracking e protezione costi API Anthropic.

Step 6: 3 livelli di protezione budget €5/mese.
Livello 2 — soft cap con tracking persistente su Supabase (tabella api_usage).

Soglie:
  <$3.00  → OK, procedi
  $3-$4   → WARNING, alert Telegram, procedi
  $4-$4.50 → DEGRADED, declassa Sonnet→Haiku, alert
  >$4.50  → BLOCKED non-critical, solo emergency
  >$4.80  → BLOCKED tutto, solo purpose='emergency'
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Pricing table — Anthropic maggio 2026 (USD per 1M tokens)
PRICING = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00},
    "claude-opus-4-6":   {"input": 5.00, "output": 25.00},
}

# Model ID mapping
MODEL_IDS = {
    "sonnet": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5",
    "opus":   "claude-opus-4-6",
}

# Budget thresholds (USD)
BUDGET_OK = 3.00
BUDGET_WARNING = 4.00
BUDGET_DEGRADED = 4.50
BUDGET_BLOCKED = 4.80
BUDGET_HARD_CAP = 5.00

# Purpose categories
EMERGENCY_PURPOSES = {"emergency", "race_week_critical", "fatigue_critical"}


class BudgetExceededError(Exception):
    """Raised when budget is exceeded and call is blocked."""
    pass


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Stima costo di una chiamata API in USD."""
    model_id = MODEL_IDS.get(model, model)
    pricing = PRICING.get(model_id)
    if not pricing:
        # Fallback conservativo: usa pricing Sonnet
        pricing = PRICING["claude-sonnet-4-6"]
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 6)


def get_month_spend_usd() -> float:
    """Somma cost_usd_estimated del mese corrente da api_usage."""
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    res = sb.table("api_usage").select("cost_usd_estimated").gte(
        "timestamp", month_start.isoformat()
    ).execute()

    total = sum(float(r.get("cost_usd_estimated", 0)) for r in (res.data or []))
    return round(total, 4)


def get_month_stats() -> dict:
    """Statistiche complete del mese corrente."""
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    res = sb.table("api_usage").select("*").gte(
        "timestamp", month_start.isoformat()
    ).execute()

    rows = res.data or []
    total_cost = sum(float(r.get("cost_usd_estimated", 0)) for r in rows)
    total_calls = len(rows)
    successful = sum(1 for r in rows if r.get("success"))
    days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - now.replace(day=1)).days if now.month < 12 else 31
    days_elapsed = now.day
    days_remaining = days_in_month - days_elapsed

    # Model breakdown
    models = {}
    purposes = {}
    for r in rows:
        m = r.get("model", "unknown")
        p = r.get("purpose", "unknown")
        models[m] = models.get(m, 0) + 1
        purposes[p] = purposes.get(p, 0) + 1

    # Current budget level
    if total_cost < BUDGET_OK:
        level = "OK"
    elif total_cost < BUDGET_WARNING:
        level = "WARNING"
    elif total_cost < BUDGET_DEGRADED:
        level = "DEGRADED"
    elif total_cost < BUDGET_BLOCKED:
        level = "BLOCKED_NON_CRITICAL"
    else:
        level = "BLOCKED_ALL"

    return {
        "total_cost_usd": round(total_cost, 4),
        "budget_limit_usd": BUDGET_HARD_CAP,
        "budget_pct": round(total_cost / BUDGET_HARD_CAP * 100, 1),
        "budget_level": level,
        "total_calls": total_calls,
        "successful_calls": successful,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "avg_daily_cost": round(total_cost / max(days_elapsed, 1), 4),
        "models": models,
        "purposes": purposes,
    }


def select_model(prefer: str, spend: Optional[float] = None) -> str:
    """Seleziona modello effettivo in base a budget.

    Args:
        prefer: modello preferito ('sonnet', 'haiku', 'opus')
        spend: spesa corrente (se None, la legge dal DB)

    Returns:
        model ID effettivo (es. 'claude-sonnet-4-6')
    """
    if spend is None:
        spend = get_month_spend_usd()

    prefer_id = MODEL_IDS.get(prefer, prefer)

    if spend < BUDGET_OK:
        # Tutto ok, rispetta preferenza
        return prefer_id
    elif spend < BUDGET_WARNING:
        # Warning ma procedi con preferenza
        return prefer_id
    elif spend < BUDGET_DEGRADED:
        # Declassa: opus→sonnet, sonnet→haiku, haiku→haiku
        if prefer in ("opus", "claude-opus-4-6"):
            return MODEL_IDS["sonnet"]
        else:
            return MODEL_IDS["haiku"]
    elif spend < BUDGET_BLOCKED:
        # Solo haiku per qualsiasi cosa
        return MODEL_IDS["haiku"]
    else:
        # Blocked: restituisce haiku ma check_budget_or_raise bloccherà
        return MODEL_IDS["haiku"]


def check_budget_or_raise(estimated_cost: float, purpose: str) -> str:
    """Controlla budget e ritorna livello. Raise se bloccato.

    Returns:
        Budget level string ('OK', 'WARNING', 'DEGRADED', 'BLOCKED')

    Raises:
        BudgetExceededError se il budget è esaurito e purpose non è emergency
    """
    spend = get_month_spend_usd()
    projected = spend + estimated_cost
    is_emergency = purpose in EMERGENCY_PURPOSES

    if projected > BUDGET_BLOCKED and not is_emergency:
        _send_budget_alert(
            f"🛑 Budget API ESAURITO (${spend:.2f}/${BUDGET_HARD_CAP:.2f}). "
            f"Tutte le chiamate AI disabilitate fino a fine mese. "
            f"Solo emergenze ammesse."
        )
        raise BudgetExceededError(
            f"Budget exhausted: ${spend:.2f} spent, ${estimated_cost:.4f} requested. "
            f"Only emergency purposes allowed."
        )

    if projected > BUDGET_DEGRADED and not is_emergency:
        _send_budget_alert(
            f"⚠️ Budget API al {spend/BUDGET_HARD_CAP*100:.0f}% (${spend:.2f}/${BUDGET_HARD_CAP:.2f}). "
            f"Declassato a Haiku. Chiamate non critiche bloccate sopra $4.80."
        )
        return "BLOCKED_NON_CRITICAL"

    if projected > BUDGET_WARNING:
        _send_budget_alert(
            f"📊 Budget API al {spend/BUDGET_HARD_CAP*100:.0f}% (${spend:.2f}/${BUDGET_HARD_CAP:.2f}). "
            f"Modello declassato a Haiku per risparmiare."
        )
        return "DEGRADED"

    if projected > BUDGET_OK:
        # Alert solo la prima volta (check se già mandato oggi)
        logger.info("Budget warning: $%.2f / $%.2f", spend, BUDGET_HARD_CAP)
        return "WARNING"

    return "OK"


def log_api_call(
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    metadata: Optional[dict] = None,
    provider: str = "anthropic",
) -> float:
    """Logga una chiamata API su Supabase. Ritorna costo stimato."""
    cost = estimate_cost(model, input_tokens, output_tokens)
    sb = get_supabase()
    sb.table("api_usage").insert({
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd_estimated": cost,
        "success": success,
        "metadata": metadata,
    }).execute()
    logger.info(
        "API call logged: model=%s purpose=%s tokens=%d/%d cost=$%.4f success=%s",
        model, purpose, input_tokens, output_tokens, cost, success,
    )
    return cost


def _send_budget_alert(message: str) -> None:
    """Manda alert budget via Telegram."""
    try:
        from coach.planning.briefing import send_to_telegram
        send_to_telegram(message)
    except Exception:
        logger.warning("Failed to send budget alert via Telegram")
