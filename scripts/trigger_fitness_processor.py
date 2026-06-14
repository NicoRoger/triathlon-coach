"""Trigger manuale del FitnessTestProcessor su attività di giugno 2026.

Bypassa il cutoff 6h di check_recent() e processa tutti i test fitness
nel range 2026-06-01 -> 2026-06-30 matchati con planned_sessions.

Uso:
  PYTHONPATH=. python scripts/trigger_fitness_processor.py --dry-run
  PYTHONPATH=. python scripts/trigger_fitness_processor.py
"""
from __future__ import annotations

import argparse
import json
import logging

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.coaching.fitness_test_processor import FitnessTestProcessor
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ============================================================================
# main
# ============================================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Trigger FitnessTestProcessor su attività giugno 2026 (finestra estesa)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stampa le attività matchate senza chiamare process_fitness_test()",
    )
    args = parser.parse_args()

    # Finestra estesa: tutto giugno 2026 (non solo 6h come check_recent)
    cutoff_from = "2026-06-01T00:00:00+00:00"
    cutoff_to = "2026-06-30T23:59:59+00:00"

    print("=== Trigger Fitness Processor (June 2026) ===")
    print("Finestra: 2026-06-01 -> 2026-06-30")
    if args.dry_run:
        print("Modalità: --dry-run (nessuna scrittura su DB)")
    print()

    sb = get_supabase()
    processor = FitnessTestProcessor()

    activities = (
        sb.table("activities")
        .select(
            "id,external_id,started_at,sport,duration_s,avg_hr,max_hr,"
            "avg_power_w,np_w,avg_pace_s_per_km,avg_pace_s_per_100m,tss,splits,notes"
        )
        .gte("started_at", cutoff_from)
        .lte("started_at", cutoff_to)
        .in_("sport", ["bike", "run", "swim"])
        .order("started_at")
        .execute()
        .data
        or []
    )

    print(f"Attività trovate: {len(activities)}")
    print()

    processed_count = 0
    keywords = ["ftp", "css", "threshold", "soglia", "test", "ramp"]

    for activity in activities:
        activity_id = activity.get("id") or activity.get("external_id")
        activity_date = str(activity.get("started_at", ""))[:10]
        sport = activity.get("sport")

        try:
            # Cerca planned_session con session_type='fitness_test'
            planned = (
                sb.table("planned_sessions")
                .select("*")
                .eq("planned_date", activity_date)
                .eq("sport", sport)
                .eq("session_type", "fitness_test")
                .limit(1)
                .execute()
                .data
            )

            if planned:
                planned_session = planned[0]
                structured = planned_session.get("structured") or {}
                test_type = structured.get("test_type", "N/A")

                print(
                    f"[{sport} {activity_date}] id={activity_id}"
                    f" — matched planned_session fitness_test (test_type={test_type})"
                )
                logger.info("Matched: %s %s — session_type=fitness_test", sport, activity_date)

                if args.dry_run:
                    print("  [dry-run] Salto process_fitness_test()")
                else:
                    print("  -> processando...")
                    result = processor.process_fitness_test(activity, planned_session)
                    print(f"  Risultato: {json.dumps(result, default=str)}")
                    processed_count += 1

                print()
                continue

            # Nessuna planned_session: keyword match sulle notes per avviso manuale
            notes = (activity.get("notes") or "").lower()
            ext_id_str = str(activity.get("external_id") or "").lower()
            search_str = f"{notes} {ext_id_str}".strip()
            if any(kw in search_str for kw in keywords):
                logger.info(
                    "keyword_match_no_planned_session: %s %s — manual review needed",
                    sport, activity_date,
                )
                print(
                    f"[{sport} {activity_date}] id={activity_id}"
                    f" — keyword_match_no_planned_session: manual review needed"
                )
                print()

        except Exception:  # noqa: BLE001
            logger.exception(
                "Errore processing attività %s (%s %s)",
                activity_id, sport, activity_date,
            )
            print(
                f"[{sport} {activity_date}] id={activity_id}"
                f" — ERRORE (vedi log sopra)"
            )
            print()

    # Riepilogo finale
    if args.dry_run:
        print(f"[dry-run] Nessuna attività processata — rieseguire senza --dry-run per scrivere su DB.")
    else:
        print(f"Processati: {processed_count} attività — vedi output sopra per dettagli.")
    print("Rieseguire verify_physiology.py per confermare i valori in DB.")


if __name__ == "__main__":
    main()
