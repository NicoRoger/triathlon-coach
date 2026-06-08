"""Verifica live della qualità delle prescrizioni Phase 5.

Script informativo: stampa sezioni leggibili per ispezione visiva di WORKOUT-03.
Nessun exit automatico — l'operatore legge l'output e decide.

Sezioni:
  - active_constraints: vincoli medici attivi (WORKOUT-03)
  - physiology_zones age: freschezza delle zone fisiologiche per disciplina
  - mesocycles progression_plan: presenza del piano di progressione nel mesociclo attivo
  - checklist manuale: WORKOUT-01/02/04/05 (verifica manuale output LLM)

Esecuzione: python -m scripts.verify_prescription_quality
         o: python scripts/verify_prescription_quality.py
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Sezioni verify
# ============================================================================

def _verify_active_constraints(sb) -> None:
    """Verifica WORKOUT-03: active_constraints ha i 2 seed e resolved_at IS NULL."""
    print("=== Active Constraints (WORKOUT-03) ===")
    try:
        res = (
            sb.table("active_constraints")
            .select("id,type,discipline,description,severity,created_at,resolved_at")
            .execute()
        )
        rows = res.data or []
        active = [r for r in rows if r.get("resolved_at") is None]
        print(f"Vincoli totali: {len(rows)} | Attivi: {len(active)}")
        for r in active:
            severity = (r.get("severity") or "n/a").upper()
            discipline = (r.get("discipline") or "?").upper()
            description = (r.get("description") or "")[:80]
            print(f"  [{severity}] {discipline}: {description}")
        if len(active) < 2:
            print("ATTENZIONE: meno di 2 vincoli attivi — seed migration non eseguito?")
    except Exception as exc:
        print(f"ERRORE sezione active_constraints: {exc}")
    print()


def _verify_physiology_zones_age(sb) -> None:
    """Verifica freschezza zone fisiologiche per disciplina (WORKOUT-03 prereq)."""
    print("=== Physiology Zones — freschezza ===")
    try:
        res = (
            sb.table("physiology_zones")
            .select("discipline,method,valid_from,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m")
            .execute()
        )
        rows = res.data or []
        today = date.today()
        for r in rows:
            discipline = (r.get("discipline") or "?").upper()
            valid_from_str = r.get("valid_from")
            if valid_from_str:
                try:
                    valid_from = date.fromisoformat(str(valid_from_str)[:10])
                    age_days = (today - valid_from).days
                    flag = " ⚠️ OBSOLETE (>42gg)" if age_days > 42 else ""
                    print(f"  {discipline}: valid_from={valid_from} ({age_days} giorni){flag}")
                except (ValueError, TypeError):
                    print(f"  {discipline}: valid_from non parsabile: {valid_from_str!r}")
            else:
                print(f"  {discipline}: valid_from=NULL — zone mai aggiornate")
        if not rows:
            print("ATTENZIONE: nessuna zona fisiologica trovata — testare FTP/CSS/threshold prima di prescrivere.")
    except Exception as exc:
        print(f"ERRORE sezione physiology_zones: {exc}")
    print()


def _verify_mesocycles_progression_plan(sb) -> None:
    """Verifica presenza progression_plan nel mesociclo attivo (WORKOUT-04)."""
    print("=== Mesocycles — progression_plan (WORKOUT-04) ===")
    try:
        today_str = date.today().isoformat()
        res = (
            sb.table("mesocycles")
            .select("id,name,phase,start_date,end_date,progression_plan")
            .lte("start_date", today_str)
            .gte("end_date", today_str)
            .execute()
        )
        rows = res.data or []
        if not rows:
            print("  Nessun mesociclo attivo trovato.")
        for r in rows:
            name = r.get("name", "?")
            phase = r.get("phase", "?")
            pp = r.get("progression_plan")
            if pp:
                keys = list(pp.keys()) if isinstance(pp, dict) else ["(non-dict)"]
                print(f"  {name} [{phase}]: progression_plan presente — chiavi: {keys}")
            else:
                print(f"  {name} [{phase}]: progression_plan=NULL — nessun piano di progressione esplicito")
    except Exception as exc:
        print(f"ERRORE sezione mesocycles: {exc}")
    print()


def _print_manual_checklist() -> None:
    """Stampa la checklist manuale per WORKOUT-01/02/04/05."""
    print("=== Checklist manuale (WORKOUT-01/02/04/05) ===")
    items = [
        "[ ] WORKOUT-01: proponi sessione in Claude.ai — verifica warmup/main/cooldown nel output",
        "[ ] WORKOUT-02: cambia FTP in DB, richiedi sessione — verifica che i watt cambino",
        "[ ] WORKOUT-04: verifica TSS proposto vs mesocycles.progression_plan",
        "[ ] WORKOUT-05: verifica distribuzione 80/20 nel piano settimanale",
    ]
    for item in items:
        print(f"  {item}")
    print()


# ============================================================================
# Entrypoint
# ============================================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()

    logger.info("verify_prescription_quality.py — Phase 5 WORKOUT check")
    print()

    _verify_active_constraints(sb)
    _verify_physiology_zones_age(sb)
    _verify_mesocycles_progression_plan(sb)
    _print_manual_checklist()


if __name__ == "__main__":
    main()
