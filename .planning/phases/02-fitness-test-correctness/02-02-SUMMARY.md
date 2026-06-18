---
phase: 02-fitness-test-correctness
plan: "02"
subsystem: scripts
tags:
  - physiology-zones
  - data-hygiene
  - cleanup
  - plausible-bounds
dependency_graph:
  requires:
    - coach/coaching/fitness_test_processor.py (PLAUSIBLE_BOUNDS)
    - coach/utils/supabase_client.py (get_supabase)
  provides:
    - scripts/cleanup_physiology_zones.py
  affects:
    - physiology_zones table (DELETE on --confirm)
tech_stack:
  added: []
  patterns:
    - load_dotenv before coach.* imports (lru_cache constraint)
    - argparse --confirm for destructive mode gating
    - per-row try/except with logger.exception for resilient bulk deletes
key_files:
  created:
    - scripts/cleanup_physiology_zones.py
  modified: []
decisions:
  - "PLAUSIBLE_BOUNDS imported from fitness_test_processor — not redefined (D-09)"
  - "Default dry run; destructive mode requires explicit --confirm flag (T-02-02-01)"
  - "Per-discipline delete counts (bike/run/swim) in both output modes"
  - "Per-row try/except — one failed delete does not abort remaining rows"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-05"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 02 Plan 02: Cleanup physiology_zones Summary

**One-liner:** Dry-run + confirmed DELETE of out-of-bounds `physiology_zones` rows using `PLAUSIBLE_BOUNDS` imported from `fitness_test_processor`.

## What Was Built

`scripts/cleanup_physiology_zones.py` — operational script for the destructive half of Phase 2 data hygiene.

**Dry run (default, no args):**
- Queries all `physiology_zones` rows
- For each row, checks the discipline-specific value (ftp_w for bike, threshold_pace_s_per_km for run, css_pace_s_per_100m for swim) against PLAUSIBLE_BOUNDS
- Rows with None values are skipped (only rows with actual values are evaluated)
- Prints each out-of-bounds row with discipline, id, value, range, method, and date
- Prints per-discipline count summary
- Makes zero DB mutations

**Confirmed delete (--confirm):**
- Same bounds check logic
- For each out-of-bounds row: logs via logger.info then executes DELETE by UUID
- Per-row try/except so one Supabase error doesn't abort remaining deletions
- Prints per-row DELETED lines and final count summary (bike/run/swim)

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Create scripts/cleanup_physiology_zones.py | 5ffdc77 | scripts/cleanup_physiology_zones.py |

## Acceptance Criteria — All Passed

All 17 acceptance criteria verified:
- Syntactically valid Python (ast.parse exits 0)
- `load_dotenv()` before first `from coach.` import
- `from coach.coaching.fitness_test_processor import PLAUSIBLE_BOUNDS` present
- No `PLAUSIBLE_BOUNDS = {` dict literal (bounds from import only)
- `--confirm` argparse flag (store_true)
- `DRY RUN` header string present
- `CONFIRM` header string present
- `physiology_zones` table referenced in `.delete()` call
- `.eq("id",` for per-row UUID targeting
- Per-discipline counts: `bike:`, `run:`, `swim:` in output
- No `sys.exit(1)` or `exit(1)`
- No `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` in string literals (T-02-02-02 mitigated)
- `if __name__ == "__main__": main()` present

## Deviations from Plan

None — plan executed exactly as written.

**Note (worktree setup):** The worktree was initialized from commit `7b1dcf4` instead of expected base `1eccebf`. Working tree was brought to correct state using `git checkout 1eccebf -- <files>` before execution. The worktree branch had zero prior commits so this was non-destructive. Tracked as an environment deviation, not a code deviation.

## Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-02-02-01 | mitigate | Default dry run; DELETE only on explicit `--confirm`; each delete targets specific UUID |
| T-02-02-02 | mitigate | No `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` in any string literal |
| T-02-02-SC | accept | No new packages installed |

## Known Stubs

None. Script is fully implemented — all paths (dry run, confirm, no-data case) produce correct output.

## Self-Check: PASSED

- [x] `scripts/cleanup_physiology_zones.py` exists: confirmed (223 lines, minimum 60 required)
- [x] Commit `5ffdc77` exists: `feat(02-02): create scripts/cleanup_physiology_zones.py`
- [x] All 17 acceptance criteria pass
- [x] Syntax valid: `python -c "import ast; ast.parse(...)"` exits 0
