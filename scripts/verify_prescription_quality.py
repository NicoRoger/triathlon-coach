"""Verifica live della qualità delle prescrizioni Phase 5.

Phase gate script: valuta WORKOUT-03 (automatico) con esito bool e riepilogo passed/N.
WORKOUT-01/02/04/05 restano nella checklist manuale (richiedono verifica LLM in Claude.ai).
Nessun exit automatico — l'operatore legge l'output e decide.

Sezioni:
  - active_constraints: vincoli medici attivi (WORKOUT-03) → bool
  - physiology_zones age: freschezza delle zone fisiologiche per disciplina → bool
  - mesocycles progression_plan: presenza del piano di progressione nel mesociclo attivo → bool
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

def _verify_active_constraints(sb) -> bool:
    """Verifica WORKOUT-03: active_constraints ha i 2 seed e resolved_at IS NULL.

    Ritorna True se almeno 2 vincoli attivi esistono con discipline swim e run.
    Ritorna False se < 2 vincoli attivi o se manca swim o run.
    """
    print("=== Active Constraints (WORKOUT-03) ===")
    ok = True
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
            ok = False
        # Verifica che swim e run siano entrambi presenti
        active_disciplines = {r.get("discipline") for r in active}
        if "swim" not in active_disciplines:
            print("ATTENZIONE: vincolo 'swim' non trovato — seed spalla dx mancante")
            ok = False
        if "run" not in active_disciplines:
            print("ATTENZIONE: vincolo 'run' non trovato — seed fascite sx mancante")
            ok = False
        if ok:
            print("  [OK] 2+ vincoli attivi con discipline swim e run presenti")
    except Exception as exc:
        print(f"ERRORE sezione active_constraints: {exc}")
        ok = False
    print()
    return ok


def _verify_physiology_zones_age(sb) -> bool:
    """Verifica freschezza zone fisiologiche per disciplina (WORKOUT-03 prereq).

    Sezione informativa: segnala age > 42 giorni con ATTENZIONE ma NON forza fail.
    Ritorna False solo in caso di eccezione imprevista.
    """
    print("=== Physiology Zones — freschezza ===")
    ok = True
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
                    flag = " -- ATTENZIONE: zone obsolete (>42gg), considera test fitness" if age_days > 42 else ""
                    print(f"  {discipline}: valid_from={valid_from} ({age_days} giorni){flag}")
                except (ValueError, TypeError):
                    print(f"  {discipline}: valid_from non parsabile: {valid_from_str!r}")
            else:
                print(f"  {discipline}: valid_from=NULL — zone mai aggiornate")
        if not rows:
            print("  Nessuna zona fisiologica trovata — testare FTP/CSS/threshold prima di prescrivere.")
    except Exception as exc:
        print(f"ERRORE sezione physiology_zones: {exc}")
        ok = False
    print()
    return ok


def _verify_mesocycles_progression_plan(sb) -> bool:
    """Verifica presenza progression_plan nel mesociclo attivo (WORKOUT-04).

    Gestisce gracefully il caso "nessun mesociclo" (stato valido — Pitfall 6).
    Ritorna False solo in caso di eccezione imprevista.
    """
    print("=== Mesocycles — progression_plan (WORKOUT-04) ===")
    ok = True
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
            print("  Nessun mesociclo attivo trovato — stato valido se non ancora pianificato.")
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
        ok = False
    print()
    return ok


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

    results = [
        _verify_active_constraints(sb),
        _verify_physiology_zones_age(sb),
        _verify_mesocycles_progression_plan(sb),
    ]

    passed = sum(1 for r in results if r)
    print(f"=== Riepilogo: {passed}/{len(results)} OK ===")
    print()

    _print_manual_checklist()


if __name__ == "__main__":
    main()
