---
phase: 05-workout-prescription-quality
plan: "03"
subsystem: skill-prompts
tags: [skill-prompts, propose_session, generate_mesocycle, fitness_test, gate-fisiologico, active_constraints, progression_plan, structured-jsonb, drill-tecnici, WORKOUT-01, WORKOUT-02, WORKOUT-03, WORKOUT-04, WORKOUT-05]
dependency_graph:
  requires:
    - 05-01 (active_constraints table + progression_plan column in DB)
    - 05-02 (MCP Worker: age_days, active_constraints, update_constraint, current_progression_step)
  provides:
    - skills/propose_session.md (gate fisiologico + vincoli dinamici + drill + race-pace + contesto mesociclo)
    - skills/generate_mesocycle.md (gate fisiologico + active_constraints + progression_plan + structured JSONB)
    - skills/fitness_test.md (Step 0 FTP age check data-driven)
  affects:
    - Coach AI prescriptions (Claude.ai Opus via MCP): ogni prescrizione usa ora physiology_zones + active_constraints + progression_step
    - 05-04 (phase gate): verifica live output LLM con i nuovi prompt
tech_stack:
  added: []
  patterns:
    - GATE FISIOLOGICO obbligatorio Step 0 in propose_session + generate_mesocycle
    - active_constraints da get_weekly_context (non da CLAUDE.md statico)
    - structured flat steps list JSONB per ogni sessione commit_plan_change
    - progression_plan JSONB in commit_mesocycle (week1/week2/week3 per tipo qualita)
    - perceived effort contestualizzazione se >=2 fattori avversi (caldo/TSB/sonno)
    - age_days check data-driven per FTP (non testo statico "6 settimane")
key_files:
  created: []
  modified:
    - skills/propose_session.md
    - skills/generate_mesocycle.md
    - skills/fitness_test.md
decisions:
  - "propose_session Step 0 usa bold+caps GATE FISIOLOGICO per segnalare esecuzione obbligatoria — pattern coerente con 'Multi-race awareness' esistente in generate_mesocycle"
  - "Drill tecnici come sezione autonoma 'Drill tecnici Nicolo' invece di inline — consente al coach di selezionare 1-2 drill rilevanti per fase senza ripetere la logica nei template"
  - "perceived effort triggered da >=2 fattori avversi (non 1): bilanciamento tra sensibilita alle condizioni e frequenza di trigger"
  - "generate_mesocycle Procedura usa Step 0 prima dei passi numerati 1-11: visivamente distinto come prerequisito assoluto"
  - "fitness_test Step 0 inserito prima di 'Quando proporre': forza check data-driven prima di qualsiasi valutazione qualitativa delle condizioni"
metrics:
  duration_minutes: ~8
  completed_date: "2026-06-08"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 3
---

# Phase 05 Plan 03: Skill Prompts Upgrade Summary

**One-liner:** Riscrittura di 3 skill prompts con gate fisiologico obbligatorio, vincoli medici dinamici da DB, drill tecnici per Nicolo, template prescrizioni strutturate warmup/main/cooldown, e check FTP age data-driven.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | propose_session.md riscrittura | 8d1b637 | skills/propose_session.md |
| 2 | generate_mesocycle.md estensione | 81d83f3 | skills/generate_mesocycle.md |
| 3 | fitness_test.md estensione | f21e347 | skills/fitness_test.md |

## What Was Built

### Task 1: propose_session.md

Riscrittura completa della `## Procedura` in `## Procedura obbligatoria (NON saltare nessuno step)` con 5 step numerati:

- **Step 0 GATE FISIOLOGICO**: `get_physiology_zones(discipline)` obbligatorio prima di ogni prescrizione; no prescrizione se zones vuoto; segnala se `age_days > 42`; tutti i target numerici da physiology_zones.
- **Step 1**: `get_planned_session(today)` — sessione pianificata.
- **Step 2**: `get_weekly_context()` — estrae `active_constraints` (fonte di verita DB, non CLAUDE.md), `current_progression_step`, `daily_metrics` (TSB, HRV), `daily_wellness` (sleep, temperatura).
- **Step 3**: `get_activity_history(sport, days=14)` — riduzione volume se RPE medio >= 8.0 o fatica neuromuscolare.
- **Step 4**: Readiness a 3 livelli + contestualizzazione zone: perceived effort se >=2 fattori avversi (T>25C / TSB<-10 / sleep<65).
- **Step 5**: Race-pace via `race_prediction` + `get_race_context` per sessioni Lavarone-specifiche.

Nuova sezione `## Drill tecnici Nicolo` con drill per nuoto (pull buoy, DPS, fingertip drag), bici (big gear, cadenza, climbing), corsa (strides, marcia tibiali, cadenza).

Template output rinnovato con `Contesto mesociclo` (settimana N/3, TSS accumulato/target, ruolo sessione), `Vincoli attivi:`, `Warm-up / Drill block / Main set / Cool-down`, istruzione commit `structured` JSONB con esempio canonical.

### Task 2: generate_mesocycle.md

- **Step 0 GATE FISIOLOGICO** inserito prima dei passi procedurali per tutte le discipline coinvolte.
- **Step 7** aggiornato: "gia fatto in Step 0".
- **Step 8** esteso: legge `active_constraints` (SOSTITUISCONO CLAUDE.md) e `current_progression_step` con regola RPE <= 7.5 per avanzamento e fallback null (progressione conservativa).
- **Commit in DB** esteso: `commit_mesocycle` include `progression_plan` JSONB; `commit_plan_change` richiede `structured` flat steps list.
- Nota espansione template aggiunta.
- `## Cosa NON fare` esteso con divieto vincoli statici e obbligo progression_plan + structured.

### Task 3: fitness_test.md

Nuova sezione `## Step 0 — Check FTP age (SEMPRE per sessioni bici)` inserita prima di `## Quando proporre un test`:
1. Chiama `get_physiology_zones('bike')`
2. Leggi `zones[0].age_days`
3. Se `age_days > 42` o zones vuoto: propone test con data ottimale calcolata e TSB target >0
4. Condizione data-driven: cita il valore numerico esatto dal DB, non il testo statico "6 settimane".

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

### Automated source assertions

```
propose_session.md:   OK (all 11 substrings present)
generate_mesocycle.md: OK (all 8 substrings present)
fitness_test.md:       OK (all 5 substrings present)
```

### pytest suite

```
172 passed in 4.72s — no regressions (Phase 5 Wave 3 modifies only markdown)
```

### Verifica live (rimandato a Plan 04)

L'output LLM effettivo (warmup/main/cooldown, zone numeriche, vincoli da DB, drill, contesto mesociclo) e demandato al phase gate manuale (Plan 04 — verifica live WORKOUT-01..05).

## Known Stubs

None — i 3 file sono skill prompts markdown puramente testuali che dirigono Claude.ai Opus. Non contengono dati hardcoded o placeholder che fluiscono all'UI. La qualita dell'output LLM e verificata nel phase gate Plan 04.

## Threat Flags

None — i file modificati sono markdown di istruzioni caricati come system prompt per Claude.ai. Il trust boundary `skill prompt -> coach AI` e accettato (operatore committa il testo). Nessuna nuova superficie di rete, path di auth, o accesso a file introdotto.

## Self-Check: PASSED

- `skills/propose_session.md` — file exists, commit 8d1b637 confirmed
- `skills/generate_mesocycle.md` — file exists, commit 81d83f3 confirmed
- `skills/fitness_test.md` — file exists, commit f21e347 confirmed
- pytest 172 passed — no regressions
