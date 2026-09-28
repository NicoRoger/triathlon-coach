"""Matching seduta pianificata ↔ attività svolta.

Collega ogni planned_session passata (status planned/modified) all'attività
Garmin dello stesso giorno (Rome) e dello stesso sport: scrive
completed_activity_id e status='completed'.

Prima di questo job l'unico writer di completed_activity_id era
fitness_test_processor (solo per i test): tutte le altre sedute restavano
'planned' con completed_activity_id nullo anche a lavoro fatto. A valle,
pattern_extraction non riusciva a risalire al session_type dell'attività e
compliance/outcome (hypothesis, outcome_verification) contavano zero sedute
completate.

Non è una modifica del piano (CLAUDE.md §5.4): registra solo che la seduta
prescritta è stata eseguita — descrizione, data e target restano intatti.

Uso:
    python -m coach.planning.session_matching [--days 14]
"""
from __future__ import annotations

import argparse
import logging
from datetime import timedelta
from typing import Optional

from coach.utils.athlete import aq
from coach.utils.dt import to_rome_date, today_rome

logger = logging.getLogger(__name__)

MATCHABLE_STATUSES = ("planned", "modified")


def match_sessions(planned: list[dict], activities: list[dict]) -> list[tuple[str, str]]:
    """Accoppia sedute pianificate e attività. Funzione pura (testabile).

    Regole:
    - stesso giorno Rome e stesso sport;
    - un'attività si collega a una sola seduta;
    - con più candidate vince la durata più vicina a quella pianificata;
    - i fitness_test sono di fitness_test_processor (estrae la soglia prima di
      marcarli): il loro giorno+sport resta fuori, così un'attività di test
      non finisce collegata a un'altra seduta dello stesso sport.

    Returns: lista di (planned_session_id, activity_id).
    """
    by_key: dict[tuple[str, str], list[dict]] = {}
    for a in activities:
        d = to_rome_date(a.get("started_at"))
        if d and a.get("id") and a.get("sport"):
            by_key.setdefault((d.isoformat(), a["sport"]), []).append(a)

    test_keys = {
        (str(p.get("planned_date")), p.get("sport"))
        for p in planned if p.get("session_type") == "fitness_test"
    }

    used: set[str] = set()
    matches: list[tuple[str, str]] = []
    ordered = sorted(planned, key=lambda p: (str(p.get("planned_date")), str(p.get("id"))))
    for p in ordered:
        key = (str(p.get("planned_date")), p.get("sport"))
        if p.get("session_type") == "fitness_test" or key in test_keys:
            continue
        candidates = [a for a in by_key.get(key, []) if a["id"] not in used]
        if not candidates:
            continue
        target = p.get("duration_s")
        if target:
            best = min(candidates, key=lambda a: abs((a.get("duration_s") or 0) - target))
        else:
            best = min(candidates, key=lambda a: str(a.get("started_at")))
        used.add(best["id"])
        matches.append((p["id"], best["id"]))
    return matches


def match_recent(days: int = 14) -> int:
    """Collega le sedute degli ultimi `days` giorni (oggi incluso)."""
    today = today_rome()
    since = today - timedelta(days=days)

    planned = (
        aq("planned_sessions")
        .select("id,planned_date,sport,session_type,duration_s,status")
        .gte("planned_date", since.isoformat())
        .lte("planned_date", today.isoformat())
        .in_("status", list(MATCHABLE_STATUSES))
        .is_("completed_activity_id", "null")
        .execute()
    ).data or []
    if not planned:
        logger.info("Session matching: nessuna seduta da collegare")
        return 0

    # Margine di un giorno sul cutoff UTC: started_at è UTC, il giorno è Rome.
    activities = (
        aq("activities")
        .select("id,started_at,sport,duration_s")
        .gte("started_at", (since - timedelta(days=1)).isoformat())
        .execute()
    ).data or []

    # Attività già collegate a una seduta (anche fuori finestra) non si riusano.
    linked = (
        aq("planned_sessions")
        .select("completed_activity_id")
        .not_.is_("completed_activity_id", "null")
        .gte("planned_date", (since - timedelta(days=1)).isoformat())
        .execute()
    ).data or []
    linked_ids = {r["completed_activity_id"] for r in linked}
    activities = [a for a in activities if a.get("id") not in linked_ids]

    n = 0
    for planned_id, activity_id in match_sessions(planned, activities):
        try:
            aq("planned_sessions").update({
                "status": "completed",
                "completed_activity_id": activity_id,
            }).eq("id", planned_id).is_("completed_activity_id", "null").execute()
            n += 1
        except Exception:  # noqa: BLE001
            logger.warning("Impossibile collegare seduta %s ad attività %s",
                           planned_id, activity_id, exc_info=True)
    logger.info("Session matching: %d sedute collegate", n)
    return n


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args(argv)

    from coach.utils.health import record_health
    try:
        match_recent(args.days)
    except Exception as e:  # noqa: BLE001
        record_health("session_matching", success=False, error=str(e))
        raise
    record_health("session_matching", success=True)


if __name__ == "__main__":
    main()
