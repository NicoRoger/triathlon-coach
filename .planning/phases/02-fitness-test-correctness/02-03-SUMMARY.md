---
plan: 02-03
phase: 02-fitness-test-correctness
status: complete
completed: 2026-06-05
key-files:
  created:
    - scripts/trigger_fitness_processor.py
  modified:
    - CLAUDE.md
    - .planning/phases/02-fitness-test-correctness/02-03-SUMMARY.md
---

## Summary

Created `scripts/trigger_fitness_processor.py` — a manual backfill trigger that queries activities over the full June 2026 window (bypassing the 6h cutoff in `check_recent()`), matches them against `planned_sessions` with `session_type=fitness_test`, and calls `FitnessTestProcessor.process_fitness_test()` for each match.

Human checkpoint verified via live execution against the DB.

## Checkpoint Result

Final `verify_physiology.py` output after processing:

```
BIKE:
  (nessun dato — FTP watts non calcolabile senza potenziometro; LTHR=158bpm registrato)

RUN:
  Threshold: 4:23/km (263 s/km)  [OK — range 150-360 s/km]  (metodo: threshold_run_20min_provisional, data: 2026-05-30)
  CLAUDE.md: match

SWIM:
  CSS: 1:20/100m (80 s/100m)  [OK — range 70-150 s/100m]  (metodo: css_swim_400_200, data: 2026-06-04)
  CLAUDE.md: match
```

No `[FUORI RANGE]`. No `DISCREPANZA` for measured disciplines.

## Issues Encountered

1. **Planned session `structured: null`** — CSS swim test on 2026-06-04 had `structured=null` so the processor skipped it with `"reason": "no test_type in structured"`. Fixed by patching the planned session to `{"test_type": "css_swim_400_200"}` before re-running.

2. **Unicode cp1252 on Windows** — `→` character in `trigger_fitness_processor.py` caused `UnicodeEncodeError` on the developer's Windows terminal. Fixed by replacing with `->`.

3. **Bike FTP: no power meter** — The 2026-05-26 FTP test activity (`8ba18483`) has `avg_power_w=null`. Garmin recorded the ride without a power sensor. FTP in watts cannot be extracted. LTHR=158bpm noted in `physiology_zones` row (discipline=bike, method=lthr_20min). BIKE shows `(nessun dato)` for FTP — acceptable per D-16.

## Phase 2 Outcome

| Discipline | Status | Value | Source |
|------------|--------|-------|--------|
| SWIM | ✅ Processed | CSS 80 s/100m (1:20/100m) | css_swim_400_200, 2026-06-04 |
| RUN | ✅ In DB | Threshold 263 s/km (4:23/km) | threshold_run_20min_provisional, 2026-05-30 |
| BIKE | ⚠ No power data | LTHR 158bpm recorded | 20min test 2026-05-26, no power meter |

## Self-Check: PASSED
