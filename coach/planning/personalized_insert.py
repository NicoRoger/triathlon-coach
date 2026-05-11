"""Blocco 5.3 — Personalized briefing inserts.

Legge docs/coaching_observations.md e determina quale pattern è rilevante
per oggi (giorno settimana, sport pianificato, situazione). Inserisce
una riga nel brief mattutino. Zero costo LLM — solo lettura file + match.

Uso: chiamata da briefing.py come funzione.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
OBSERVATIONS_FILE = DOCS_DIR / "coaching_observations.md"

WEEKDAY_NAMES_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
SPORT_BY_WEEKDAY = {
    0: "corsa",       # lunedì
    1: "nuoto",       # martedì
    2: "bici",        # giovedì
    3: "nuoto",       # giovedì
    4: "corsa",       # venerdì
    5: "bici",        # sabato
    6: "corsa",       # domenica
}


def get_personalized_insert(today: Optional[date] = None) -> Optional[str]:
    """Ritorna una riga HTML per il brief, o None se nessun pattern rilevante."""
    if not OBSERVATIONS_FILE.exists():
        return None

    content = OBSERVATIONS_FILE.read_text(encoding="utf-8")
    if len(content) < 100:
        return None

    today = today or date.today()
    weekday = today.weekday()
    weekday_name = WEEKDAY_NAMES_IT[weekday]
    sport_today = SPORT_BY_WEEKDAY.get(weekday, "")

    insights: list[str] = []

    # Match weekday-specific patterns
    for line in content.split("\n"):
        line_lower = line.lower().strip()
        if not line_lower.startswith("- "):
            continue

        # Giorno specifico menzionato
        if weekday_name in line_lower:
            insights.append(line.strip().lstrip("- ").strip())
            continue

        # Sport di oggi menzionato con pattern rilevante
        if sport_today and sport_today in line_lower:
            if any(kw in line_lower for kw in ["hrv", "recupero", "fatica", "rpe", "tendenza", "pattern", "correlazione"]):
                insights.append(line.strip().lstrip("- ").strip())

    if not insights:
        return None

    best = insights[0][:200]
    return f"💡 <b>Pattern</b>: {best}"
