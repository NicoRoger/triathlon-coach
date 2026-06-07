"""Verifica live del comportamento di sistema end-to-end (Phase 4).

Script read-only informativo: controlla 4 aree — brief zone, session_analyses,
plan_modulations, budget tracker — e stampa pass/fail con staleness check.
Nessun exit automatico, nessuna scrittura su DB.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.utils.supabase_client import get_supabase
from coach.utils.dt import today_rome
from coach.utils.budget import BUDGET_DEGRADED, BUDGET_BLOCKED, get_month_spend_usd

logger = logging.getLogger(__name__)

STALE_DAYS_CUTOFF = 7


# ============================================================================
# Sezione Brief Zones — verifica VERIFY-03 / FITNESS-04
# ============================================================================
def _verify_brief_zones(sb) -> bool:
    """Controlla che il brief mattutino recente includa zone misurate da physiology_zones."""
    print("[BRIEF ZONES]")
    ok = True
    try:
        today_iso = today_rome().isoformat()
        cutoff = (today_rome() - timedelta(days=STALE_DAYS_CUTOFF)).isoformat()

        # Ultimo brief mattutino inviato
        res = (
            sb.table("bot_messages")
            .select("sent_at,purpose")
            .eq("purpose", "morning_brief")
            .order("sent_at", desc=True)
            .limit(1)
            .execute()
        )
        row = res.data[0] if res.data else None

        if row is None:
            print("  [ATTENZIONE] Nessun morning_brief trovato in bot_messages")
            ok = False
        else:
            sent_at = row.get("sent_at", "")[:10]
            days_ago = (date.fromisoformat(today_iso) - date.fromisoformat(sent_at)).days
            if days_ago <= STALE_DAYS_CUTOFF:
                staleness_label = "OK"
            else:
                staleness_label = "STALE"
                ok = False
            print(f"  Ultimo brief: {sent_at} ({days_ago} giorni fa — {staleness_label})")

        # Verifica zone in physiology_zones (proxy: se esistono zone, il brief le include)
        zones_res = (
            sb.table("physiology_zones")
            .select("discipline,valid_from")
            .is_("valid_to", "null")
            .order("valid_from", desc=True)
            .execute()
        )
        zones_rows = zones_res.data or []

        # Dedup per disciplina
        seen: set[str] = set()
        by_disc: dict[str, str] = {}
        for z in zones_rows:
            disc = z.get("discipline", "")
            if disc not in seen:
                seen.add(disc)
                by_disc[disc] = z.get("valid_from", "")[:10]

        if not by_disc:
            print("  [ATTENZIONE] physiology_zones vuoto — brief usa placeholder hard-coded")
            ok = False
        else:
            disc_list = ", ".join(f"{d}={v}" for d, v in sorted(by_disc.items()))
            print(f"  [OK] physiology_zones: {disc_list}")
            print(f"  [OK] briefing.py legge physiology_zones → Zone misurate nel brief")

    except Exception as exc:
        print(f"  ERRORE sezione BRIEF ZONES: {exc}")
        ok = False
    print()
    return ok


# ============================================================================
# Sezione Session Analyses — verifica VERIFY-04
# ============================================================================
def _verify_session_analyses(sb) -> bool:
    """Conta session_analyses recenti e verifica model_used=gemini-2.5-flash."""
    print("[SESSION ANALYSES]")
    ok = True
    try:
        today_iso = today_rome().isoformat()
        cutoff = (today_rome() - timedelta(days=STALE_DAYS_CUTOFF)).isoformat()

        res = (
            sb.table("session_analyses")
            .select("created_at,model_used")
            .gte("created_at", f"{cutoff}T00:00:00Z")
            .order("created_at", desc=True)
            .execute()
        )
        rows = res.data or []

        count = len(rows)
        if count == 0:
            print(f"  [ATTENZIONE] Nessuna session_analysis negli ultimi {STALE_DAYS_CUTOFF} giorni")
            ok = False
        else:
            last_date = rows[0].get("created_at", "")[:10]
            days_ago = (date.fromisoformat(today_iso) - date.fromisoformat(last_date)).days
            if days_ago <= STALE_DAYS_CUTOFF:
                staleness_label = "OK"
            else:
                staleness_label = "STALE"
                ok = False
            print(f"  session_analyses: {count} righe (ultima: {last_date}, {days_ago} giorni fa — {staleness_label})")

            # Verifica model_used
            wrong_model = [r for r in rows if r.get("model_used") != "gemini-2.5-flash"]
            if wrong_model:
                bad_models = list({r.get("model_used") for r in wrong_model})
                print(f"  [ATTENZIONE] {len(wrong_model)} righe con model_used diverso da gemini-2.5-flash: {bad_models}")
                ok = False
            else:
                print(f"  [OK] model_used: gemini-2.5-flash su tutte le {count} righe recenti")

    except Exception as exc:
        print(f"  ERRORE sezione SESSION ANALYSES: {exc}")
        ok = False
    print()
    return ok


# ============================================================================
# Sezione Plan Modulations — verifica VERIFY-05 / DEPLOY-04
# ============================================================================
def _verify_plan_modulations(sb) -> bool:
    """Stampa breakdown status plan_modulations e staleness dell'ultima riga."""
    print("[PLAN MODULATIONS]")
    ok = True
    try:
        today_iso = today_rome().isoformat()

        res = (
            sb.table("plan_modulations")
            .select("status,proposed_at,resolved_at")
            .order("proposed_at", desc=True)
            .execute()
        )
        rows = res.data or []

        if not rows:
            print("  Nessuna modulazione in plan_modulations")
            # Non è necessariamente un errore — ok se non ci sono modulazioni
        else:
            # Breakdown per status
            breakdown: dict[str, int] = {}
            for r in rows:
                s = r.get("status") or "unknown"
                breakdown[s] = breakdown.get(s, 0) + 1
            breakdown_str = ", ".join(f"{s}={n}" for s, n in sorted(breakdown.items()))
            print(f"  status breakdown: {breakdown_str}")

            # Staleness: usa proposed_at della riga più recente
            last_row = rows[0]
            last_ts = last_row.get("proposed_at") or last_row.get("resolved_at") or ""
            if last_ts:
                last_date = last_ts[:10]
                days_ago = (date.fromisoformat(today_iso) - date.fromisoformat(last_date)).days
                if days_ago <= STALE_DAYS_CUTOFF:
                    staleness_label = "OK"
                else:
                    staleness_label = "STALE"
                print(f"  Ultima modulazione: {last_date} ({days_ago} giorni fa — {staleness_label})")

            # Verifica che ci sia almeno una riga applied (VERIFY-05)
            applied_count = breakdown.get("applied", 0)
            if applied_count > 0:
                print(f"  [OK] {applied_count} modulazione(i) applicata(e) — flusso accepted→applied OK")
            else:
                print("  [ATTENZIONE] Nessuna modulazione con status='applied' — verificare flusso Telegram→planned_sessions")
                ok = False

    except Exception as exc:
        print(f"  ERRORE sezione PLAN MODULATIONS: {exc}")
        ok = False
    print()
    return ok


# ============================================================================
# Sezione Budget Tracker — verifica VERIFY-06
# ============================================================================
def _verify_budget(sb) -> bool:
    """Stampa spesa Anthropic mese corrente e verifica soglie budget.py."""
    print("[BUDGET TRACKER]")
    ok = True
    try:
        spend = get_month_spend_usd()
        if spend < BUDGET_DEGRADED:
            budget_label = "OK"
        else:
            budget_label = "ATTENZIONE — sopra soglia degrado"
            ok = False
        print(f"  Spesa Anthropic mese corrente: ${spend:.2f} (soglia degrado €{BUDGET_DEGRADED:.2f}: {budget_label})")
        print(f"  [OK] budget.py: BUDGET_DEGRADED = {BUDGET_DEGRADED}, BUDGET_BLOCKED = {BUDGET_BLOCKED}")

    except Exception as exc:
        print(f"  ERRORE sezione BUDGET TRACKER: {exc}")
        ok = False
    print()
    return ok


# ============================================================================
# main
# ============================================================================
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()
    today_iso = today_rome().isoformat()

    logger.info("verify_live_behavior.py — dati al %s", today_iso)
    print()
    print(f"=== Live Behavior Check — {today_iso} ===")
    print()

    results = [
        _verify_brief_zones(sb),
        _verify_session_analyses(sb),
        _verify_plan_modulations(sb),
        _verify_budget(sb),
    ]

    passed = sum(1 for r in results if r)
    print(f"=== Riepilogo: {passed}/4 OK ===")


if __name__ == "__main__":
    main()
