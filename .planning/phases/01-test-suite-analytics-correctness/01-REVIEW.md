---
phase: 01-test-suite-analytics-correctness
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tests/test_audit_resilience.py
  - scripts/verify_analytics.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-05
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Two files were reviewed: `tests/test_audit_resilience.py` (978 lines, 40+ test methods
covering audit IDs B1-B4, D1-D5, G1-G3, H1-H3, I1-I9, L2-L5, O1-O9) and
`scripts/verify_analytics.py` (221 lines, operational inspection script for live DB).

Both files are broadly correct and well-structured. The test suite demonstrates solid
coverage of the specific audit regression scenarios. However, there is one critical
correctness defect (a test that silently passes whether or not the fix being tested is
present), five warnings about brittle or incomplete test/script logic, and three info
items about dead code and minor quality.

---

## Critical Issues

### CR-01: `test_b2_daily_excludes_today_from_recent_z` does not actually test the B2 fix

**File:** `tests/test_audit_resilience.py:170`

**Issue:** The test is intended to verify that `daily.compute_for` does not include
today's z-score in `recent_z_scores`, which would prevent `fatigue_warning` from
triggering after only one low-HRV day. However, with `hrv_today=35.0` against a
history around 60ms (SD ~1.0), the z-score is approximately -25, which unconditionally
triggers `fatigue_critical` — a hard override in `compute_readiness` that bypasses the
`fatigue_warning` path entirely. The assertion `"fatigue_warning" not in m["flags"]`
therefore passes regardless of whether today's z-score is included in `recent_z_scores`
or not: the B2 bug would not cause `fatigue_warning` to appear here because
`fatigue_critical` is always set first.

In practice, the test does not distinguish "B2 fixed" from "B2 still broken but
overshadowed by fatigue_critical", meaning a revert of the B2 fix would leave this
test green.

**Fix:** Use a `hrv_today` value that falls in the warning band (z between -2 and -1)
rather than deep crash territory. For example, with history mean=60 and SD=1.5, a
value of 58.5 gives z ≈ -1.0 exactly. Adjust `today_wellness.hrv_rmssd` so that z is
between -2.0 and -1.0 to force the consecutive-days path while avoiding
`fatigue_critical`:

```python
# history: 15 days of 60.0 → SD=0 → z is always 0.0 (boundary case)
# Use a history with realistic SD first:
for i in range(15, 0, -1):
    d = (day - timedelta(days=i)).isoformat()
    # Pattern that gives mean≈60.5, SD≈1.2 for z-score sensitivity
    wellness.append({"date": d, "hrv_rmssd": 60.0 + (i % 3) * 0.8, ...})
# oggi: valore in banda warning (−2 < z < −1), non in fatigue_critical
wellness.append({"date": day.isoformat(), "hrv_rmssd": 58.8, ...})
# z ≈ −1.4 → triggers warning check but not fatigue_critical
# With B2 bug: "fatigue_warning" IN flags (today included → consecutive ≥ 1)
# With B2 fix: "fatigue_warning" NOT IN flags (today excluded → 0 prior days)
```

---

## Warnings

### WR-01: `_FakeQuery.eq()` permanently mutates `self._rows` — cross-query state leak in daily.py tests

**File:** `tests/test_audit_resilience.py:56`

**Issue:** `_FakeQuery.eq()` filters `self._rows` in-place. When `daily.py`'s
`_fetch_recent_subjective` calls `.eq("illness_flag", True)` on the `subjective_log`
fake query, it mutates the rows that were already provided. This is a separate
`_FakeQuery` object (each `_FakeSupabase.table()` call creates a fresh instance with a
copy of the table data), so the mutation is isolated to that call chain. The
current tests pass because `subjective_log` is always `[]`. However, if any future test
passes a non-empty `subjective_log` with rows that do not have `illness_flag=True`,
calling `.eq("illness_flag", True).gte(...).execute()` after `.select("*").gte(...)`
on the same query chain would silently filter out data for the `gte` step because `eq`
mutates before `gte` no-ops. More importantly: the query chain
`.select("logged_at").eq("illness_flag", True).gte("logged_at", since_5)` always
uses a fresh `_FakeQuery` instance (new `table()` call in `res2`), so the isolation is
accidental rather than structural.

**Fix:** Make `eq()` non-destructive by returning a new `_FakeQuery` with filtered
rows, or use a copy:

```python
def eq(self, col, val):
    filtered = [r for r in self._rows if r.get(col) == val]
    clone = _FakeQuery(filtered)
    clone.upserted = self.upserted
    return clone
```

### WR-02: `test_g3_int_none_guard` does not test actual production code — it tests a local pattern reproduction

**File:** `tests/test_audit_resilience.py:564`

**Issue:** The test only exercises two inline `dict.get()` + `int()` expressions
written directly in the test body. It does not import or call any function from
`outcome_verification` or any other module. If the actual fix in the target module is
reverted or applied to the wrong location, this test still passes. It provides zero
regression coverage for the G3 fix.

**Fix:** Import and call the actual rendering function from the production module that
was fixed:

```python
def test_g3_int_none_guard():
    from coach.coaching.outcome_verification import render_verification_report  # adjust name
    # Provide a row with n=None; assert no TypeError is raised and output is a string
    report = render_verification_report([{"n": None, ...}])
    assert isinstance(report, str)
```

### WR-03: `test_i2_days_in_month_correct_all_months` does not test a leap year

**File:** `tests/test_audit_resilience.py:287`

**Issue:** The I2 bug was an arithmetic error in `days_in_month` (December and
presumably any non-31-day month). The test checks January (31), February non-leap
(28), April (30), and December (31). February in a leap year (29 days) is not
covered. The fix uses `calendar.monthrange()` which correctly handles leap years;
however, the absence of a leap-year case means a regression to a simple
`month_days = [31, 28, 31, 30, ...]` lookup table would pass all current assertions.

**Fix:** Add a leap-year February case:

```python
expected = {1: 31, 2: 28, 4: 30, 12: 31}
# Add leap year check
fake_now_leap = datetime(2028, 2, 15, tzinfo=timezone.utc)  # 2028 is a leap year
# ... same patching pattern → assert stats["days_remaining"] == 29 - 15 == 14
```

### WR-04: `_verify_hrv` in `scripts/verify_analytics.py` silently produces misleading output when today has no HRV but history exists

**File:** `scripts/verify_analytics.py:51`

**Issue:** When `today_row` is not None but `today_row.get("hrv_rmssd")` is None (i.e.
the row exists but HRV was not recorded), execution falls through to the `else` branch
(line 60) unconditionally and `hrv_today_val = today_row["hrv_rmssd"]` is `None`.
This is then passed to `hrv_z_score(None, hrv_history)` which returns `None` (the
function guards `if hrv_today is None`). The output will print "Z-score oggi: N/A"
which is correct, but the execution path arrived there accidentally via the `None`
guard in `hrv_z_score` rather than through the explicit `today_row.get("hrv_rmssd")
is None` check on line 51. The guard on line 51 only fires when `today_row` itself is
None, not when the row exists but HRV is absent — the logic structure creates a hidden
path difference that would produce different print output ("Z-score oggi: N/A" vs
"Nessun dato HRV per oggi") without indicating the distinction to the operator. This
can mask a data-quality issue (Garmin returned a wellness row with no HRV value).

**Fix:** Extend the guard to cover the `hrv_rmssd is None` case explicitly:

```python
if today_row is None or today_row.get("hrv_rmssd") is None:
    print(f"Nessun dato HRV per oggi ({today_iso})")
    if hrv_history:
        mean = statistics.fmean(hrv_history)
        sd = statistics.pstdev(hrv_history)
        print(f"Baseline 28d: media={mean:.1f}ms, SD={sd:.1f}ms "
              f"({len(hrv_history)} giorni, oggi escluso)")
```

### WR-05: `test_h2_pick_test_date_bounded` has dead / no-op code block (lines 552-554)

**File:** `tests/test_audit_resilience.py:552`

**Issue:** Lines 552-554 contain a `for n in [...]` loop with an `if ... pass` body
that does nothing. The loop was apparently a guard to check whether modules are
already in `sys.modules` before deciding what to do, but the condition is written so
that the only branch is `pass`. It neither stubs nor preserves any module. This code
is dead and misleads the reader about the test's setup intent — it looks like module
isolation is being handled but nothing is actually done.

```python
for n in ["coach.utils.supabase_client", "coach.utils.dt"]:
    if n in sys.modules and not hasattr(sys.modules[n], "today_rome") and n.endswith("dt"):
        pass   # dead — this branch never changes sys.modules
```

**Fix:** Remove the dead block. If module isolation is required (it is not, since
`_pick_test_date` receives `sb` as a parameter and calls `dt.today_rome` only in
`schedule_overdue_tests`, not in `_pick_test_date` directly), add an explicit stub.
Otherwise remove entirely:

```python
# Remove lines 552-554 entirely — they are dead code and not needed
ts = _load("coach.coaching.test_scheduler", "coach/coaching/test_scheduler.py")
result = ts._pick_test_date(_SB(), date(2026, 6, 1))
assert result is not None
```

---

## Info

### IN-01: `test_b2_daily_excludes_today_from_recent_z` comment contradicts observable behavior

**File:** `tests/test_audit_resilience.py:186`

**Issue:** The inline comment reads "crollo singolo molto basso → fatigue_critical
possibile" but with `hrv_today=35.0` against a stable history of ~60ms, `fatigue_critical`
is guaranteed (z ≈ -25σ), not merely "possible". This is a documentation quality issue
that confuses the intent of the assertion boundary. (Note: the underlying CR-01 finding
identifies the more serious correctness consequence.)

**Fix:** Update comment to accurately reflect what the test actually produces:

```python
# Crollo a 35ms → fatigue_critical CERTO (z ≈ -25σ); fatigue_warning non appare
# perché il path del warning è cortocircuitato. Vedere CR-01 per copertura corretta.
assert "fatigue_warning" not in m["flags"]
```

### IN-02: `scripts/verify_analytics.py` uses `logging.basicConfig(level=INFO)` which enables httpx request logging — acknowledged but undocumented in the script itself

**File:** `scripts/verify_analytics.py:206`

**Issue:** The security note in the implementation description (T-02-01) acknowledges
that `logging.basicConfig(level=INFO)` causes httpx to log the Supabase URL. This is
accepted per the plan's analysis. However, the script itself contains no inline
comment warning the operator that running it in a terminal with scrollback or in a CI
environment (log aggregators) may expose the Supabase URL in INFO-level HTTP request
lines. An operator using this script in an unexpected context could inadvertently leak
infrastructure URLs.

**Fix:** Add a comment at the logging setup to surface the known behavior:

```python
# NOTE: INFO level causes httpx to log HTTP request URLs (including the Supabase URL).
# Acceptable for local dev inspection; avoid piping output to log aggregators.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
```

### IN-03: `test_g1_parses_zero_from_biometric_fallback` relies on module cached in `sys.modules` from a prior test

**File:** `tests/test_audit_resilience.py:601`

**Issue:** The test checks `sys.modules.get("coach.coaching.extract_beliefs_from_observations")`
and only loads the module if it is absent. This means the test's behavior depends on
the execution order of tests in the file. If `test_g1_no_contradiction_when_zero_candidates`
runs first (it does in the current file order), the module is loaded with a specific
`belief_engine` stub. If pytest runs tests in a different order or the test is run in
isolation, the stub may differ or the module may not be loaded. The test is not
hermetic.

**Fix:** Remove the conditional load and always load the module with an explicit stub,
mirroring the pattern in `test_g1_no_contradiction_when_zero_candidates`:

```python
def test_g1_parses_zero_from_biometric_fallback():
    be = types.ModuleType("coach.analytics.belief_engine")
    be.list_beliefs = lambda **k: []  # type: ignore
    be.contradict_belief = be.create_belief = be.reinforce_belief = lambda *a, **k: None  # type: ignore
    sys.modules["coach.analytics.belief_engine"] = be
    mod = _load("coach.coaching.extract_beliefs_from_observations",
                "coach/coaching/extract_beliefs_from_observations.py")
    cands = mod.parse_observations_to_candidates("### Titolo\n- **k**: v\n")
    assert cands == []
```

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
