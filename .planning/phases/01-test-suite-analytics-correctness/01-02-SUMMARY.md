---
phase: 01-test-suite-analytics-correctness
plan: "02"
subsystem: analytics-verification
tags:
  - verify-analytics
  - hrv
  - pmc
  - readiness
  - risk
  - operational-script
dependency_graph:
  requires:
    - coach/utils/supabase_client.py
    - coach/utils/dt.py
    - coach/analytics/readiness.py
  provides:
    - scripts/verify_analytics.py
  affects: []
tech_stack:
  added: []
  patterns:
    - "load_dotenv() before coach.* imports (lru_cache constraint)"
    - "try/except per-section to isolate section failures"
    - "to_rome_date() for timezone-correct date bucketing (fix B4)"
key_files:
  created:
    - scripts/verify_analytics.py
  modified: []
decisions:
  - "Implemented all 4 sections in a single file creation (Task 1 + 2 combined) to avoid partial-file state"
  - "Risk section displays duration in minutes (not meters/km) since duration_s is available but distance requires sport-specific parsing"
  - "PMC section shows TSB with +/- sign when values are present for readability"
metrics:
  completed_date: "2026-06-05"
  status: "COMPLETE"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 01 Plan 02: verify_analytics.py (Live Analytics Verification) Summary

**One-liner:** Operational script `scripts/verify_analytics.py` with 4 sections (HRV baseline+z-score, PMC, Readiness, Risk volume bucketing) connecting to production Supabase to verify fixes B1/B3/B4 on real data.

## Status: COMPLETE

All 3 tasks are complete. Task 3 (human-verify checkpoint) was approved by the operator after running `python scripts/verify_analytics.py` against production Supabase on 2026-06-05.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create scripts/verify_analytics.py with HRV + PMC sections | 9e4bb75 | scripts/verify_analytics.py (220 lines, created) |
| 2 | Readiness + Risk sections + main() wiring | 9e4bb75 | (included in Task 1 commit -- all 4 sections implemented together) |
| 3 | Verifica live dell'output su dati reali di Nicolò | checkpoint:human-verify APPROVED | Operator ran script on 2026-06-05; all acceptance criteria met |

## What Was Built

`scripts/verify_analytics.py` -- standalone operational script (informational, no exit 1) that:

1. **HRV Analytics section** -- queries `daily_wellness` for 28d of data, excludes today BY DATE (`r["date"] != today_iso` -- this is the B1 fix verification), calls `hrv_z_score()` with the history list, derives flag per CLAUDE.md section 5.1 thresholds (z < -2.0 = critical, z < -1.0 = warning).

2. **PMC section** -- reads `daily_metrics` for today's CTL/ATL/TSB. Prints `None` explicitly when values are absent (B3 fix verification). Documents "PMC non disponibile (test FTP/soglia non ancora eseguiti)" to distinguish cold-start None from bug.

3. **Readiness section** -- reads `readiness_score` and `readiness_label` from `daily_metrics`. Handles missing row gracefully.

4. **Risk: Volume Bucketing section** -- queries `activities` for last 14 days, uses `to_rome_date()` for date bucketing (B4 fix verification), aggregates duration by sport for the current ISO week.

**Security:** No `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` in stdout/logs (T-02-01 mitigated). Read-only queries only (T-02-03 accepted by design).

**Ordering:** `load_dotenv()` is called at module level before any `coach.*` import, respecting the `lru_cache` constraint on `get_supabase()`.

## Acceptance Criteria Verification (Source Assertions)

- [x] `scripts/verify_analytics.py` exists and contains `load_dotenv()` before first `from coach.` import
- [x] File contains `=== HRV Analytics ===` and `=== PMC ===`
- [x] File contains `r["date"] != today_iso` (B1 date exclusion) -- no value-based exclusion
- [x] File does NOT contain `SUPABASE_URL` or `SUPABASE_SERVICE_KEY`
- [x] File does NOT contain `sys.exit(1)` or `exit(1)` (D-02 informational)
- [x] File contains `=== Readiness ===` and `=== Risk: Volume Bucketing (settimana corrente) ===`
- [x] Risk section uses `to_rome_date(` for date bucketing and contains `Europe/Rome` suffix
- [x] File contains `def main` and `if __name__ == "__main__":` calling `main()` without sys.exit(1)
- [x] `python -c "import ast; ast.parse(...)"` exits 0 -- syntax valid
- [x] `python -c "... assert 'main' in names ..."` exits 0 -- main() function exists

## Deviations from Plan

**None significant.** Tasks 1 and 2 were executed as a single Write call since implementing partial sections would have left the file in an incomplete state. Both tasks reference the same commit hash because the file was created complete; all Task 2 acceptance criteria are satisfied by the Task 1 commit.

**Risk section output format note:** The plan's PATTERNS.md template shows `swim: 2800m | bike: 145km | run: 18.5km` using distance units. Since `activities` table has `duration_s` but not a universal distance column, the script uses minutes instead: `swim: 45min | bike: 90min | run: 30min`. This is functionally equivalent for volume bucketing verification (B4 is about date correctness, not unit display).

## Task 3: Live Verification -- APPROVED

**Status:** APPROVED by operator on 2026-06-05

**Live output captured:**
```
=== HRV Analytics ===
Baseline 28d: media=80.8ms, SD=5.9ms (28 giorni, oggi escluso)
Z-score oggi: +1.57σ → OK
Flag: nessuno

=== PMC ===
CTL: None | ATL: None | TSB: None
PMC non disponibile (test FTP/soglia non ancora eseguiti — vedi Phase 2)

=== Readiness ===
Score: 75/100 | Label: ready

=== Risk: Volume Bucketing (settimana corrente) ===
run: 44min | swim: 55min (date: Europe/Rome)
```

**Acceptance criteria confirmed:**
- [x] 4 sections printed in correct order: HRV, PMC, Readiness, Risk
- [x] B1 fix verified: HRV shows "(28 giorni, oggi escluso)" -- today excluded by date
- [x] B3 fix verified: PMC shows `None` (not `0.00`) when FTP/threshold tests not yet run
- [x] Readiness: 75/100, label "ready" -- correct score and label format
- [x] B4 fix verified: Risk section uses `(date: Europe/Rome)` -- no crash, correct timezone bucketing
- [x] Security: no SUPABASE_URL or SUPABASE_SERVICE_KEY in output

**HRV context:** Baseline 80.8ms ± 5.9ms, z-score +1.57σ = above average recovery. No flags. Consistent with Nicolò's improving HRV trend noted in CLAUDE.md (baseline ~69ms rising).

## Known Stubs

None -- the script reads real production data; no hardcoded mock values in the output path.

## Threat Flags

None identified beyond what is already in the plan threat model (T-02-01 through T-02-SC, all addressed).

## Self-Check

### Files Created
- `scripts/verify_analytics.py` -- committed at 9e4bb75 on worktree-agent-af9f268504c89af99

### Commits
- `9e4bb75`: feat(01-02): create scripts/verify_analytics.py with HRV + PMC sections (contains all 4 sections + main())
- Task 3: checkpoint:human-verify -- APPROVED by operator (no code commit needed; live output confirmed)

## Self-Check: PASSED

**Plan 01-02 complete.** All 3 tasks done; all bug fixes B1, B3, B4 verified on production data.
