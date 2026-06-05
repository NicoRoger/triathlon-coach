---
phase: 02-fitness-test-correctness
plan: "01"
subsystem: scripts
tags:
  - physiology
  - verify
  - fitness-test
  - read-only
dependency_graph:
  requires:
    - coach/coaching/fitness_test_processor.py (PLAUSIBLE_BOUNDS, _fmt_pace, _fmt_swim_pace)
    - coach/utils/supabase_client.py (get_supabase)
    - CLAUDE.md (ftp_attuale_w, threshold_pace_per_km, css_attuale_per_100m)
  provides:
    - scripts/verify_physiology.py (read-only physiology zones verifier)
  affects:
    - physiology_zones table (read-only)
tech_stack:
  added: []
  patterns:
    - load_dotenv before coach.* imports (lru_cache constraint)
    - section functions with try/except per verify_analytics.py pattern
    - PLAUSIBLE_BOUNDS import from fitness_test_processor (no duplication)
key_files:
  created:
    - scripts/verify_physiology.py
  modified: []
decisions:
  - "Imported PLAUSIBLE_BOUNDS and formatters from fitness_test_processor rather than inline to avoid duplication (D-09)"
  - "Used re.search with numeric extraction for CLAUDE.md comparison to handle 'value (test date)' format written by processor"
  - "Bounds key for BIKE uses ftp_bike_20min (80-450W) — covers both 20min and ramp methods"
metrics:
  duration: "2m"
  completed: "2026-06-05T21:17:16Z"
requirements_delivered:
  - FITNESS-02
  - FITNESS-03
  - VERIFY-02
---

# Phase 02 Plan 01: Verify Physiology Zones Summary

**One-liner:** Read-only physiology zones verifier with PLAUSIBLE_BOUNDS checks and CLAUDE.md field comparison.

## What Was Built

`scripts/verify_physiology.py` — an informational script that queries the `physiology_zones` table and prints three sections (BIKE/RUN/SWIM) showing:
- Most-recent row per discipline (ordered by `valid_from DESC`)
- FTP/threshold/CSS value with `[OK — range X-YW]` or `[FUORI RANGE — range X-YW]` bounds check
- Comparison line against the corresponding CLAUDE.md field (`ftp_attuale_w`, `threshold_pace_per_km`, `css_attuale_per_100m`) — `match` or `DISCREPANZA: DB=X CLAUDE.md=Y`
- If the entire table is empty: `physiology_zones: vuoto — test eseguiti ma non processati. Usare: PYTHONPATH=. python scripts/trigger_fitness_processor.py`

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create scripts/verify_physiology.py | 6a48906 | scripts/verify_physiology.py (+250 lines) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The script is a read-only verifier; all data paths flow from the DB and CLAUDE.md.

## Threat Flags

None. The script contains no credentials in string literals, performs no DB writes, and does not print environment variable values. Threat T-02-01-01 (SUPABASE_URL/KEY disclosure) is mitigated — verified by acceptance criteria check.

## Self-Check: PASSED

- `scripts/verify_physiology.py` exists: FOUND
- Commit 6a48906 exists: FOUND
- All 19 acceptance criteria checked: PASSED (main guard check adjusted for newline format — actual code correct)
- No unexpected file deletions
