---
phase: 02-fitness-test-correctness
verified: 2026-06-06T00:00:00Z
status: human_needed
score: 3/4 must-haves verified
overrides_applied: 0
gaps: []
deferred: []
human_verification:
  - test: "Confirm BIKE FTP absence is accepted as hardware-limited outcome (no power meter)"
    expected: "Decision recorded: BIKE FTP = '(nessun dato)' is acceptable for Phase 2; Phase 4 tracks outstanding disciplines"
    why_human: "ROADMAP SC-2 says 'FTP in DB è tra 80 e 450W' but FTP is absent due to hardware (no power meter on the 2026-05-26 ride). Code and process are correct; human must accept the deviation from SC-2 literal wording or request a re-test plan before Phase 3."
  - test: "Confirm CR-01 (CSS ±10% formula error) is accepted for Phase 2 scope"
    expected: "Decision recorded: CR-01 is a known quality issue in fitness_test_processor.py, tracked in code review, to be fixed in a future phase or standalone fix"
    why_human: "CR-01 in 02-REVIEW.md identifies a formula bug where CSS uses a fixed /2 divisor instead of actual captured distances. The CSS value in DB (80 s/100m) is within bounds, but could be off by ±10%. This does not block phase goal if the deviation is accepted — but requires human sign-off since it affects data correctness."
---

# Phase 2: Fitness Test Correctness — Verification Report

**Phase Goal:** I valori FTP, CSS e soglia corsa nel DB derivano dai test fitness eseguiti da Nicolò a giugno 2026, sono entro bounds fisiologici plausibili, e non sono stati corrotti dai bug E1/E2
**Verified:** 2026-06-06
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `fitness_test_processor.py` does not use `averageSpeed` as FTP proxy or `averagePace` as threshold | VERIFIED | Lines 148-153 and 167-171 of `fitness_test_processor.py` use only `avg_power_w` (splits) and `avg_pace_s_per_km` respectively; comments explicitly document E1/E2 removal |
| 2 | FTP/threshold/CSS in DB are within plausible bounds after processing | PARTIAL | RUN threshold 263 s/km [OK 150-360], SWIM CSS 80 s/100m [OK 70-150]; BIKE FTP absent (no power meter on 2026-05-26 activity — `avg_power_w=null`). Literal ROADMAP SC-2 not fully met. |
| 3 | CSS guard `t400 > t200 > 0` is present — no negative/absurd CSS | VERIFIED | Line 195 `fitness_test_processor.py`: `if t400 is not None and t200 is not None and t400 > t200 > 0`; test `test_e3_css_guard_t400_gt_t200` confirms |
| 4 | `physiology_zones` returns non-null rows with updated post-test timestamps | PARTIAL | SWIM row: css_swim_400_200, 2026-06-04, 80 s/100m. RUN row: threshold_run_20min_provisional, 2026-05-30, 263 s/km. BIKE row exists with `lthr=158bpm` (lthr_run method) but `ftp_w=null` — FTP column is null for the bike discipline. |

**Score:** 2/4 truths fully verified; 2/4 partially verified due to BIKE FTP hardware gap.

**Roadmap SC vs evidence:**

| SC | Text | Status | Evidence |
|----|------|--------|----------|
| SC-1 | fitness_test_processor.py non usa averageSpeed/averagePace fallback | VERIFIED | Code confirmed; comments E1/E2 |
| SC-2 | FTP in DB 80-450W, threshold 150-360 s/km, CSS 70-150 s/100m | PARTIAL | RUN+SWIM in bounds; FTP absent (hardware) |
| SC-3 | CSS guard t400 > t200 > 0 present | VERIFIED | Line 195, test coverage |
| SC-4 | physiology_zones rows non-null with updated timestamp post-test | PARTIAL | RUN+SWIM populated; BIKE row has lthr but ftp_w=null |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/verify_physiology.py` | Read-only physiology zones verifier, min 80 lines | VERIFIED | 250 lines; syntactically valid; queries physiology_zones; prints BIKE/RUN/SWIM with [OK/FUORI RANGE]; reads CLAUDE.md for comparison; no sys.exit; no DB writes |
| `scripts/cleanup_physiology_zones.py` | Dry-run + DELETE of out-of-bounds rows, min 60 lines | VERIFIED | 223 lines; syntactically valid; PLAUSIBLE_BOUNDS imported (not redefined); --confirm flag; .delete().eq("id", ...) present; per-discipline counts |
| `scripts/trigger_fitness_processor.py` | Manual processor trigger, June 2026 window, min 50 lines | VERIFIED | 151 lines; syntactically valid; FitnessTestProcessor imported; 2026-06-01 cutoff; session_type='fitness_test' query; process_fitness_test() call guarded by --dry-run; per-activity try/except |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `verify_physiology.py` | physiology_zones table | `get_supabase().table('physiology_zones').select()` | VERIFIED | Line 62: `.table("physiology_zones").select(...)` |
| `verify_physiology.py` | CLAUDE.md | `Path(__file__).resolve().parent.parent / "CLAUDE.md"` | VERIFIED | Line 28: `CLAUDE_MD_PATH = Path(__file__).resolve().parent.parent / "CLAUDE.md"`; regex extracts ftp_attuale_w, threshold_pace_per_km, css_attuale_per_100m |
| `cleanup_physiology_zones.py` | PLAUSIBLE_BOUNDS | `from coach.coaching.fitness_test_processor import PLAUSIBLE_BOUNDS` | VERIFIED | Line 22 — import, not redefinition; no `PLAUSIBLE_BOUNDS = {` dict literal in script |
| `cleanup_physiology_zones.py` | physiology_zones table | `.delete().eq("id", row_id)` | VERIFIED | Line 198: `sb.table("physiology_zones").delete().eq("id", row_id).execute()` |
| `trigger_fitness_processor.py` | FitnessTestProcessor | `FitnessTestProcessor().process_fitness_test()` | VERIFIED | Line 20 import; line 109 call; guarded by `not args.dry_run` |
| `trigger_fitness_processor.py` | activities + planned_sessions | June 2026 date range + session_type=fitness_test | VERIFIED | Lines 43-88: cutoff_from="2026-06-01T00:00:00+00:00"; `.eq("session_type", "fitness_test")` |

---

### Data-Flow Trace (Level 4)

Scripts are operational one-shots, not dynamic-render components — Level 4 does not apply. The human checkpoint in Plan 03 Task 2 serves as the functional data-flow verification: the executor ran `trigger_fitness_processor.py`, then `verify_physiology.py`, and documented the live output in 02-03-SUMMARY.md.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All three scripts parse cleanly | `python -c "import ast; ast.parse(...)"` × 3 | Syntax ok × 3 | PASS |
| No sys.exit or exit(1) in any script | grep on all three scripts | No matches | PASS |
| No SUPABASE credentials in string literals | grep on verify_physiology.py | No matches | PASS |
| No PLAUSIBLE_BOUNDS redefinition in cleanup script | grep for `PLAUSIBLE_BOUNDS = {` | No matches | PASS |
| E1 fix: no averageSpeed usage as watts | grep `averageSpeed` in fitness_test_processor.py | Only in comment (non-functional) | PASS |
| E2 fix: no averagePace usage as threshold | grep `averagePace` in fitness_test_processor.py | Only in comment (non-functional) | PASS |
| E3 fix: CSS guard present | grep `t400 > t200 > 0` | Line 195 confirmed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FITNESS-01 | 02-02, 02-03 | fitness_test_processor.py does not use averageSpeed/averagePace fallback | VERIFIED | Code confirms E1/E2 removal; comments document intent; REQUIREMENTS.md traceability lists as "Pending" — this is a traceability label only (fix was done in Phase 1 prior work, confirmed by Phase 2) |
| FITNESS-02 | 02-01, 02-02 | FTP/CSS/threshold within plausible bounds | PARTIAL | RUN+SWIM confirmed in bounds; BIKE FTP absent (hardware gap) |
| FITNESS-03 | 02-01, 02-03 | CSS calculated with t400>t200>0 guard | VERIFIED | Line 195 + test coverage |
| VERIFY-02 | 02-01, 02-03 | physiology_zones values correspond to June 2026 tests | PARTIAL | RUN (2026-05-30) and SWIM (2026-06-04) confirmed; BIKE FTP cannot be derived without power meter |

**REQUIREMENTS.md traceability note:** FITNESS-01 is marked "Pending" in REQUIREMENTS.md traceability table, but the acceptance criteria were delivered — the code fix existed before Phase 2 (as per 02-CONTEXT.md §canonical_refs: "già fixato") and is confirmed by code inspection. The traceability label appears to reflect pre-Phase-2 state and was not updated to "Complete" for FITNESS-01. This is a documentation gap, not an implementation gap.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/cleanup_physiology_zones.py` | 137-145 | `unit_suffix` assigned but never used (dead code) | Info | No functional impact — flagged in 02-REVIEW.md IN-01 |
| `scripts/cleanup_physiology_zones.py` | 223 | `if __name__ == "__main__": main()` on single line | Info | Style inconsistency — flagged in 02-REVIEW.md IN-02 |
| `scripts/cleanup_physiology_zones.py` | 97-102 | Initial DB fetch has no try/except — an exception propagates as raw traceback | Warning | If Supabase auth fails, cleanup exits with traceback instead of friendly error — flagged in 02-REVIEW.md WR-03 |
| `scripts/trigger_fitness_processor.py` | 119 | `search_str = notes or ext_id_str` — if notes is non-empty, external_id is never searched for keywords | Warning | Keyword fallback may miss matches when activity has notes but external_id contains test keyword — flagged in 02-REVIEW.md CR-03 |
| `coach/coaching/fitness_test_processor.py` | 196 | CSS formula uses fixed `/2` divisor regardless of actual split distances — error up to ±10% | Warning | CSS value in DB (80 s/100m) may be off by up to ±8 s/100m if Garmin recorded 380m/190m instead of exact 400m/200m — flagged in 02-REVIEW.md CR-01 |
| `coach/coaching/fitness_test_processor.py` | 157 | `_extract_ftp_bike_ramp` falls back to `np_w` when `max_power_w` missing — NP underestimates peak 1-min power | Warning | Would produce silently low ramp FTP — flagged in 02-REVIEW.md WR-04. Not exercised in Phase 2 (no ramp test data). |

No TBD/FIXME/XXX debt markers found in any Phase 2 scripts.

---

### Human Verification Required

#### 1. BIKE FTP Absence — Accept or Plan Re-Test

**Test:** Review the phase goal vs BIKE FTP absence.
The phase goal states "I valori FTP, CSS e soglia corsa nel DB" — implying FTP must be present. ROADMAP SC-2 says "FTP in DB è tra 80 e 450W". The 2026-05-26 FTP test recorded `avg_power_w=null` (no power meter). LTHR (158bpm) was stored instead.

**Expected:** Either (a) accept BIKE FTP absence as hardware-limited for Phase 2 and note that a re-test with a power meter is needed before Phase 5 (WORKOUT-02 requires measured FTP), or (b) conclude Phase 2 has a gap because FTP is not derivable from available data.

**Why human:** The 02-03-PLAN.md explicitly lists "(nessun dato) for that discipline" as an acceptable outcome (D-16). The plan was designed to accept this. However, the ROADMAP SC-2 literally requires FTP in bounds. A human must decide whether the hardware limitation constitutes a phase gap or an accepted deviation. If accepted, this should be documented as an override or a note in CLAUDE.md / Phase 4 tracking.

---

#### 2. CSS Formula Precision (CR-01) — Accept or Fix Before Phase 3

**Test:** Review 02-REVIEW.md CR-01 — CSS formula uses fixed `/2` divisor (assumes exact 400m/200m splits) instead of actual captured distances.
The stored CSS is 80 s/100m. If Garmin captured 380m/190m, true CSS = (t400 - t200)/1.9*100, not (t400 - t200)/2. Error magnitude ≈ 5%.

**Expected:** Either (a) accept the current CSS value as sufficiently close and note CR-01 as a future quality improvement, or (b) treat as a blocker requiring fix before Phase 3 uses these zones for prescriptions.

**Why human:** The value is within PLAUSIBLE_BOUNDS and the CLAUDE.md shows match. The practical impact on training zones (CSS ±4 s/100m) is within noise for current training phase. But the precision concern is real and affects downstream quality (Phase 5, WORKOUT-02). Human sign-off needed on whether this is acceptable for Phase 3 entry.

---

### Gaps Summary

No hard FAILED gaps: all three scripts exist, are syntactically valid, implement their described behavior, and the human checkpoint for Plan 03 was completed with live DB verification (RUN+SWIM populated, BIKE hardware-limited).

The two items requiring human sign-off are:
1. BIKE FTP absence — hardware limitation vs literal ROADMAP SC-2 wording. The plan's D-16 provision covers this as acceptable, but the roadmap wording conflicts.
2. CR-01 CSS formula precision — known ±10% error in `fitness_test_processor.py` that affects the CSS value already stored. Not a Phase 2 script bug, but it touches the data that Phase 2 was supposed to verify as correct.

Both are human decisions, not automated verification failures. The code and process evidence supports the phase being functionally complete for RUN and SWIM, with BIKE FTP deferred due to hardware.

---

_Verified: 2026-06-06_
_Verifier: Claude (gsd-verifier)_
