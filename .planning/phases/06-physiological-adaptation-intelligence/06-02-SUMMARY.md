---
phase: 06-physiological-adaptation-intelligence
plan: "02"
subsystem: analytics-coaching
tags: [tdd, wave-2, adaptation-intelligence, fatigue-classification, green]
dependency_graph:
  requires:
    - 06-01 (migration DB + RED test scaffold)
  provides:
    - coach/analytics/readiness.py: FatigueResult dataclass + classify_fatigue_type() + helpers
    - coach/coaching/post_session_analysis.py: fatigue hook + extended session_analyses record
  affects:
    - session_analyses (rows now include fatigue_type, fatigue_confidence, sport)
    - plan 03 (get_weekly_context can now query last_fatigue_by_sport from real data)
    - plan 04 (update_beliefs_from_session_patterns consumes fatigue_type from session_analyses)
tech_stack:
  added: []
  patterns:
    - FatigueResult dataclass (analytics output pattern — mirrors ReadinessReport)
    - Decision tree with guard clauses returning early (mirrors compute_flags pattern)
    - statistics.fmean() for half-split averages
    - Lazy import inside function body (mirrors modulation lazy import pattern)
    - fatigue classification runs BEFORE try/except BudgetExceededError (zero LLM, never raises)
key_files:
  created: []
  modified:
    - coach/analytics/readiness.py
    - coach/coaching/post_session_analysis.py
decisions:
  - "FatigueResult added immediately after ReadinessReport (line 64) per PATTERNS.md self-extension pattern — same @dataclass convention, same file"
  - "5% pace drop threshold for bike (Claude's Discretion from RESEARCH.md) — consistent with run/swim to avoid false negatives on athletes whose power decays gradually (documented inline)"
  - "classify_fatigue_type positioned outside/before BudgetExceededError guard — zero LLM function must run even when API budget exhausted"
  - "debrief_rpe extracted via next() generator with is not None guard — handles mixed debrief entries where rpe key may be absent"
metrics:
  duration: "7min"
  completed: "2026-06-08T21:00:42Z"
  tasks_completed: 2
  files_changed: 2
requirements: [ADAPT-01]
---

# Phase 06 Plan 02: classify_fatigue_type() — GREEN Summary

**One-liner:** Deterministic fatigue classification (muscular vs cardiovascular) via HR drift + pace drop + RPE implemented in analytics layer and hooked into post-session pipeline saving fatigue_type/fatigue_confidence/sport to session_analyses.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| setup | Bring wave-1 foundation into worktree branch | 02a30bd | migrations/2026-06-08-physiological-adaptation.sql, tests/test_fatigue_classification.py, tests/test_physio_adaptation.py |
| 1 | classify_fatigue_type() + helpers in readiness.py (GREEN) | ab88dda | coach/analytics/readiness.py |
| 2 | Hook in post_session_analysis.py — persist fatigue_type/confidence/sport | 1deaab7 | coach/coaching/post_session_analysis.py |

## What Was Built

### Task 1: `coach/analytics/readiness.py` extensions

**`FatigueResult` dataclass** (added after `ReadinessReport`, line 65):
- `failure_type: Optional[str]` — 'muscular' | 'cardiovascular' | 'mixed' | None
- `confidence: float` — 0.0–1.0
- `signal_used: str` — 'hr_drift+pace' | 'rpe_only' | 'insufficient'
- `notes: Optional[str] = None`

**`_compute_hr_drift(activity, splits) -> Optional[float]`**:
- Extracts HR per split via `s.get("avg_hr") or s.get("hr")`, discards None
- Requires 4+ valid values; divides at `len//2`
- Returns `fmean(second_half) - fmean(first_half)` (positive = HR rises = cardiovascular signal)

**`_compute_pace_drop(sport, splits) -> Optional[float]`**:
- Discipline-specific: run -> `avg_pace_s_per_km`, swim -> `avg_pace_s_per_100m`, bike -> `avg_power_w`
- Returns relative degradation: positive = worse performance (slower pace or less power)
- 5% threshold for bike (Claude's Discretion — consistent with run/swim)

**`classify_fatigue_type(activity, splits, debrief_rpe) -> FatigueResult`**:
Decision tree (D-03):
1. `duration_s < 1800` -> `FatigueResult(None, 0.0, 'insufficient', 'Sessione < 30min')`
2. No splits -> RPE fallback: RPE>=8 -> `('muscular', 0.4, 'rpe_only', ...)`, else `(None, 0.3, 'rpe_only', ...)`
3. Compute hr_drift + pace_drop, apply thresholds:
   - cardiovascular_signal: `hr_drift > 10.0`
   - muscular_signal: `hr_drift <= 10 AND RPE >= 8 AND pace_drop > 0.05`
   - Both -> mixed (0.65), cardio only -> `min(0.9, 0.6 + (drift-10)*0.02)`, muscular only -> 0.7 if RPE>=9 else 0.6, none -> (None, 0.3)

Zero LLM imports throughout — analytics layer constraint preserved.

### Task 2: `coach/coaching/post_session_analysis.py` extensions

**Injection point** (after `zone_compliance` computation, before context_parts assembly):
```python
from coach.analytics.readiness import classify_fatigue_type
splits = activity.get("splits") or None
debrief_rpe = next((int(d["rpe"]) for d in debrief if d.get("rpe") is not None), None)
fatigue_result = classify_fatigue_type(activity, splits, debrief_rpe)
```

**Extended `record` dict** for `session_analyses` insert:
```python
"fatigue_type": fatigue_result.failure_type or "insufficient_data",
"fatigue_confidence": fatigue_result.confidence,
"sport": sport,   # resolves Open Question 2 / Pitfall 2
```

Existing keys (`activity_id`, `analysis_text`, `suggested_actions`, `model_used`, `cost_usd`) unchanged. Classification positioned outside `try/except BudgetExceededError` — runs even when LLM budget exhausted.

## Verification Results

```
python -m pytest tests/test_fatigue_classification.py::test_cardiovascular_signal \
  tests/test_fatigue_classification.py::test_muscular_signal \
  tests/test_fatigue_classification.py::test_fallback_rpe_only_no_splits \
  tests/test_fatigue_classification.py::test_insufficient_data_short_session \
  tests/test_fatigue_classification.py::test_missing_splits_low_rpe -x -q
=> 5 passed (GREEN)

python -m pytest tests/ -q --ignore=tests/manual
=> 179 passed, 3 failed
   (3 failures are Wave 0 RED tests for plans 03+04 — expected, out of scope for plan 02)
   - test_belief_update_minimum_sessions (plan 04 target)
   - test_belief_update_skips_null_session_type (plan 04 target)
   - test_skill_active_beliefs_step (plan 03 target)

grep llm_client/anthropic/google coach/analytics/readiness.py
=> CLEAN — no LLM imports
```

## Deviations from Plan

None — plan executed exactly as written.

### Design Notes (not deviations)

1. **Worktree setup**: The worktree branch was based off `main` and did not have the wave-1 foundation commits (migration + RED test scaffold from plan 01). Cherry-picked commits 2948aa2 + 8680ac8 (excluding `.claude/settings.local.json` modification) and committed as `02a30bd` to provide the test contract before implementing GREEN code.

2. **5% bike threshold**: Explicitly deferred to Claude's Discretion in RESEARCH.md §D-03. Chose 5% consistent with run/swim rather than a different threshold to avoid false negatives on endurance athletes with gradual power decay. Documented inline in `_compute_pace_drop`.

## Known Stubs

None. The implementation is complete:
- `classify_fatigue_type()` is fully deterministic with all branches covered
- `post_session_analysis.py` hook writes real values on every `analyze_session()` call
- The 3 remaining RED tests are Wave 0 stubs for plans 03/04 (not stubs in the plan-02 sense — they define future contracts, not broken current behavior)

## Threat Flags

No new security surface beyond what was planned:
- T-06-04 mitigated: all splits access uses `.get()` with defaults; guard on <4 HR values; function never raises
- T-06-05 mitigated: failure_type comes from closed set ('muscular'/'cardiovascular'/'mixed'/None->'insufficient_data'); CHECK constraint on DB (migration plan 01)
- T-06-06 accepted: no new external surface — classification stays in single-athlete DB with existing RLS
- T-06-SC: no new packages installed (statistics is stdlib)

## Self-Check: PASSED

- [x] `coach/analytics/readiness.py` contains `class FatigueResult`, `def classify_fatigue_type(`, `def _compute_hr_drift(`, `def _compute_pace_drop(`
- [x] `coach/analytics/readiness.py` contains NO import of llm_client/anthropic/google
- [x] `coach/coaching/post_session_analysis.py` contains `from coach.analytics.readiness import classify_fatigue_type`
- [x] `coach/coaching/post_session_analysis.py` contains `"fatigue_type"`, `"fatigue_confidence"`, `"sport": sport`
- [x] Commit ab88dda exists (Task 1)
- [x] Commit 1deaab7 exists (Task 2)
- [x] 5 target tests GREEN
- [x] 179 previously-passing tests still pass (no regressions)
