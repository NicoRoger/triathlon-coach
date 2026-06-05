# Phase 1: Test Suite & Analytics Correctness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 1-test-suite-analytics-correctness
**Areas discussed:** Verifica "dati reali", Consecutive fatigue flag test, Readiness label (None)

---

## Verifica "dati reali" (ANALYTICS-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Script + DB live | Script Python che query Supabase con credenziali reali e stampa valori HRV baseline, z-score, readiness, risk | ✓ |
| Code audit solo | Leggere readiness.py/daily.py per confermare fix B1 nel codice — nessuna query DB | |
| Entrambi | Code audit veloce + spot-check DB reale | |

**User's choice:** Script + DB live (Recommended)
**Notes:** Script solo informativo (nessun exit 1 automatico), committato come `scripts/verify_analytics.py`. Tutti e 4 i check selezionati: HRV baseline/z-score, PMC CTL/ATL/TSB, readiness score+label, risk volume bucketing con date Rome.

---

## Script output format

| Option | Description | Selected |
|--------|-------------|----------|
| Solo informativo | Stampa e basta — nessun exit 1, ispezione visiva manuale | ✓ |
| Fail-fast con bounds check | Assert plausibilità con exit 1 se fuori range | |

**User's choice:** Solo informativo

---

## Script lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| File persistente in scripts/ | Committato, richiamabile manualmente, documentabile nel Makefile | ✓ |
| Usa e getta | Solo per Phase 1, output incollato nel VERIFICATION.md | |

**User's choice:** File persistente in scripts/

---

## Test logica "2 giorni consecutivi" (ANALYTICS-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Aggiungere test consecutivo | Test esplicito che verifica warning solo al 2° giorno consecutivo | |
| Copertura attuale OK | I 3 test B2 esistenti coprono il caso principale | ✓ |
| Fuori scope Phase 1 | Va in Phase 4 (live behavior) | |

**User's choice:** Copertura attuale OK

**Context:** I test B2 esistenti in `test_audit_resilience.py` coprono già:
- `test_b2_single_low_day_does_not_warn` — 1 giorno basso, nessun warning
- `test_b2_two_consecutive_low_days_warn` — 2 giorni consecutivi, warning scatta
- `test_b2_daily_excludes_today_from_recent_z` — oggi escluso da recent_z_scores

**Edge case non-consecutivo (D-05):**

| Option | Description | Selected |
|--------|-------------|----------|
| Copertura attuale OK | Non critico per Phase 1, backlog | ✓ |
| Aggiungi edge case non-consecutivo | Verifica ieri OK + 2fa basso + oggi basso = no warning | |
| Aggiungi + fix se sbagliato | Test + fix readiness.py se la logica è window-based non strettamente consecutiva | |

**User's choice:** Copertura attuale OK — edge case deferito al backlog

---

## Readiness label "(None)" — ANALYTICS-04

| Option | Description | Selected |
|--------|-------------|----------|
| Test su daily_metrics output | Assert in test esistente che `daily.compute_for()` scriva readiness_label non-null e readiness_score ∈ [0, 100] | ✓ |
| Niente da fare | Fix già in readiness.py (B11 testato), campo scritto correttamente | |
| Fix dead code + test | Fixare briefing_v1.py + test — anche se morto | |

**User's choice:** Test su daily_metrics output

**Context:** Il bug C1 (`(None)` in brief) è in `briefing_v1.py` — codice morto senza chiamanti. Il brief attivo `briefing.py` (v2) non renderizza `readiness_label`. Il rischio è che il campo in `daily_metrics` possa risultare null se `daily.compute_for()` non lo scrive correttamente.

---

## Claude's Discretion

- Struttura esatta del log output di `verify_analytics.py` — formato con sezioni `===` e valori numerici espliciti (proposto da Claude)
- Dove inserire il test ANALYTICS-04: nel blocco B3/B11 esistente in `test_audit_resilience.py` (non in un file nuovo) — scelta di coerenza con i pattern esistenti

## Deferred Ideas

- Edge case non-consecutivo per fatigue_warning — backlog
- Fix C1 in `briefing_v1.py` (codice morto) — se mai si riattiva v1
- Bounds-check automatico con exit 1 in `verify_analytics.py` come health check CI — Phase 3
