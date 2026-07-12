"""Registry dei `purpose` di bot_messages (WP2).

Il purpose è il CONTRATTO dell'idempotenza notifiche: chi invia (via
send_and_log_message) e chi controlla "già inviato oggi?" devono usare la
STESSA stringa. Due bug storici (doppio debrief serale, 3× weekly review)
sono nati esattamente da stringhe divergenti scritte a mano nei due punti.

Regola: nel codice Python mai stringhe literal per i purpose — importare da
qui. Il lato TypeScript (workers) ha le sue stringhe: la coerenza cross-stack
è verificata da tests/test_purposes.py sui purpose condivisi.
"""
from __future__ import annotations

MORNING_BRIEF = "morning_brief"
ENERGY_UPDATE = "energy_update"
DEBRIEF_REMINDER = "debrief_reminder"
WEEKLY_REVIEW_REMINDER = "weekly_review_reminder"
PROACTIVE_QUESTION = "proactive_question"
PROACTIVE_DISABLED_TODAY = "proactive_disabled_today"
MODULATION_PROPOSAL = "modulation_proposal"
ZONES_RECALC = "zones_recalc"
GENERIC = "generic"

ALL_PURPOSES = frozenset(
    v for k, v in globals().items()
    if k.isupper() and isinstance(v, str) and not k.startswith("_") and k != "ALL_PURPOSES"
)
