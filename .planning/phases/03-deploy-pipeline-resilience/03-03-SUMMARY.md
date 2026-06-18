---
phase: 03-deploy-pipeline-resilience
plan: "03"
subsystem: pipeline
tags: [briefing, watchdog, dr-snapshot, resilience, test, idempotency]
dependency_graph:
  requires: []
  provides: [PIPELINE-02, PIPELINE-03, PIPELINE-04]
  affects: [tests/test_audit_resilience.py]
tech_stack:
  added: []
  patterns: [fake-supabase-stub, chained-builder-tracing, tdd-gap-closure]
key_files:
  created: []
  modified:
    - tests/test_audit_resilience.py
decisions:
  - "Wave 0 PIPELINE-04 gap chiuso: aggiunto test esplicito per _brief_already_sent_today invece di affidarsi solo alla copertura indiretta"
  - "Fake client dedicato (_IdempotencyFakeQuery/_IdempotencyFakeSupabase) per tracciare gli argomenti .eq() senza estendere _FakeQuery generale"
  - "Tre funzioni di test separate (True-branch, False-branch, filtro-purpose) per massima leggibilità del failure message"
  - "Live-run confirmation per L3/L4/PIPELINE-04 demandata a Phase 4 (scheduled Actions runs)"
metrics:
  duration_minutes: 15
  completed_date: "2026-06-07"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 03 Plan 03: Pipeline Guards Verification & PIPELINE-04 Test Gap Closure — Summary

**One-liner:** Chiuso il gap di copertura Wave 0 PIPELINE-04 con 3 unit test espliciti per `_brief_already_sent_today()` (True/False/filtro-purpose) via fake Supabase in-process; confermati verde L4 watchdog (PIPELINE-02) e L3 DR-snapshot abort (PIPELINE-03).

---

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add explicit test_pipeline04_brief_idempotency unit test (Wave 0 gap) | `850eb3e` | `tests/test_audit_resilience.py` |
| 2 | Verify L4 watchdog, L3 DR abort, and PIPELINE-04 idempotency observably | *(verifica pura — nessun file modificato)* | - |

---

## Task 1 Detail: Test espliciti per PIPELINE-04

**Gap identificato (VALIDATION.md Wave 0):** `_brief_already_sent_today()` era coperta solo indirettamente — nessun test unitario che verificasse i due branch (True/False) e il filtro sul purpose corretto.

**Soluzione adottata:** Aggiunta la classe `_IdempotencyFakeQuery` (traccia argomenti di `.eq()`) e `_IdempotencyFakeSupabase` (routing verso la query fake), seguite da tre funzioni di test:

| Funzione | Cosa verifica |
|----------|---------------|
| `test_pipeline04_brief_idempotency_skips_when_already_sent` | Ritorna `True` con riga `morning_brief` presente |
| `test_pipeline04_brief_idempotency_sends_when_none` | Ritorna `False` con lista vuota |
| `test_pipeline04_brief_idempotency_filters_on_morning_brief_purpose` | Verifica che `.eq("purpose", "morning_brief")` sia chiamato |

**Pattern usato:** Fake in-process, nessuna chiamata di rete. Segue lo stile di `test_i4_record_health_does_not_raise_on_db_error` e `test_l4_watchdog_alerts_missing_component` del medesimo file.

**Risultato test:**
```
pytest tests/test_audit_resilience.py -k "pipeline04_brief_idempotency" -x -q
3 passed, 55 deselected in 2.77s
```

---

## Task 2 Detail: Verifica guard L3/L4/PIPELINE-04

### PIPELINE-02 — Watchdog L4: missing-component detection

**Test automatici:** 2 passed, 0 failed
```
pytest tests/test_audit_resilience.py::test_l4_watchdog_alerts_missing_component
       tests/test_audit_resilience.py::test_l4_watchdog_stale_component -x -q
2 passed in 2.64s
```

**Source assertion:** `scripts/watchdog.py` `compute_alerts()` itera `THRESHOLDS_HOURS.items()` (riga 34), alertando su componenti attesi ma mancanti, non solo su righe stantie (fix L4 confermato intatto).

### PIPELINE-03 — DR Snapshot L3: empty-table abort

**Test automatici:** 1 passed, 0 failed
```
pytest tests/test_audit_resilience.py::test_l3_empty_snapshot_aborts -x -q
1 passed in 2.64s
```

**Source assertion:** `scripts/dr_snapshot.py` definisce `EmptySnapshotError` (riga 38), `assert_snapshot_sane` (riga 42), e la chiama alla riga 84 prima del commit del backup (fix L3 confermato intatto).

### PIPELINE-04 — Brief idempotency: guard in main()

**Source assertion:** `coach/planning/briefing.py` `main()` chiama `_brief_already_sent_today(sb)` alla riga 711 e ritorna anticipatamente quando True (FORCE_SEND override a riga 708 rispettato).

**Test automatici:** 3 passed (vedi Task 1)

### Run combinato finale

```
pytest tests/test_audit_resilience.py::test_l4_watchdog_alerts_missing_component
       tests/test_audit_resilience.py::test_l4_watchdog_stale_component
       tests/test_audit_resilience.py::test_l3_empty_snapshot_aborts -x -q
3 passed in 2.91s
```

---

## Live-Run Confirmation (Deferred to Phase 4)

Le verifiche comportamentali live per i tre guard sono esplicitamente demandate alle prossime esecuzioni degli Actions schedulati (Phase 4 / monitoring):

| Guard | Conferma live attesa |
|-------|---------------------|
| L4 Watchdog missing-component | Primo run dopo che un componente va silent-dead → alert Telegram |
| L3 DR Snapshot empty-table abort | Next DR snapshot run con tabella critica vuota → `EmptySnapshotError` in log Actions |
| PIPELINE-04 brief idempotency | Doppio trigger mattutino → solo un brief recapitato, secondo skippato nel log |

Il target di questo piano era "fix presenti e provati unit-test" — confermato.

---

## Deviations from Plan

Nessuna. Il piano è stato eseguito esattamente come scritto:
- Task 1: 3 test aggiunti (TDD RED immediato verde perché funzione già implementata)
- Task 2: verifica pura senza modifiche ai sorgenti di produzione

---

## Known Stubs

Nessun stub. I tre guard (`compute_alerts`, `assert_snapshot_sane`, `_brief_already_sent_today`) sono completamente implementati e cablati nei rispettivi entry point (`main()`).

---

## Threat Surface Scan

Nessuna nuova superficie di attacco introdotta. Solo `tests/test_audit_resilience.py` modificato (file di test, non deployment).

I threat registrati nel piano sono tutti in stato `mitigate` confermato:
- T-03-07 (Tampering DR backup): `assert_snapshot_sane` presente e chiamato — confermato
- T-03-08 (Repudiation componente silenzioso): `compute_alerts` itera `THRESHOLDS_HOURS` — confermato
- T-03-09 (DoS duplicate brief): `_brief_already_sent_today` in `main()` con test espliciti — confermato

---

## Self-Check: PASSED

- [x] File `tests/test_audit_resilience.py` modificato: CONFERMATO (99 righe aggiunte)
- [x] Commit `850eb3e` esiste: CONFERMATO
- [x] 3 nuovi test PIPELINE-04 passano: CONFERMATO (3 passed in 2.77s)
- [x] 3 test L3/L4 esistenti passano: CONFERMATO (3 passed in 2.91s)
- [x] Source assertion watchdog THRESHOLDS_HOURS: CONFERMATO (riga 34)
- [x] Source assertion dr_snapshot EmptySnapshotError + assert_snapshot_sane + chiamata riga 84: CONFERMATO
- [x] Source assertion briefing _brief_already_sent_today in main() riga 711: CONFERMATO
