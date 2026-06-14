---
phase: "04"
plan: "02"
subsystem: live-behavior-verification
tags: [verify-04, verify-05, deploy-04, gemini-routing, modulation, session-analysis]
dependency_graph:
  requires: [04-01]
  provides: [VERIFY-04-routing-test, VERIFY-05-accepted-applied-test, D-03-wiring-confirmed]
  affects: [tests/test_live_behavior.py, .github/workflows/ingest.yml]
tech_stack:
  added: []
  patterns: [fake-supabase-pattern, purpose-routing-assert, accepted-applied-flow]
key_files:
  created:
    - tests/test_live_behavior.py
  modified: []
decisions:
  - "ingest.yml già wired correttamente (D-03 soddisfatto in Phase 3): nessuna modifica al workflow"
  - "Test 2 (guard E7) usa fake LLM injected via sys.modules per evitare chiamate di rete"
  - "Test 3 (VERIFY-05) usa _AcceptedModFakeQuery con update in-place per simulare la transizione DB"
metrics:
  duration: "~10 min"
  completed: "2026-06-07"
  tasks_completed: 1
  tasks_total: 2
  files_changed: 1
---

# Phase 04 Plan 02: Live Behavior Verification — Routing Gemini + Accepted→Applied Summary

**One-liner:** Test pytest che bloccano regressioni su routing `session_analysis → gemini-2.5-flash` (VERIFY-04) e flusso `accepted → applied → planned_sessions` (VERIFY-05/DEPLOY-04); ingest.yml confermato già wired correttamente (D-03).

---

## Tasks Completed

### Task 1: Verifica wiring ingest.yml e blocca con test il routing Gemini + flusso accepted→applied

**Status:** DONE — commit `469b2a9`

**Azioni eseguite:**

1. **Verifica ingest.yml:** confermato che entrambi gli step esistono e sono correttamente ordinati:
   - `Post-session analysis` (riga 73-75): `if: success()`, eseguito dopo `Compute daily metrics`, invoca `python -m coach.coaching.post_session_analysis --recent --days ...`
   - `Apply accepted modulations (audit K1)` (riga 94-100): `continue-on-error: true`, senza `if: always()`, invoca `python -m coach.coaching.modulation --apply-accepted`
   - **Nota:** il `if: always()` alla riga 103 appartiene allo step `ETL health check`, non ad apply-accepted. D-03 già soddisfatto in Phase 3 — nessuna modifica necessaria.

2. **Creato `tests/test_live_behavior.py`** con 3 test:
   - **Test 1** (`test_verify04_session_analysis_routes_to_gemini`): ispeziona `PURPOSE_ROUTING['session_analysis'] == 'gemini'` e `GeminiClient.MODEL == 'gemini-2.5-flash'` — zero chiamate di rete.
   - **Test 2** (`test_verify04_empty_llm_text_skips_insert`): guard E7 — fake client ritorna `{"text": ""}` → `analyze_session()` ritorna `None` e zero insert su `session_analyses`.
   - **Test 3** (`test_verify05_accepted_modulation_applies_and_updates_planned_sessions`): riga `plan_modulations` con `status='accepted'` → `apply_accepted_modulations()` → `summary["applied"] == 1`, `mod["status"] == "applied"`, upsert su `planned_sessions` con i valori corretti.

**Verifica:**
```
PYTHONPATH=. python -m pytest tests/test_live_behavior.py -x -q
3 passed in 1.55s
```

---

## Task 2: Scenario live tap ✅ (CHECKPOINT — in attesa)

**Status:** CHECKPOINT — in attesa di verifica umana

Il Task 2 è un checkpoint `human-verify` che richiede l'atleta per eseguire lo scenario live end-to-end su Telegram + Supabase. Non contiene modifiche al codice.

**Dettagli checkpoint:** vedere sezione "Checkpoint" sotto.

---

## Deviations from Plan

**Nessuna deviazione** — il plan è stato eseguito esattamente come scritto.

**D-03 già soddisfatto:** ingest.yml era già wired correttamente da Phase 3. Nessuna modifica al file, come anticipato nel piano.

---

## Known Stubs

Nessuno — i test non usano dati hardcoded che fluiscono a UI/rendering.

---

## Threat Surface Scan

Nessuna nuova superficie di sicurezza introdotta. I test sono read-only (nessuna scrittura su DB reale).

---

## Self-Check: PASSED

- [x] `tests/test_live_behavior.py` esiste: FOUND
- [x] Commit `469b2a9` esiste: FOUND
- [x] `PYTHONPATH=. python -m pytest tests/test_live_behavior.py -q` → 3 passed
- [x] ingest.yml contiene `python -m coach.coaching.post_session_analysis --recent`
- [x] ingest.yml contiene `python -m coach.coaching.modulation --apply-accepted`
- [x] step apply-accepted NON ha `if: always()` (ce l'ha solo ETL health check alla riga 103)
