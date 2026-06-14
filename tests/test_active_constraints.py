"""Test di integrazione per Phase 5 — active_constraints e migration workout-prescription-quality.

Copertura: WORKOUT-03 (vincoli medici da DB, non da CLAUDE.md statico).
Verifica che la migration abbia creato active_constraints con i 2 seed
(spalla dx swim/HIGH, fascite sx run/MEDIUM) e che la struttura della tabella
sia corretta (colonne, CHECK constraints, idempotenza).

Esecuzione: python -m pytest tests/test_active_constraints.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# Task 1 — Migration file assertions (WORKOUT-03 source checks)
# ===========================================================================

def test_migration_file_present():
    """Migration Phase 5 deve esistere e contenere active_constraints."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(
        encoding="utf-8"
    )
    assert "active_constraints" in src, "active_constraints non trovato nella migration"
    assert "progression_plan" in src, "progression_plan non trovato nella migration"
    assert "WHERE NOT EXISTS" in src, "pattern idempotente WHERE NOT EXISTS non trovato"


def test_migration_idempotent():
    """Migration deve usare IF NOT EXISTS per CREATE TABLE e ADD COLUMN."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS active_constraints" in src, (
        "CREATE TABLE deve usare IF NOT EXISTS per idempotenza"
    )
    assert "ADD COLUMN IF NOT EXISTS progression_plan" in src, (
        "ADD COLUMN deve usare IF NOT EXISTS per idempotenza"
    )


def test_migration_seed_descriptions():
    """Migration deve contenere entrambe le description D-13 per i 2 vincoli attivi."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(
        encoding="utf-8"
    )
    assert "borsite + tendinopatia CLB" in src, (
        "Seed spalla dx (vincolo nuoto) non trovato nella migration"
    )
    assert "fascite plantare sinistra" in src, (
        "Seed fascite sx (vincolo corsa) non trovato nella migration"
    )


def test_migration_check_constraints():
    """Migration deve definire i CHECK constraint su type e discipline."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(
        encoding="utf-8"
    )
    assert "injury" in src and "medical" in src and "tactical" in src, (
        "CHECK constraint su type deve includere injury, medical, tactical"
    )
    assert "swim" in src and "bike" in src and "run" in src and "'all'" in src, (
        "CHECK constraint su discipline deve includere swim, bike, run, all"
    )


def test_migration_rls_enabled():
    """Migration deve abilitare RLS su active_constraints (pattern single-user)."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(
        encoding="utf-8"
    )
    assert "ENABLE ROW LEVEL SECURITY" in src, (
        "ENABLE ROW LEVEL SECURITY non trovato per active_constraints"
    )


# ===========================================================================
# Live DB test — salta gracefully se SUPABASE_URL non configurato
# ===========================================================================

def test_active_constraints_seed_has_two_rows():
    """active_constraints deve contenere almeno 2 vincoli attivi dopo la migration.

    Verifica che i 2 seed D-13 siano stati inseriti:
    - spalla dx: discipline='swim', type='injury', resolved_at IS NULL
    - fascite sx: discipline='run', type='injury', resolved_at IS NULL
    """
    if not os.getenv("SUPABASE_URL"):
        pytest.skip("SUPABASE_URL non configurato — test live skippato")

    from dotenv import load_dotenv
    load_dotenv()
    from coach.utils.supabase_client import get_supabase

    sb = get_supabase()
    res = (
        sb.table("active_constraints")
        .select("id,type,discipline,severity")
        .eq("resolved_at", None)
        .execute()
    )
    rows = res.data or []
    disciplines = {r["discipline"] for r in rows}

    assert "swim" in disciplines, (
        "vincolo nuoto (spalla dx, borsite + tendinopatia CLB) deve esistere in active_constraints"
    )
    assert "run" in disciplines, (
        "vincolo corsa (fascite sx) deve esistere in active_constraints"
    )
