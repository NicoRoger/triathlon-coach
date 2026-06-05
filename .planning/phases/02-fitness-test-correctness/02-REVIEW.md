---
phase: 02-fitness-test-correctness
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - scripts/verify_physiology.py
  - scripts/cleanup_physiology_zones.py
  - scripts/trigger_fitness_processor.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-05
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Three operational scripts reviewed: `verify_physiology.py` (read-only report of DB zones vs CLAUDE.md), `cleanup_physiology_zones.py` (destructive DELETE of out-of-bounds rows), and `trigger_fitness_processor.py` (manual re-run of `FitnessTestProcessor` over June 2026). The cross-file dependency on `coach/coaching/fitness_test_processor.py` was also read as direct context.

Three critical bugs found: (1) the CSS pace formula produces wrong results when the captured split distance is not exactly 400 m or 200 m; (2) `cleanup_physiology_zones.py` has no coverage for `lthr_run`-method rows stored under `discipline=run` with field `lthr`, so corrupt LTHR rows survive the cleanup; (3) the keyword-fallback logic in `trigger_fitness_processor.py` silently drops the search over `external_id` whenever `notes` is a non-empty string that contains no keywords — preventing detection of matching external IDs. Four warnings cover bounds mismatches, hardcoded date ranges, missing error handling on the initial DB fetch, and a type-safety gap. Two info items cover dead code and cosmetic style.

---

## Critical Issues

### CR-01: CSS formula applies fixed /2 divisor regardless of actual captured distances

**File:** `coach/coaching/fitness_test_processor.py:196`

**Issue:** The CSS formula `(t400 - t200) / 2` assumes the 400 m split is exactly 400 m and the 200 m split is exactly 200 m. The split-matching logic accepts any split where `350 <= dist <= 450` as the "400 m" and `180 <= dist <= 250` as the "200 m". If Garmin records, for example, 380 m and 190 m (both inside the acceptance windows), the denominator should be `(380 - 190) / 100 = 1.9` — giving `css = (t400 - t200) / 1.9` — but the code divides by 2 regardless.

The error magnitude is up to ≈±10 % of CSS (e.g., a true 80 s/100 m could be reported as 84 s/100 m when the short split was 190 m). This cascades into corrupted swim zones stored in the DB.

**Fix:**
```python
if t400 is not None and t200 is not None and t400 > t200 > 0:
    # Use actual captured distances instead of assuming exact 400/200
    dist_diff_m = dist_400 - dist_200  # need to track these alongside t400/t200
    if dist_diff_m > 0:
        css_per_100m = (t400 - t200) / dist_diff_m * 100
        return round(css_per_100m, 1)
    return None
```

To implement, track `dist_400` and `dist_200` alongside `t400` and `t200` in the loop:
```python
dist_400 = None
dist_200 = None
for s in splits:
    dist = float(s.get("distance_m") or s.get("distance") or 0)
    time_s = float(s.get("duration_s") or s.get("movingDuration") or s.get("elapsedDuration") or 0)
    if 350 <= dist <= 450 and t400 is None:
        t400, dist_400 = time_s, dist
    elif 180 <= dist <= 250 and t200 is None:
        t200, dist_200 = time_s, dist
```

---

### CR-02: `cleanup_physiology_zones.py` silently skips corrupt `lthr_run` rows stored under `discipline=run`

**File:** `scripts/cleanup_physiology_zones.py:50-73`

**Issue:** `_check_row()` handles only `discipline in ("bike", "run", "swim")`. When `discipline == "run"`, it checks the `threshold_pace_s_per_km` column. But `lthr_run` tests also write to `discipline=run` (via `field_map` in `fitness_test_processor.py:295`) and use the `lthr` column, not `threshold_pace_s_per_km`. A corrupt `lthr` value (e.g., a pace value in the hundreds accidentally stored as bpm) will never be flagged because:
- `_check_row` for `run` only reads `threshold_pace_s_per_km`
- `lthr` field is not checked at all
- The `PLAUSIBLE_BOUNDS["lthr_run"]` range `(120, 200)` exists in the processor but is not used in cleanup

**Fix:** Add an `lthr` check inside the `run` branch (or add an `elif discipline == "run_lthr"` if the method column is used for disambiguation):
```python
elif discipline == "run":
    # threshold_pace check
    val_pace = row.get("threshold_pace_s_per_km")
    if val_pace is not None:
        lo, hi = PLAUSIBLE_BOUNDS["threshold_run_30min"]
        if not (lo <= val_pace <= hi):
            return True, f"threshold={val_pace} s/km", val_pace, (lo, hi)
    # lthr check (lthr_run method also writes discipline=run)
    val_lthr = row.get("lthr")
    if val_lthr is not None:
        lo, hi = PLAUSIBLE_BOUNDS["lthr_run"]
        if not (lo <= val_lthr <= hi):
            return True, f"lthr={val_lthr} bpm", val_lthr, (lo, hi)
    return False, "run", None, None
```

---

### CR-03: Keyword-fallback in `trigger_fitness_processor.py` only searches `external_id` when `notes` is falsy — silently misses matches

**File:** `scripts/trigger_fitness_processor.py:117-120`

**Issue:**
```python
notes = (activity.get("notes") or "").lower()
ext_id_str = str(activity.get("external_id") or "").lower()
search_str = notes or ext_id_str
```
`notes or ext_id_str` evaluates to `notes` whenever `notes` is non-empty, regardless of whether it contains any keywords. If an activity has a non-empty notes field such as `"Z2 recovery ride"` (no keywords), and its `external_id` contains `"ftp_test_20min"`, the keyword check will test the notes string, find nothing, and never test the external_id. The test goes unreported to the operator.

This diverges from the equivalent logic in `fitness_test_processor.py:465-468` which uses `notes or external_id` as a single concatenated string: `name = (activity.get("notes") or activity.get("external_id") or "").lower()`. The trigger script should match that reference implementation.

**Fix:**
```python
notes = (activity.get("notes") or "").lower()
ext_id_str = str(activity.get("external_id") or "").lower()
search_str = f"{notes} {ext_id_str}".strip()   # search both fields always
if any(kw in search_str for kw in keywords):
    ...
```

---

## Warnings

### WR-01: `verify_physiology.py` uses the `threshold_run_30min` bounds key regardless of the actual `method` stored in the DB row

**File:** `scripts/verify_physiology.py:153`

**Issue:** The code hard-codes `PLAUSIBLE_BOUNDS.get("threshold_run_30min", (150, 360))` for the RUN section. But the DB may contain a row with `method="threshold_run_20min_provisional"` (confirmed present per CLAUDE.md, 2026-05-30). That method key does not exist in `PLAUSIBLE_BOUNDS`, so the fallback tuple `(150, 360)` is used. For the current data this happens to be the same range, but the bounds lookup should be parameterised on the actual `method` value to be robust when new provisional methods are introduced — and to surface a visible warning if the key is unknown rather than silently falling back.

**Fix:**
```python
method_key = run_row.get("method") or "threshold_run_30min"
bounds = PLAUSIBLE_BOUNDS.get(method_key) or PLAUSIBLE_BOUNDS.get("threshold_run_30min", (150, 360))
if not PLAUSIBLE_BOUNDS.get(method_key):
    print(f"  AVVISO: metodo '{method_key}' non presente in PLAUSIBLE_BOUNDS — bounds di fallback usati")
```

---

### WR-02: `trigger_fitness_processor.py` date range is hardcoded to June 2026 — will silently produce zero results in any other month

**File:** `scripts/trigger_fitness_processor.py:43-44`

**Issue:**
```python
cutoff_from = "2026-06-01T00:00:00+00:00"
cutoff_to   = "2026-06-30T23:59:59+00:00"
```
The script's docstring says "bypasses the 6 h cutoff". When run in July 2026 or later it will fetch zero activities without any operator warning. The intent is manual re-triggering for historical data, but a future operator or a CI re-run will find nothing and assume "clean" when in fact the date range is stale.

**Fix:** Accept `--from` / `--to` arguments with the June 2026 defaults, and print a prominent warning when the `--to` date is in the past:
```python
parser.add_argument("--from", dest="from_date", default="2026-06-01T00:00:00+00:00")
parser.add_argument("--to",   dest="to_date",   default="2026-06-30T23:59:59+00:00")
```
Alternatively, default `--to` to `now()` and `--from` to `--to - 30 days`.

---

### WR-03: `cleanup_physiology_zones.py` initial DB fetch has no error handling — an exception crashes with no user-visible message

**File:** `scripts/cleanup_physiology_zones.py:97-103`

**Issue:**
```python
res = (
    sb.table("physiology_zones")
    .select(...)
    .execute()
)
rows = res.data or []
```
If the Supabase request fails (network error, auth failure, schema error), the unhandled exception propagates as a Python traceback with no friendly message. In `verify_physiology.py` the equivalent query is wrapped in `try/except` with a printed error. The cleanup script should match this pattern, especially since it is the most dangerous script (it performs DELETEs).

**Fix:**
```python
try:
    res = sb.table("physiology_zones").select(...).execute()
    rows = res.data or []
except Exception as exc:
    print(f"ERRORE: impossibile leggere physiology_zones: {exc}")
    return
```

---

### WR-04: `_extract_ftp_bike_ramp` reads `max_power_w` then falls back to `np_w` — NP is not a valid proxy for peak 1-min power in a ramp test

**File:** `coach/coaching/fitness_test_processor.py:157`

**Issue:**
```python
max_power = activity.get("max_power_w") or activity.get("np_w")
```
`np_w` (Normalised Power) for a full ramp-test activity is typically close to the average power, which is much lower than the last-minute max used by the ramp protocol. Using NP when `max_power_w` is missing will underestimate the FTP significantly (often by 20–40 W). The fallback should be blocked and surfaced as an extraction failure rather than producing a silently wrong FTP.

This is not in one of the three reviewed scripts, but it is exercised directly by `trigger_fitness_processor.py` whenever it calls `process_fitness_test()` for a ramp test. Noting here because `trigger_fitness_processor.py` is the only user-facing entry point to the processor for historical tests and its correctness depends on this upstream behaviour.

**Fix:** Remove the `np_w` fallback:
```python
max_power = activity.get("max_power_w")
if not max_power:
    return None  # fallback to _try_fallback_extraction
```

---

## Info

### IN-01: `unit_suffix` is assigned but never used in `cleanup_physiology_zones.py`

**File:** `scripts/cleanup_physiology_zones.py:137-145`

**Issue:** `unit_suffix` is set to `""`, `"W"`, `" s/km"`, or `" s/100m"` inside the dry-run formatting loop, but is never referenced after assignment. The variable is dead code.

**Fix:** Remove lines 137–145 (the `unit_suffix = ...` assignments). `range_str` already includes the unit and is what the `print()` statement uses.

---

### IN-02: `if __name__ == "__main__": main()` on one line in `cleanup_physiology_zones.py`

**File:** `scripts/cleanup_physiology_zones.py:223`

**Issue:** The guard is written on a single line, inconsistent with every other script in the `scripts/` directory (all use a two-line form). No functional impact, but inconsistent with project style.

**Fix:**
```python
if __name__ == "__main__":
    main()
```

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
