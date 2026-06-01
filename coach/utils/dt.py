"""Utility date/time con timezone Europe/Rome.

Usa today_rome() invece di date.today() negli script cron per evitare
che l'ora UTC (server GitHub Actions) faccia slittare il giorno alle 23:00-01:00.
"""
from datetime import date, datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

_ROME = ZoneInfo("Europe/Rome")


def today_rome() -> date:
    """Data di calendario corrente in Europe/Rome."""
    return datetime.now(_ROME).date()


def to_rome_date(ts: Union[str, datetime, None]) -> Optional[date]:
    """Converte un timestamp (ISO string o datetime) alla DATA di calendario in
    Europe/Rome.

    Necessario per confrontare `started_at` (stored UTC) con `planned_date`
    (data Rome): un'attività a cavallo di mezzanotte ha una data UTC diversa
    dalla data Rome, e lo slicing ingenuo `started_at[:10]` sbaglia il giorno.
    Ritorna None se l'input è vuoto/non parsabile.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        s = str(ts).strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ROME).date()
