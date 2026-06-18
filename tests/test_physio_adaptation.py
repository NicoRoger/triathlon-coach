"""Test statici per Phase 6 — migration SQL + skill propose_session.md (ADAPT-02).

Copertura:
- ADAPT-02: migration SQL contiene colonne session_analyses + seed belief idempotente
- ADAPT-02: propose_session.md contiene step lettura active_beliefs + tag [athlete-belief:]

Questi test sono GREEN quando i file esistono (creati in plan 01 e plan 03).
Il test test_skill_active_beliefs_step è RED Wave 0 finché plan 03 non aggiorna propose_session.md.

Esecuzione: python -m pytest tests/test_physio_adaptation.py -v
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# Task 1 — Migration SQL: colonne session_analyses (ADAPT-01)
# ===========================================================================

def test_migration_session_analyses_columns():
    """Migration deve contenere le 3 nuove colonne su session_analyses con IF NOT EXISTS."""
    src = (ROOT / "migrations" / "2026-06-08-physiological-adaptation.sql").read_text(
        encoding="utf-8"
    )
    assert "fatigue_type" in src, (
        "fatigue_type non trovato nella migration"
    )
    assert "fatigue_confidence" in src, (
        "fatigue_confidence non trovato nella migration"
    )
    assert "IF NOT EXISTS" in src, (
        "Pattern IF NOT EXISTS non trovato nella migration (deve essere idempotente)"
    )


# ===========================================================================
# Task 1 — Migration SQL: seed belief idempotente (ADAPT-02)
# ===========================================================================

def test_migration_belief_seed_idempotent():
    """Migration deve contenere INSERT belief con ON CONFLICT DO NOTHING e endurance_failure_type."""
    src = (ROOT / "migrations" / "2026-06-08-physiological-adaptation.sql").read_text(
        encoding="utf-8"
    )
    assert "ON CONFLICT (belief_key) DO NOTHING" in src, (
        "ON CONFLICT (belief_key) DO NOTHING non trovato — seed non è idempotente"
    )
    assert "endurance_failure_type" in src, (
        "endurance_failure_type non trovato nella migration — seed belief ADAPT-02 mancante"
    )


# ===========================================================================
# Task 3 (plan 03) — Skill propose_session.md: step active_beliefs (ADAPT-02)
# Wave 0 RED: questo test è RED finché plan 03 non aggiorna propose_session.md
# ===========================================================================

def test_skill_active_beliefs_step():
    """propose_session.md deve contenere step lettura active_beliefs e tag [athlete-belief:."""
    src = (ROOT / "skills" / "propose_session.md").read_text(
        encoding="utf-8"
    )
    assert "active_beliefs" in src, (
        "active_beliefs non trovato in propose_session.md — Step 2 non esteso per ADAPT-02"
    )
    assert "[athlete-belief:" in src, (
        "[athlete-belief: non trovato in propose_session.md — tag citation format non aggiunto"
    )
