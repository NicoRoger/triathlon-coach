---
phase: 01-test-suite-analytics-correctness
fixed_at: 2026-06-05T00:00:00Z
review_path: .planning/phases/01-test-suite-analytics-correctness/01-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 6
fixed: 4
skipped: 2
status: partial
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-06-05
**Source review:** `.planning/phases/01-test-suite-analytics-correctness/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, WR-01, WR-02, WR-03, WR-04, WR-05)
- Fixed: 4 (CR-01, WR-01, WR-03, WR-05)
- Skipped: 2 (WR-02, WR-04)

---

## Fixed Issues

### CR-01: `test_b2_daily_excludes_today_from_recent_z` does not actually test the B2 fix

**Files modified:** `tests/test_audit_resilience.py`
**Commit:** `ff74fab`
**Applied fix:** Changed history pattern from `60.0 + (i % 3)` to `60.0 + (i % 3) * 0.8`
(gives mean=60.8, SD≈0.65) and changed `hrv_today` from `35.0` to `59.9`. The new
value produces z≈-1.38, which is in the warning band (-2 < z < -1) and NOT in
`fatigue_critical` territory (z < -2). This means the test now distinguishes "B2 fixed"
(today excluded from `recent_z_scores` → 0 prior warning days → no `fatigue_warning`)
from "B2 broken" (today included → 1 warning day → `fatigue_warning` would trigger).
Updated the docstring to document the z-score math. The original `hrv_today=35.0`
gave z≈-25σ, unconditionally triggering `fatigue_critical` and masking the B2 path
entirely.

---

### WR-01: `_FakeQuery.eq()` permanently mutates `self._rows`

**Files modified:** `tests/test_audit_resilience.py`
**Commit:** `aadb908`
**Applied fix:** Replaced in-place mutation `self._rows = [r for r in self._rows if ...]`
with a clone pattern that returns a new `_FakeQuery` instance with filtered rows,
copying `upserted` to the clone. The change makes query-chain isolation structural
rather than accidental, preventing future state-leak bugs if tests use non-empty
`subjective_log` rows.

---

### WR-03: `test_i2_days_in_month_correct_all_months` does not test a leap year

**Files modified:** `tests/test_audit_resilience.py`
**Commit:** `9b8553a`
**Applied fix:** Added a leap-year February case after the existing month loop.
Uses `datetime(2028, 2, 15)` (2028 is a leap year) and asserts
`days_remaining == 29 - 15 == 14`. A static lookup table `[31, 28, 31, ...]`
would return 28 and fail this assertion; `calendar.monthrange()` returns 29 correctly.

---

### WR-05: Dead no-op code block in `test_h2_pick_test_date_bounded`

**Files modified:** `tests/test_audit_resilience.py`
**Commit:** `581611b`
**Applied fix:** Removed the 3-line dead `for n in [...]` loop with an all-`pass`
body. The loop never changed `sys.modules` state and misled readers into thinking
module isolation was being managed. The test runs correctly without it since
`_pick_test_date` receives `sb` as a parameter.

---

## Skipped Issues

### WR-02: `test_g3_int_none_guard` does not test actual production code

**File:** `tests/test_audit_resilience.py:564`
**Reason:** The reviewer's suggested fix requires importing `render_verification_report`
from `coach.coaching.outcome_verification`. That function does not exist in the module.
The G3 fix (`int(r.get("n") or 0)`) is embedded inside `update_athlete_beliefs()` —
a complex function that requires full Supabase mock infrastructure to call. Applying
the suggested fix would require either: (a) refactoring production code to extract a
standalone testable function, or (b) creating a full integration-style test. Both are
out of scope for an atomic fix. Marking for manual review.
**Original issue:** Test exercises inline dict.get() expressions in the test body
rather than calling production code — provides zero regression coverage for the G3 fix.

---

### WR-04: `_verify_hrv` guard only fires when `today_row is None`

**File:** `scripts/verify_analytics.py:51`
**Reason:** Already fixed in the source. The current code at line 51 already reads
`elif today_row is None or today_row.get("hrv_rmssd") is None:` — exactly the fix
the reviewer recommended. The REVIEW.md was written against the code before this
fix was applied. No change needed.
**Original issue:** Guard did not cover the case where row exists but `hrv_rmssd`
is `None`, producing misleading output.

---

_Fixed: 2026-06-05_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
