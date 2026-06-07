"""
Verifica che le migration SQL dell'audit di resilienza 2026-06-01 siano live in Supabase.

Interroga information_schema per ogni vincolo atteso (UNIQUE, FK, CHECK) e la colonna
plan_modulations.expires_at. Esce con codice 0 se tutto è presente, 1 se manca qualcosa.

Uso:
    PYTHONPATH=. python scripts/verify_migrations.py
"""
import logging
import sys

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ── Vincoli attesi dall'audit 2026-06-01 ──────────────────────────────────────

# (tabella, nome_vincolo)
EXPECTED_UNIQUE_CONSTRAINTS = [
    ("races", "races_name_date_unique"),
    ("physiology_zones", "physiology_zones_disc_validfrom_method_unique"),
    ("planned_sessions", "unique_planned_date_sport_type"),
]

EXPECTED_FK_CONSTRAINTS = [
    ("mesocycles", "mesocycles_target_race_fk"),
    ("planned_sessions", "planned_sessions_completed_activity_id_fkey"),
    ("physiology_zones", "physiology_zones_test_activity_id_fkey"),
]

EXPECTED_CHECK_CONSTRAINTS = [
    ("plan_modulations", "plan_modulations_status_check"),
    ("subjective_log", "subjective_log_kind_check"),
]

# (tabella, colonna)
EXPECTED_COLUMNS = [
    ("plan_modulations", "expires_at"),
]


def _fetch_constraints(sb) -> set:
    """Recupera i nomi dei vincoli presenti in information_schema.table_constraints.

    Prova prima via PostgREST schema('information_schema'); se non esposto (Pitfall 4
    — PostgREST non mostra information_schema via REST), ricade su RPC
    get_public_constraints().
    """
    try:
        resp = (
            sb.schema("information_schema")
            .table("table_constraints")
            .select("constraint_name,table_name,constraint_type")
            .eq("table_schema", "public")
            .execute()
        )
        if resp.data:
            return {row["constraint_name"] for row in resp.data}
        # Risposta vuota può indicare che information_schema non è esposto
        raise ValueError("information_schema query returned empty — trying RPC fallback")
    except Exception as exc:
        logger.warning(
            "information_schema.table_constraints non accessibile via PostgREST (%s) "
            "— uso fallback RPC get_public_constraints()",
            exc,
        )
        resp = sb.rpc("get_public_constraints").execute()
        if resp.data:
            return {row["constraint_name"] for row in resp.data}
        return set()


def _fetch_columns(sb) -> set:
    """Recupera le coppie (table_name, column_name) presenti in information_schema.columns.

    Stessa strategia primaria/fallback di _fetch_constraints.
    """
    try:
        resp = (
            sb.schema("information_schema")
            .table("columns")
            .select("table_name,column_name")
            .eq("table_schema", "public")
            .execute()
        )
        if resp.data:
            return {(row["table_name"], row["column_name"]) for row in resp.data}
        raise ValueError("information_schema.columns query returned empty — trying RPC fallback")
    except Exception as exc:
        logger.warning(
            "information_schema.columns non accessibile via PostgREST (%s) "
            "— uso fallback RPC get_public_columns()",
            exc,
        )
        resp = sb.rpc("get_public_columns").execute()
        if resp.data:
            return {(row["table_name"], row["column_name"]) for row in resp.data}
        return set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()

    try:
        live_constraints = _fetch_constraints(sb)
        live_columns = _fetch_columns(sb)

        results: list[tuple[str, bool]] = []

        # Vincoli UNIQUE
        for _table, name in EXPECTED_UNIQUE_CONSTRAINTS:
            results.append((name, name in live_constraints))

        # Vincoli FK
        for _table, name in EXPECTED_FK_CONSTRAINTS:
            results.append((name, name in live_constraints))

        # Vincoli CHECK
        for _table, name in EXPECTED_CHECK_CONSTRAINTS:
            results.append((name, name in live_constraints))

        # Colonne
        for table, col in EXPECTED_COLUMNS:
            label = f"{table}.{col}"
            results.append((label, (table, col) in live_columns))

        failures: list[str] = []
        for label, ok in results:
            if ok:
                logger.info("PASS: %s", label)
            else:
                logger.error("FAIL: %s", label)
                failures.append(label)

        if failures:
            logger.error(
                "%d constraint(s) missing — migrations may not be applied",
                len(failures),
            )
            sys.exit(1)

        logger.info("All %d constraints verified OK", len(results))

    except Exception:
        logger.exception("Errore durante la verifica delle migration")
        sys.exit(1)


if __name__ == "__main__":
    main()
