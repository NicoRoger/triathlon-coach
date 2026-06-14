---
phase: 04-live-behavior-verification
plan: "03"
subsystem: budget-tracker
tags: [budget, llm-routing, verify-06, tdd]
dependency_graph:
  requires: []
  provides: [VERIFY-06-budget-threshold-aligned]
  affects: [coach/utils/budget.py, tests/test_budget.py]
tech_stack:
  added: []
  patterns: [threshold-alignment, tdd-red-green]
key_files:
  modified:
    - coach/utils/budget.py
    - tests/test_budget.py
decisions:
  - "BUDGET_DEGRADED = 4.00 (era 4.50) — allineato a ROADMAP SC4; BUDGET_WARNING e BUDGET_DEGRADED ora coincidono"
  - "select_model ristrutturato: ramo 3-3.99 procede senza declasso; ramo 4.00-4.79 declassa opus→sonnet e sonnet/haiku→haiku"
  - "test_degraded_level aggiornato: con BUDGET_DEGRADED=4.00, projected=4.05 ritorna BLOCKED_NON_CRITICAL (non DEGRADED)"
metrics:
  duration: "15min"
  completed_date: "2026-06-07"
  tasks_completed: 1
  files_modified: 2
---

# Phase 04 Plan 03: Budget Threshold Alignment (VERIFY-06) Summary

**One-liner:** Soglia di degrado Sonnet→Haiku allineata a €4.00 via `BUDGET_DEGRADED = 4.00` con 7 nuovi test VERIFY-06 e ristrutturazione di `select_model`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Allinea soglia degrado Sonnet→Haiku a €4.00 | `19ca850` | `coach/utils/budget.py`, `tests/test_budget.py` |

## What Was Built

### coach/utils/budget.py

- `BUDGET_DEGRADED` modificato da `4.50` a `4.00` — allineato a ROADMAP SC4 ("soglia di degrado a €4.00 (Sonnet→Haiku) è configurata e verificata") e CONTEXT D-04
- Docstring modulo aggiornata: rimuove il range "4-4.50 → DEGRADED" e descrive correttamente ">=$4.00 → declasso"
- Commento esplicativo aggiunto sulla costante che spiega la coincidenza `BUDGET_WARNING == BUDGET_DEGRADED == 4.00`
- `select_model` ristrutturato in 4 rami chiari:
  - `< BUDGET_OK (3.00)`: procedi con preferenza
  - `< BUDGET_DEGRADED (4.00)`: warning range $3-$3.99, procedi con preferenza
  - `< BUDGET_BLOCKED (4.80)`: zona degrado, opus→sonnet / sonnet→haiku
  - `>= BUDGET_BLOCKED`: haiku (ma `check_budget_or_raise` bloccherà non-emergency)
- `check_budget_or_raise` invariato: funziona correttamente con la nuova soglia (ramo `projected > BUDGET_DEGRADED` ora a 4.00)
- `get_month_spend_usd` invariato: legge `cost_usd_estimated` da `api_usage` table — fonte reale della spesa Anthropic

### tests/test_budget.py

7 test nuovi aggiunti (VERIFY-06):
- `test_degraded_threshold_exact_at_4_00`: `select_model("sonnet", spend=4.00)` → haiku
- `test_below_degraded_threshold_no_downgrade`: `select_model("sonnet", spend=3.50)` → sonnet
- `test_degraded_threshold_exact_opus_to_sonnet`: `select_model("opus", spend=4.00)` → sonnet
- `test_blocked_forces_haiku_all`: a $4.85 sonnet→haiku e opus→haiku
- `test_verify06_hard_block_non_emergency`: projected > $4.80 + non-emergency → BudgetExceededError
- `test_verify06_hard_block_allows_emergency`: blocco hard non si applica a `emergency`
- `test_verify06_hard_block_race_week_critical`: `race_week_critical` è emergency, passa

2 test esistenti aggiornati per riflettere il nuovo comportamento:
- `test_degraded_level`: con BUDGET_DEGRADED=4.00, projected=4.05 → `BLOCKED_NON_CRITICAL` (non `DEGRADED`)
- `test_blocked_forces_haiku` → suddiviso in `test_degraded_zone_forces_haiku_for_sonnet` + `test_blocked_forces_haiku_all`

## Verification

```
PYTHONPATH=. python -m pytest tests/test_budget.py -v
23 passed in 1.73s

grep -n "BUDGET_DEGRADED" coach/utils/budget.py
→ BUDGET_DEGRADED = 4.00 (riga 46)

grep -n "cost_usd_estimated" coach/utils/budget.py | grep -v "^#"
→ 4 occorrenze (righe 74, 79, 83, 98, 254) — get_month_spend_usd legge da api_usage
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ramo select_model irraggiungibile con BUDGET_DEGRADED == BUDGET_WARNING**

- **Found during:** Task 1 (GREEN phase, dopo impostazione BUDGET_DEGRADED=4.00)
- **Issue:** Con `BUDGET_WARNING == BUDGET_DEGRADED == 4.00`, il ramo `elif spend < BUDGET_DEGRADED` diventava irraggiungibile perché già coperto dal ramo `elif spend < BUDGET_WARNING`. `select_model("opus", spend=4.10)` restituiva haiku invece di sonnet.
- **Fix:** Ristruttura `select_model` usando solo `BUDGET_OK` e `BUDGET_DEGRADED` come soglie (4 rami invece di 5), eliminando il ramo ridondante `elif spend < BUDGET_WARNING`.
- **Files modified:** `coach/utils/budget.py` (select_model)
- **Commit:** `19ca850`

**2. [Rule 1 - Bug] Test test_blocked_forces_haiku obsoleto con nuova semantica**

- **Found during:** Task 1 (GREEN phase)
- **Issue:** `test_blocked_forces_haiku` asseriva `select_model("opus", spend=4.60)` → haiku, ma con il nuovo `select_model` il range 4.00-4.79 applica opus→sonnet (non haiku totale).
- **Fix:** Split in `test_degraded_zone_forces_haiku_for_sonnet` (opus→sonnet a 4.60) e `test_blocked_forces_haiku_all` (haiku totale a 4.85).
- **Files modified:** `tests/test_budget.py`
- **Commit:** `19ca850`

### TDD Note

I test VERIFY-06 aggiunti nella fase RED passavano già perché il vecchio `select_model` aveva già il comportamento corretto a livello funzionale (il declasso scattava a 4.00 via `BUDGET_WARNING`). Il fix in GREEN ha però rivelato il bug del ramo irraggiungibile quando `BUDGET_DEGRADED` è stato abbassato a 4.00. Il processo TDD ha quindi correttamente identificato l'incoerenza strutturale del codice.

## Known Stubs

Nessuno — la funzione `get_month_spend_usd` legge dati reali da `api_usage`.

## Threat Flags

Nessun nuovo threat surface introdotto. T-04-06 e T-04-07 dal threat register del piano sono mitigati:
- T-04-06: `check_budget_or_raise` blocca non-emergency quando projected > BUDGET_BLOCKED ($4.80), confermato da test
- T-04-07: discrepanza soglia documentata vs comportamento reale eliminata — `BUDGET_DEGRADED = 4.00` corrisponde a ROADMAP SC4

## Self-Check: PASSED

- `coach/utils/budget.py`: FOUND
- `tests/test_budget.py`: FOUND
- Commit `19ca850`: FOUND in git log
- `BUDGET_DEGRADED = 4.00`: presente (2 occorrenze — costante + commento)
