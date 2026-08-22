"""Pausa coaching: sospende le notifiche all'atleta senza spegnere il sistema.

Serve quando l'atleta è fermo per un motivo noto — infortunio, accertamenti
medici, viaggio prolungato — e i messaggi a calendario fisso (brief, energia,
debrief, check-in, weekly review) diventano rumore quotidiano su qualcosa che
non sta facendo.

La pausa NON ferma l'ingest né l'analytics: i dati continuano a essere
raccolti (HRV, sonno, HR a riposo restano preziosi proprio in un periodo di
stop, e servono a ripartire da una base reale invece che da un buco). Si
interrompe solo l'uscita verso Telegram, in un punto solo.

Gli alert di SISTEMA continuano ad arrivare: budget, fallback provider e
watchdog non parlano di allenamento, parlano del sistema, e silenziarli
significherebbe non accorgersi che qualcosa si è rotto mentre non guardi.

Configurazione, in ordine di precedenza:
  1. env `COACH_PAUSE_UNTIL` (YYYY-MM-DD) — override senza toccare il codice
  2. `PAUSE_UNTIL` qui sotto — default committato, visibile e revisionabile

La pausa scade DA SOLA: il giorno indicato è il primo in cui le notifiche
tornano. Non serve ricordarsi di riattivarla.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

from coach.utils.purposes import BUDGET_ALERT, GENERIC, PROVIDER_FALLBACK, SMOKE_TEST

logger = logging.getLogger(__name__)

#: Notifiche di SISTEMA: passano sempre, anche in pausa. Non riguardano
#: l'allenamento e servono ad accorgersi dei guasti.
SYSTEM_PURPOSES = frozenset({BUDGET_ALERT, PROVIDER_FALLBACK, SMOKE_TEST, GENERIC})

#: Primo giorno in cui le notifiche all'atleta tornano attive.
#: None = nessuna pausa.
#:
#: 2026-08-27: stop allenamenti in attesa della risonanza magnetica cardiaca.
#: Le notifiche riprendono il giorno dell'esame; se servisse prolungare, basta
#: cambiare questa data (o impostare COACH_PAUSE_UNTIL).
PAUSE_UNTIL: Optional[date] = date(2026, 8, 27)


def pause_until() -> Optional[date]:
    """Data di fine pausa, o None se non c'è pausa attiva."""
    raw = os.environ.get("COACH_PAUSE_UNTIL", "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            logger.warning(
                "COACH_PAUSE_UNTIL=%r non è una data ISO (YYYY-MM-DD): ignorata", raw
            )
    return PAUSE_UNTIL


def is_paused(purpose: str, today: Optional[date] = None) -> bool:
    """True se questa notifica va soppressa oggi."""
    if purpose in SYSTEM_PURPOSES:
        return False
    until = pause_until()
    if until is None:
        return False
    if today is None:
        from coach.utils.dt import today_rome
        today = today_rome()
    return today < until
