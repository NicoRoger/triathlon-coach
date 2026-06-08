---
phase: 05-workout-prescription-quality
plan: "01"
subsystem: database
tags: [migration, active_constraints, progression_plan, workout-prescription, WORKOUT-03, WORKOUT-04]
dependency_graph:
  requires: []
  provides:
    - migrations/2026-06-07-workout-prescription-quality.sql
    - tests/test_active_constraints.py
    - scripts/verify_prescription_quality.py
  affects:
    - workers/mcp-server/src/index.ts (Plan 02 reads active_constraints)
    - mesocycles table (progression_plan column added)
tech_stack:
  added: []
  patterns:
    - CREATE TABLE IF NOT EXISTS (idempotent DDL)
    - WHERE NOT EXISTS seed (no UNIQUE key on active_constraints)
    - pytest.skip for live DB tests without SUPABASE_URL
    - load_dotenv() before coach.* imports (lru_cache constraint)
key_files:
  created:
    - migrations/2026-06-07-workout-prescription-quality.sql
    - tests/test_active_constraints.py
    - scripts/verify_prescription_quality.py
  modified: []
decisions:
  - "Used WHERE NOT EXISTS for seed idempotency (not ON CONFLICT DO NOTHING) because active_constraints has no natural UNIQUE key — matches PATTERNS.md Pitfall 5"
  - "ENABLE ROW LEVEL SECURITY on active_constraints follows single-user service_role pattern (all other tables); no explicit policies needed"
  - "5 source-assertion tests + 1 live skip test — exceeds plan minimum of 3 to improve coverage"
metrics:
  duration_s: 227
  completed_date: "2026-06-08"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 0
---

# Phase 05 Plan 01: DB Migration & Test Foundation Summary

Wave 0 foundation for Phase 5 — active_constraints table + mesocycles.progression_plan column + WORKOUT-03 test coverage + verify scaffold.

## One-liner

Migration SQL creates `active_constraints` table (medical constraints dynamic DB) + `progression_plan` JSONB column on `mesocycles`, seeding 2 active injury constraints (spalla dx/swim/HIGH, fascite sx/run/MEDIUM) with idempotent WHERE NOT EXISTS pattern.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migration SQL active_constraints + progression_plan + seed | f0fc051 | migrations/2026-06-07-workout-prescription-quality.sql |
| 2 | Test stub WORKOUT-03 | 01a2f2b | tests/test_active_constraints.py |
| 3 | Scaffold verify_prescription_quality.py | c245168 | scripts/verify_prescription_quality.py |

## Artifacts Produced

### migrations/2026-06-07-workout-prescription-quality.sql

- `CREATE TABLE IF NOT EXISTS active_constraints` with columns: `id UUID PK`, `type TEXT CHECK('injury','medical','tactical')`, `discipline TEXT CHECK('swim','bike','run','all')`, `description TEXT`, `severity TEXT CHECK('high','medium','low')`, `created_at TIMESTAMPTZ`, `resolved_at TIMESTAMPTZ` (nullable)
- `ALTER TABLE active_constraints ENABLE ROW LEVEL SECURITY` (service_role only, V4 ASVS L1)
- `ALTER TABLE mesocycles ADD COLUMN IF NOT EXISTS progression_plan JSONB`
- 2 seed rows D-13 with `WHERE NOT EXISTS` guard (no UNIQUE key on table — ON CONFLICT would be a no-op)

### tests/test_active_constraints.py

6 tests (5 source assertions + 1 live skip):
- `test_migration_file_present` — active_constraints, progression_plan, WHERE NOT EXISTS
- `test_migration_idempotent` — CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS
- `test_migration_seed_descriptions` — borsite + tendinopatia CLB, fascite plantare sinistra
- `test_migration_check_constraints` — type/discipline CHECK values
- `test_migration_rls_enabled` — ENABLE ROW LEVEL SECURITY
- `test_active_constraints_seed_has_two_rows` — LIVE (skip if SUPABASE_URL absent)

Test result: `177 passed, 1 skipped` (full suite).

### scripts/verify_prescription_quality.py

Read-only Phase 5 gate scaffold with 4 sections:
- `_verify_active_constraints(sb)` — lists active constraints, warns if < 2
- `_verify_physiology_zones_age(sb)` — checks freshness per discipline, flags >42 days
- `_verify_mesocycles_progression_plan(sb)` — checks active mesocycle for progression_plan
- `_print_manual_checklist()` — WORKOUT-01/02/04/05 manual verification items

Each `_verify_*` function wrapped in try/except for zero-crash on empty DB.

## Verification Results

```
pytest tests/test_active_constraints.py -v
5 passed, 1 skipped in 0.32s

pytest tests/ -x -q
177 passed, 1 skipped in 5.78s
```

## Success Criteria

- [x] Migration idempotente esiste con active_constraints + progression_plan + 2 seed
- [x] Test WORKOUT-03 verde/skip senza errori di collezione
- [x] Script verify scaffold sintatticamente valido con tutte le sezioni

## Must-Have Truths Verified

- [x] tests/test_active_constraints.py passa verde (source assertions)
- [x] Migration è idempotente (IF NOT EXISTS + WHERE NOT EXISTS)
- [x] La migration contiene CREATE TABLE IF NOT EXISTS active_constraints
- [x] La migration contiene ADD COLUMN IF NOT EXISTS progression_plan JSONB
- [x] 2 vincoli seed D-13 presenti (borsite + tendinopatia CLB, fascite plantare sinistra)

## Deviations from Plan

None — plan executed exactly as written. The only minor addition was writing 5 source-assertion tests instead of the minimum 3 (added test_migration_seed_descriptions and test_migration_check_constraints for better coverage).

## Known Stubs

None. The verify_prescription_quality.py is an intentional scaffold — it is designed as a Phase 5 gate script to be run manually. All functions are implemented. No hardcoded empty values that flow to UI rendering.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes introduced. The active_constraints table has RLS enabled (T-05-01 mitigated). The WHERE NOT EXISTS pattern prevents duplicate seed insertion (T-05-02 mitigated).

## Self-Check: PASSED

- [x] migrations/2026-06-07-workout-prescription-quality.sql: FOUND
- [x] tests/test_active_constraints.py: FOUND
- [x] scripts/verify_prescription_quality.py: FOUND
- [x] Commit f0fc051: FOUND (Task 1)
- [x] Commit 01a2f2b: FOUND (Task 2)
- [x] Commit c245168: FOUND (Task 3)
