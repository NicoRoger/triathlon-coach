---
phase: 06-physiological-adaptation-intelligence
plan: "01"
subsystem: analytics-db
tags: [migration, tdd, wave-0, adaptation-intelligence, beliefs]
dependency_graph:
  requires: []
  provides:
    - migrations/2026-06-08-physiological-adaptation.sql
    - tests/test_fatigue_classification.py
    - tests/test_physio_adaptation.py
  affects:
    - session_analyses (new columns: fatigue_type, fatigue_confidence, sport)
    - beliefs (new row: endurance_failure_type)
    - plan 02 (classify_fatigue_type implementation target)
    - plan 03 (propose_session.md skill update target)
    - plan 04 (update_beliefs_from_session_patterns implementation target)
tech_stack:
  added: []
  patterns:
    - ALTER TABLE IF NOT EXISTS idempotent migration
    - INSERT ON CONFLICT (belief_key) DO NOTHING for belief seed
    - Wave 0 RED test scaffold (TDD)
    - Static file assertion tests (read_text + assert substring)
key_files:
  created:
    - migrations/2026-06-08-physiological-adaptation.sql
    - tests/test_fatigue_classification.py
    - tests/test_physio_adaptation.py
  modified: []
decisions:
  - "sport TEXT column added to session_analyses (Open Question 2 resolution): avoids JOIN with activities in Worker TypeScript getLastFatigueBySport (Pitfall 2)"
  - "evidence_note mapped to source_metadata JSONB (not SQL column): correct beliefs schema from 2026-05-14-cognitive-mvp.sql (Pitfall 3)"
  - "ON CONFLICT (belief_key) DO NOTHING: idempotent seed guaranteed at DB level (Pitfall 5)"
  - "test_skill_active_beliefs_step is intentionally RED Wave 0: plan 03 will add active_beliefs to propose_session.md"
metrics:
  duration: "4min"
  completed: "2026-06-08T20:48:00Z"
  tasks_completed: 2
  files_changed: 3
requirements: [ADAPT-01, ADAPT-02, ADAPT-03]
---

# Phase 06 Plan 01: DB Foundation + Wave 0 RED Test Scaffold Summary

**One-liner:** DB migration adds fatigue classification columns to session_analyses + seeds endurance_failure_type belief; Wave 0 RED tests define the contracts for plans 02-04.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migration DB — colonne session_analyses + seed belief endurance_failure_type | 2948aa2 | migrations/2026-06-08-physiological-adaptation.sql |
| 2 | Test scaffold RED — test_fatigue_classification.py + test_physio_adaptation.py | 8680ac8 | tests/test_fatigue_classification.py, tests/test_physio_adaptation.py |

## What Was Built

### Task 1: Migration SQL (`migrations/2026-06-08-physiological-adaptation.sql`)

Additive idempotent migration covering two concerns:

**ADAPT-01 — ALTER TABLE session_analyses** (3 new columns):
- `fatigue_type TEXT CHECK (IN 'muscular', 'cardiovascular', 'mixed', 'insufficient_data')` — T-06-01 mitigation
- `fatigue_confidence FLOAT CHECK (0-1 or NULL)` — T-06-01 mitigation
- `sport TEXT` — resolves Open Question 2 / Pitfall 2 by denormalizing sport onto session_analyses, enabling `getLastFatigueBySport()` in Worker TypeScript without a JOIN

**ADAPT-02 — INSERT INTO beliefs** (endurance_failure_type seed):
- `belief_key = 'endurance_failure_type'`, `confidence = 0.75`, `evidence_n = 8`, `status = 'validated_belief'`
- `source = 'manual_seed'`, `source_metadata` carries `evidence_note` as JSONB key (not SQL column — Pitfall 3 resolved)
- `ON CONFLICT (belief_key) DO NOTHING` — idempotent at DB level (T-06-02 / Pitfall 5)

### Task 2: Test Scaffold Wave 0 (RED)

**`tests/test_fatigue_classification.py`** (7 tests, all RED Wave 0):
- 5 unit tests for `classify_fatigue_type()` (ADAPT-01): cardiovascular signal, muscular signal, RPE-only fallback, short session None, low-RPE no-splits None
- 2 unit tests for `update_beliefs_from_session_patterns()` (ADAPT-03): n<3 skips belief creation, session_type=None skips belief creation (Pitfall 4)
- Contains `from coach.analytics.readiness import classify_fatigue_type` → ImportError (function not yet implemented — plan 02 target)
- Contains `make_splits_run()` helper factory for synthetic splits

**`tests/test_physio_adaptation.py`** (3 tests, 2 GREEN + 1 RED Wave 0):
- `test_migration_session_analyses_columns` — GREEN: migration has fatigue_type, fatigue_confidence, IF NOT EXISTS
- `test_migration_belief_seed_idempotent` — GREEN: migration has ON CONFLICT (belief_key) DO NOTHING + endurance_failure_type
- `test_skill_active_beliefs_step` — RED Wave 0: propose_session.md not yet updated (plan 03 target)

## Verification Results

```
python -m pytest tests/test_physio_adaptation.py::test_migration_session_analyses_columns tests/test_physio_adaptation.py::test_migration_belief_seed_idempotent -x -q
=> 2 passed (GREEN)

python -m pytest tests/test_fatigue_classification.py -q
=> ImportError: cannot import name 'classify_fatigue_type' (RED — expected Wave 0)

python -m pytest tests/test_physio_adaptation.py -q
=> 2 passed, 1 failed (test_skill_active_beliefs_step RED — expected Wave 0)
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Design Notes (not deviations)

The `sport TEXT` column was explicitly planned in the PLAN.md (line 97: "serve a getLastFatigueBySport nel plan 03 per evitare il JOIN problematico — Pitfall 2") and is reflected in the migration. This resolves Open Question 2 from RESEARCH.md at the schema level.

## Known Stubs

None. The migration is complete and non-stub. The test files are intentionally RED (Wave 0 scaffold) — they are not stubs, they define contracts for plans 02/03/04.

## Threat Flags

No new security surface introduced beyond what was planned:
- T-06-01 mitigated: CHECK constraints on fatigue_type values and fatigue_confidence range
- T-06-02 mitigated: ON CONFLICT (belief_key) DO NOTHING ensures idempotent seed
- T-06-SC: No new packages installed

## Self-Check: PASSED

- [x] `migrations/2026-06-08-physiological-adaptation.sql` exists
- [x] `tests/test_fatigue_classification.py` exists
- [x] `tests/test_physio_adaptation.py` exists
- [x] Commit 2948aa2 exists (Task 1)
- [x] Commit 8680ac8 exists (Task 2)
- [x] 2 static tests GREEN, unit tests RED (expected)
