"""Utility date/time con timezone Europe/Rome.

Usa today_rome() invece di date.today() negli script cron per evitare
che l'ora UTC (server GitHub Actions) faccia slittare il giorno alle 23:00-01:00.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

_ROME = ZoneInfo("Europe/Rome")


def today_rome() -> date:
    """Data di calendario corrente in Europe/Rome."""
    return datetime.now(_ROME).date()
