"""Verifica live delle physiology zones dal DB di produzione (FTP, Threshold, CSS).

Script informativo read-only: stampa 3 sezioni (BIKE, RUN, SWIM) con bounds check
[OK/FUORI RANGE] e confronto con i campi corrispondenti in CLAUDE.md.
Se la tabella è vuota, stampa istruzioni per triggerare il processore.

Nessun exit automatico, nessuna scrittura su DB — solo lettura e report.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.coaching.fitness_test_processor import (
    PLAUSIBLE_BOUNDS,
    _fmt_pace,
    _fmt_swim_pace,
)
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

CLAUDE_MD_PATH = Path(__file__).resolve().parent.parent / "CLAUDE.md"


# ============================================================================
# Lettura campi CLAUDE.md
# ============================================================================
def _read_claude_md_fields() -> dict[str, str]:
    """Legge CLAUDE.md ed estrae ftp_attuale_w, threshold_pace_per_km, css_attuale_per_100m."""
    fields: dict[str, str] = {
        "ftp_attuale_w": "(non trovato)",
        "threshold_pace_per_km": "(non trovato)",
        "css_attuale_per_100m": "(non trovato)",
    }
    try:
        content = CLAUDE_MD_PATH.read_text(encoding="utf-8")
        for field in fields:
            m = re.search(rf"{re.escape(field)}:\s*(.+)", content)
            if m:
                fields[field] = m.group(1).strip()
    except Exception as exc:
        logger.warning("Impossibile leggere CLAUDE.md: %s", exc)
    return fields


# ============================================================================
# Sezione Physiology Zones — verifica FITNESS-02 / VERIFY-02
# ============================================================================
def _verify_physiology_zones(sb) -> None:
    """Queries physiology_zones, prints per-discipline sections with bounds and CLAUDE.md comparison."""
    print("=== Physiology Zones ===")
    print()

    try:
        res = (
            sb.table("physiology_zones")
            .select("discipline,valid_from,method,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m,notes")
            .order("valid_from", desc=True)
            .execute()
        )
        rows = res.data or []
    except Exception as exc:
        print(f"ERRORE lettura physiology_zones: {exc}")
        print()
        return

    if not rows:
        print(
            "physiology_zones: vuoto — test eseguiti ma non processati. "
            "Usare: PYTHONPATH=. python scripts/trigger_fitness_processor.py"
        )
        print()
        return

    claude_fields = _read_claude_md_fields()

    # Prendi il record più recente per disciplina
    seen: set[str] = set()
    by_discipline: dict[str, dict] = {}
    for row in rows:
        disc = row.get("discipline") or ""
        if disc not in seen:
            seen.add(disc)
            by_discipline[disc] = row

    # ── BIKE ─────────────────────────────────────────────────────────────────
    print("BIKE:")
    try:
        bike_row = by_discipline.get("bike")
        if not bike_row:
            print("  (nessun dato)")
        else:
            ftp_w = bike_row.get("ftp_w")
            method = bike_row.get("method") or "—"
            valid_from = bike_row.get("valid_from") or "—"

            if ftp_w is not None:
                ftp_val = float(ftp_w)
                # Bounds: usa ftp_bike_20min bounds (80-450W), comune a entrambi i metodi FTP
                bounds = PLAUSIBLE_BOUNDS.get("ftp_bike_20min", (80, 450))
                if bounds[0] <= ftp_val <= bounds[1]:
                    bounds_label = f"[OK — range {bounds[0]}-{bounds[1]}W]"
                else:
                    bounds_label = f"[FUORI RANGE — range {bounds[0]}-{bounds[1]}W]"
                print(
                    f"  FTP: {round(ftp_val)}W  {bounds_label}  "
                    f"(metodo: {method}, data: {valid_from})"
                )

                # Confronto CLAUDE.md
                claude_ftp_raw = claude_fields.get("ftp_attuale_w", "")
                # Estrai il numero dal valore CLAUDE.md (es. "240W (test 2026-06-03)" → "240")
                claude_ftp_match = re.search(r"(\d+)", claude_ftp_raw)
                if claude_ftp_match:
                    claude_ftp_num = int(claude_ftp_match.group(1))
                    if round(ftp_val) == claude_ftp_num:
                        comparison = "match"
                    else:
                        comparison = (
                            f"DISCREPANZA: DB={round(ftp_val)}W "
                            f"CLAUDE.md={claude_ftp_num}W"
                        )
                else:
                    comparison = f"DISCREPANZA: DB={round(ftp_val)}W CLAUDE.md={claude_ftp_raw}"
                print(f"  CLAUDE.md ftp_attuale_w: {claude_ftp_raw}  {comparison}")
            else:
                print(
                    f"  FTP: (nessun valore)  (metodo: {method}, data: {valid_from})"
                )
    except Exception as exc:
        print(f"  ERRORE sezione BIKE: {exc}")
    print()

    # ── RUN ──────────────────────────────────────────────────────────────────
    print("RUN:")
    try:
        run_row = by_discipline.get("run")
        if not run_row:
            print("  (nessun dato)")
        else:
            threshold_s = run_row.get("threshold_pace_s_per_km")
            method = run_row.get("method") or "—"
            valid_from = run_row.get("valid_from") or "—"

            if threshold_s is not None:
                threshold_val = float(threshold_s)
                bounds = PLAUSIBLE_BOUNDS.get("threshold_run_30min", (150, 360))
                if bounds[0] <= threshold_val <= bounds[1]:
                    bounds_label = f"[OK — range {bounds[0]}-{bounds[1]} s/km]"
                else:
                    bounds_label = f"[FUORI RANGE — range {bounds[0]}-{bounds[1]} s/km]"
                pace_str = _fmt_pace(threshold_val)
                print(
                    f"  Threshold: {pace_str}/km ({round(threshold_val)} s/km)  "
                    f"{bounds_label}  (metodo: {method}, data: {valid_from})"
                )

                # Confronto CLAUDE.md
                claude_pace_raw = claude_fields.get("threshold_pace_per_km", "")
                # Estrai il pace (MM:SS) dal valore CLAUDE.md
                claude_pace_match = re.search(r"(\d+:\d{2})", claude_pace_raw)
                if claude_pace_match:
                    claude_pace_str = claude_pace_match.group(1)
                    if pace_str == claude_pace_str:
                        comparison = "match"
                    else:
                        comparison = (
                            f"DISCREPANZA: DB={pace_str}/km "
                            f"CLAUDE.md={claude_pace_str}/km"
                        )
                else:
                    comparison = f"DISCREPANZA: DB={pace_str}/km CLAUDE.md={claude_pace_raw}"
                print(f"  CLAUDE.md threshold_pace_per_km: {claude_pace_raw}  {comparison}")
            else:
                print(
                    f"  Threshold: (nessun valore)  (metodo: {method}, data: {valid_from})"
                )
    except Exception as exc:
        print(f"  ERRORE sezione RUN: {exc}")
    print()

    # ── SWIM ─────────────────────────────────────────────────────────────────
    print("SWIM:")
    try:
        swim_row = by_discipline.get("swim")
        if not swim_row:
            print("  (nessun dato)")
        else:
            css_s = swim_row.get("css_pace_s_per_100m")
            method = swim_row.get("method") or "—"
            valid_from = swim_row.get("valid_from") or "—"

            if css_s is not None:
                css_val = float(css_s)
                bounds = PLAUSIBLE_BOUNDS.get("css_swim_400_200", (70, 150))
                if bounds[0] <= css_val <= bounds[1]:
                    bounds_label = f"[OK — range {bounds[0]}-{bounds[1]} s/100m]"
                else:
                    bounds_label = f"[FUORI RANGE — range {bounds[0]}-{bounds[1]} s/100m]"
                swim_str = _fmt_swim_pace(css_val)
                print(
                    f"  CSS: {swim_str}/100m ({round(css_val)} s/100m)  "
                    f"{bounds_label}  (metodo: {method}, data: {valid_from})"
                )

                # Confronto CLAUDE.md
                claude_css_raw = claude_fields.get("css_attuale_per_100m", "")
                claude_css_match = re.search(r"(\d+:\d{2})", claude_css_raw)
                if claude_css_match:
                    claude_css_str = claude_css_match.group(1)
                    if swim_str == claude_css_str:
                        comparison = "match"
                    else:
                        comparison = (
                            f"DISCREPANZA: DB={swim_str}/100m "
                            f"CLAUDE.md={claude_css_str}/100m"
                        )
                else:
                    comparison = f"DISCREPANZA: DB={swim_str}/100m CLAUDE.md={claude_css_raw}"
                print(f"  CLAUDE.md css_attuale_per_100m: {claude_css_raw}  {comparison}")
            else:
                print(
                    f"  CSS: (nessun valore)  (metodo: {method}, data: {valid_from})"
                )
    except Exception as exc:
        print(f"  ERRORE sezione SWIM: {exc}")
    print()


# ============================================================================
# main
# ============================================================================
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()

    logger.info("verify_physiology.py — physiology zones report")
    print()

    _verify_physiology_zones(sb)


if __name__ == "__main__":
    main()
