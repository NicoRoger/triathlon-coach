---
phase: 03-deploy-pipeline-resilience
plan: "02"
subsystem: pipeline
tags: [ingest, modulation, deploy, github-actions, resilience]
dependency_graph:
  requires: []
  provides: [DEPLOY-04, PIPELINE-01]
  affects: [.github/workflows/ingest.yml]
tech_stack:
  added: []
  patterns: [github-actions-step-conditions, exit-code-propagation]
key_files:
  created: []
  modified:
    - .github/workflows/ingest.yml
decisions:
  - "D-06 applicato: rimosso if: always() da Apply-accepted-modulations step; defaults a success() implicito"
  - "Commento aggiornato nel YAML per evitare false positive nella verifica automatica"
  - "PIPELINE-01 live-log confirmation deferred a piano 03-04 / Phase 4"
metrics:
  duration_minutes: 8
  completed_date: "2026-06-07"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 03 Plan 02: Modulation Wiring + Exit-Code Vertical Slice — Summary

**One-liner:** Rimosso `if: always()` dal passo apply-accepted-modulations in ingest.yml (D-06), provate la transizione accepted->applied (DEPLOY-04) e la presenza del path exit-1 nel Garmin sync (PIPELINE-01).

---

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Rimuovi if: always() da Apply-accepted-modulations step (D-06) | `4bbd2e8` | `.github/workflows/ingest.yml` |
| 2 | Verifica DEPLOY-04 (accepted->applied) e PIPELINE-01 (exit 1) | *(verifica pura - nessun file modificato)* | - |

---

## Task 1 Detail: Rimozione if: always()

**Problema (RESEARCH.md Pitfall 2 / T-03-04):** Il passo "Apply accepted modulations (audit K1)" in `ingest.yml` aveva `if: always()` alla riga 98. Questo avrebbe applicato modulazioni accettate anche dopo un fallimento del Garmin sync, scrivendo su `planned_sessions` con dati stantii.

**Fix applicato:** Rimossa la riga `if: always()`. Il passo ora defaults a `if: success()` per semantica nativa GitHub Actions - gira solo se tutti i passi precedenti (incluso il Garmin sync con exit 1) hanno avuto successo.

**Invarianti preservati:**
- `continue-on-error: true` mantenuto (D-05: failure nella modulation non blocca ingest)
- `python -m coach.coaching.modulation --apply-accepted` mantenuto (D-04: step separato)
- YAML ancora valido (confermato con `yaml.safe_load`)

**Output YAML verificato:**
```
Apply accepted modulations (audit K1) | if: <default success>
```

---

## Task 2 Detail: Verifica DEPLOY-04 e PIPELINE-01

### DEPLOY-04 - accepted -> applied transition

**Test automatici:** 2 passed, 0 failed
```
pytest tests/test_audit_resilience.py::test_k1_accepted_modulation_gets_applied
pytest tests/test_audit_resilience.py::test_d2_full_apply_accepted
Result: 2 passed in 8.52s
```

**Source assertions (deterministic):**
- `coach/coaching/modulation.py` contiene `def apply_accepted_modulations` (riga 175)
- `coach/coaching/modulation.py` contiene il flag argparse `--apply-accepted` (riga 366)
- `.github/workflows/ingest.yml` contiene `python -m coach.coaching.modulation --apply-accepted`

### PIPELINE-01 - exit 1 su Garmin sync fallito

**Source assertion (code path present):**
- `ok=0` inizializzazione presente nel Garmin step
- `for i in 1 2 3` retry loop presente
- `if [ "$ok" -ne 1 ]; then ... exit 1; fi` presente come ultimo comando del loop

**Nota:** La conferma live (Actions log reale con fallimento propagato) e' demandata a piano 03-04 / Phase 4. Questo task ha come target "il code path exit-1 e' presente e intatto" - confermato.

---

## Deviations from Plan

**1. [Rule 1 - Bug] Commento YAML conteneva la stringa if: always() letteralmente**
- **Found during:** Task 1 verification
- **Issue:** Il commento D-06 aggiunto inizialmente conteneva `if: always()` come stringa esplicativa. La verifica automatica (`assert 'if: always()' not in blk`) falliva trovando quella stringa nel commento.
- **Fix:** Riformulato il commento: "nessun if: su questo step" invece di citare la stringa rimossa letteralmente.
- **Files modified:** `.github/workflows/ingest.yml`
- **Commit:** Stesso `4bbd2e8`

---

## Known Stubs

Nessun stub presente. Il passo `--apply-accepted` e' completamente cablato: seleziona righe `status='accepted'`, chiama `apply_modulation()`, transisce a `status='applied'`.

---

## Threat Surface Scan

Nessuna nuova superficie di attacco introdotta. Le modifiche riducono la superficie:
- Rimuovendo la condizione `always`, si elimina il path in cui `planned_sessions` veniva scritto su dati stantii (T-03-04: Tampering - risolto).
- T-03-05 (DoS per errore modulation) rimane accepted tramite `continue-on-error: true`.
- T-03-06 (silent-green su Garmin fallito) rimane mitigato dal code path `exit 1` confermato intatto (PIPELINE-01).

---

## PIPELINE-01 Live-Log Confirmation (Deferred)

La verifica comportamentale completa di PIPELINE-01 - ossia un'esecuzione GitHub Actions reale che fallisce dopo 3 tentativi e mostra il run come rosso nel log - e' esplicitamente demandata al piano **03-04 / Phase 4** (verifica live). Il code path e' presente e corretto; la prova end-to-end richiede un ambiente CI live.

---

## Self-Check: PASSED

- [x] File `.github/workflows/ingest.yml` modificato nel worktree: CONFERMATO
- [x] Commit `4bbd2e8` esiste: CONFERMATO
- [x] YAML valido post-modifica: CONFERMATO (`yaml.safe_load` senza errori)
- [x] Verifica automatica `ingest-step-ok`: CONFERMATO
- [x] pytest 2/2 passed: CONFERMATO
- [x] Source assertions DEPLOY-04 + PIPELINE-01: TUTTE PASSATE
