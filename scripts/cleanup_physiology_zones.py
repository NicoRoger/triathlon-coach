"""Cleanup physiology_zones — rimuove righe con valori fuori bounds plausibili.

Dry run (default): mostra le righe che verrebbero cancellate senza toccare il DB.
Con --confirm: esegue il DELETE delle righe out-of-bounds e logga ogni cancellazione.

Uso:
    PYTHONPATH=. python scripts/cleanup_physiology_zones.py           # dry run
    PYTHONPATH=. python scripts/cleanup_physiology_zones.py --confirm # cancella

Contesto: bug E1/E2 pre-fix potevano scrivere valori FTP/threshold assurdi in
physiology_zones. Questo script identifica e rimuove quelle righe corrotte.
"""
from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.coaching.fitness_test_processor import PLAUSIBLE_BOUNDS
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Logica bounds-check per disciplina
# ============================================================================

def _check_row(row: dict) -> tuple[bool, str, float | None, tuple[int, int] | None]:
    """Ritorna (is_out_of_bounds, field_label, value, bounds).

    Returns (False, ...) se la riga non ha valore da controllare o è nei bounds.
    Returns (True, ...) se il valore è fuori range.
    """
    discipline = row.get("discipline", "")

    if discipline == "bike":
        val = row.get("ftp_w")
        if val is None:
            return False, "ftp_w", None, None
        lo, hi = PLAUSIBLE_BOUNDS["ftp_bike_20min"]
        label = f"ftp_w={val}W"
        bounds = (lo, hi)
        if not (lo <= val <= hi):
            return True, label, val, bounds
        return False, label, val, bounds

    elif discipline == "run":
        val = row.get("threshold_pace_s_per_km")
        if val is None:
            return False, "threshold_pace_s_per_km", None, None
        lo, hi = PLAUSIBLE_BOUNDS["threshold_run_30min"]
        label = f"threshold={val} s/km"
        bounds = (lo, hi)
        if not (lo <= val <= hi):
            return True, label, val, bounds
        return False, label, val, bounds

    elif discipline == "swim":
        val = row.get("css_pace_s_per_100m")
        if val is None:
            return False, "css_pace_s_per_100m", None, None
        lo, hi = PLAUSIBLE_BOUNDS["css_swim_400_200"]
        label = f"css={val} s/100m"
        bounds = (lo, hi)
        if not (lo <= val <= hi):
            return True, label, val, bounds
        return False, label, val, bounds

    return False, "(unknown discipline)", None, None


# ============================================================================
# main
# ============================================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Cleanup physiology_zones: cancella righe con valori fuori bounds fisiologici."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Esegue il DELETE. Senza questo flag → dry run (nessuna modifica al DB).",
    )
    args = parser.parse_args()

    sb = get_supabase()

    # Fetch all rows
    res = (
        sb.table("physiology_zones")
        .select("id,discipline,valid_from,method,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m")
        .execute()
    )
    rows = res.data or []

    # Identify out-of-bounds rows
    out_of_bounds: list[dict] = []
    for row in rows:
        is_oob, label, value, bounds = _check_row(row)
        if is_oob:
            out_of_bounds.append({
                "id": row["id"],
                "discipline": row.get("discipline", ""),
                "valid_from": row.get("valid_from", ""),
                "method": row.get("method", ""),
                "label": label,
                "bounds": bounds,
            })

    # -----------------------------------------------------------------------
    # DRY RUN path (no --confirm)
    # -----------------------------------------------------------------------
    if not args.confirm:
        print()
        print("=== Cleanup physiology_zones (DRY RUN) ===")

        if not out_of_bounds:
            print("Nessuna riga fuori bounds. DB già pulito.")
            print()
            return

        print("Righe fuori bounds che verrebbero cancellate:")
        print()

        counts: dict[str, int] = {"bike": 0, "run": 0, "swim": 0}
        for item in out_of_bounds:
            disc = item["discipline"]
            lo, hi = item["bounds"]
            unit_suffix = ""
            if disc == "bike":
                unit_suffix = "W"
                range_str = f"{lo}-{hi}W"
            elif disc == "run":
                unit_suffix = " s/km"
                range_str = f"{lo}-{hi} s/km"
            elif disc == "swim":
                unit_suffix = " s/100m"
                range_str = f"{lo}-{hi} s/100m"
            else:
                range_str = f"{lo}-{hi}"

            print(
                f"  [{disc}] id={item['id']}  {item['label']}  "
                f"FUORI RANGE ({range_str})  "
                f"(metodo: {item['method']}, data: {item['valid_from']})"
            )
            if disc in counts:
                counts[disc] += 1

        print()
        total = len(out_of_bounds)
        print(
            f"Totale: {total} righe da cancellare "
            f"({counts['bike']} disciplina bike, "
            f"{counts['run']} disciplina run, "
            f"{counts['swim']} disciplina swim)"
        )
        print("Nessuna modifica al DB. Rieseguire con --confirm per cancellare.")
        print()
        return

    # -----------------------------------------------------------------------
    # CONFIRM path
    # -----------------------------------------------------------------------
    print()
    print("=== Cleanup physiology_zones (CONFIRM) ===")

    if not out_of_bounds:
        print("Nessuna riga fuori bounds. DB già pulito. Nessuna cancellazione effettuata.")
        print()
        return

    print("Cancellazione in corso...")

    deleted_counts: dict[str, int] = {"bike": 0, "run": 0, "swim": 0}
    total_deleted = 0

    for item in out_of_bounds:
        row_id = item["id"]
        disc = item["discipline"]
        try:
            logger.info(
                "DELETE physiology_zones id=%s  discipline=%s  %s  metodo=%s  data=%s",
                row_id,
                disc,
                item["label"],
                item["method"],
                item["valid_from"],
            )
            sb.table("physiology_zones").delete().eq("id", row_id).execute()
            print(
                f"  DELETED [{disc}] id={row_id}  {item['label']}  "
                f"(metodo: {item['method']}, data: {item['valid_from']})"
            )
            if disc in deleted_counts:
                deleted_counts[disc] += 1
            total_deleted += 1
        except Exception:
            logger.exception(
                "Errore durante DELETE id=%s discipline=%s — continuo con le righe rimanenti",
                row_id,
                disc,
            )

    print()
    print(
        f"Cancellate: {total_deleted} righe totali "
        f"(bike: {deleted_counts['bike']}, "
        f"run: {deleted_counts['run']}, "
        f"swim: {deleted_counts['swim']})"
    )
    print()


if __name__ == "__main__": main()
