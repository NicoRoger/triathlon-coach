"""Report CLI del budget Anthropic API mensile."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach.utils.budget import get_month_stats


def main() -> None:
    logging.basicConfig(level=logging.ERROR)
    try:
        from dotenv import load_dotenv; load_dotenv(override=True)
    except ImportError: pass

    try:
        stats = get_month_stats()
    except Exception as e:
        print(f"Errore nel recupero delle statistiche budget: {e}")
        sys.exit(1)

    print("=" * 40)
    print("💰 BUDGET API MESE CORRENTE")
    print("=" * 40)
    print(f"Stato globale:    {stats['budget_level']}")
    print(f"Spesa:            ${stats['total_cost_usd']:.2f} / ${stats['budget_limit_usd']:.2f} ({stats['budget_pct']}%)")
    print(f"Chiamate totali:  {stats['total_calls']} ({stats['successful_calls']} success)")
    print(f"Media giornaliera: ${stats['avg_daily_cost']:.2f}/gg (su {stats['days_elapsed']} gg trascorsi)")
    
    if stats["days_remaining"] > 0 and stats["days_elapsed"] > 0:
        proj = stats["total_cost_usd"] / stats["days_elapsed"] * (stats["days_elapsed"] + stats["days_remaining"])
        print(f"Proiezione mese:  ${proj:.2f}")

    print("\n-- Modelli utilizzati --")
    for m, count in sorted(stats["models"].items(), key=lambda x: -x[1]):
        print(f"  {m}: {count}")

    print("\n-- Categorie spesa (purposes) --")
    for p, count in sorted(stats["purposes"].items(), key=lambda x: -x[1]):
        print(f"  {p}: {count}")
    
    print("=" * 40)


if __name__ == "__main__":
    main()
