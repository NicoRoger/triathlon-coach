# Phase 1: Test Suite & Analytics Correctness - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 2 (1 new, 1 modified)
**Analogs found:** 2 / 2

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/verify_analytics.py` | utility (operational script) | request-response (DB read → stdout) | `scripts/smoke_test.py` | role-match |
| `tests/test_audit_resilience.py` (add test method) | test | CRUD (fake DB → assert) | `tests/test_audit_resilience.py` lines 193-205 (test_b3_missing_pmc_does_not_score_tsb_optimal) | exact |

---

## Pattern Assignments

### `scripts/verify_analytics.py` (utility, request-response)

**Analog:** `scripts/smoke_test.py` + `scripts/backfill_metrics.py`

**Imports pattern** (`scripts/smoke_test.py` lines 1-10, `scripts/backfill_metrics.py` lines 1-5):
```python
"""Docstring describing purpose."""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()  # MUST be called before any coach.* import that calls get_supabase()

from coach.utils.supabase_client import get_supabase
from coach.utils.dt import today_rome, to_rome_date
```

**Critical ordering constraint** (RESEARCH.md Anti-Patterns):
`load_dotenv()` must be called at module level (or first line of `main()`), before any `coach.*` import. `get_supabase()` is decorated with `@lru_cache(maxsize=1)` — if called without env vars it raises `KeyError` and the cache preserves the error state for the process lifetime.

**Core pattern** (`scripts/smoke_test.py` lines 110-128):
```python
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()
    # ... query DB and print sections ...

if __name__ == "__main__":
    sys.exit(main())  # or: main() with no exit code (informational script)
```

**DB query pattern** (`scripts/smoke_test.py` lines 34-47):
```python
from coach.utils.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("daily_metrics") \
    .select("date,ctl,atl,tsb,readiness_score,readiness_label,flags") \
    .eq("date", today_iso) \
    .execute()
row = res.data[0] if res.data else None
```

**Output format** (D-03 in CONTEXT.md — exact template):
```
=== HRV Analytics ===
Baseline 28d: media=67.3ms, SD=8.1ms (29 giorni, oggi escluso)
Z-score oggi: -0.4σ → OK
Flag: nessuno

=== PMC ===
CTL: 42.1 | ATL: 38.7 | TSB: +3.4

=== Readiness ===
Score: 74/100 | Label: caution

=== Risk: Volume Bucketing (settimana corrente) ===
swim: 2800m | bike: 145km | run: 18.5km (date: Europe/Rome)
```

**Security constraint** (RESEARCH.md Security Domain): Never log `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` to stdout. Print only analytics values.

**No exit 1** (D-02): script is informational only — no `sys.exit(1)` on anomalous values. The operator reads the output and decides.

---

### `tests/test_audit_resilience.py` — add `test_b3_readiness_label_not_null` (test, CRUD)

**Analog:** `tests/test_audit_resilience.py` lines 193-205 (`test_b3_missing_pmc_does_not_score_tsb_optimal`)

**Infrastructure to reuse** (`tests/test_audit_resilience.py` lines 72-103):
```python
# _FakeSupabase: dict-backed fake, captures last upsert to daily_metrics
class _FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables
        self.last_upsert: dict | None = None

    def table(self, name):
        q = _FakeQuery(list(self._tables.get(name, [])))
        if name == "daily_metrics":
            orig = q.upsert
            def _capture(data, **k):
                self.last_upsert = data
                return orig(data, **k)
            q.upsert = _capture
        return q

def _make_daily_module(supabase: _FakeSupabase):
    """Loads daily.py with real pmc/readiness deps and fake supabase."""
    _load("coach.analytics.pmc", "coach/analytics/pmc.py")
    _load("coach.analytics.readiness", "coach/analytics/readiness.py")
    for n in ["coach.utils.supabase_client", "coach.utils.health"]:
        m = types.ModuleType(n)
        sys.modules[n] = m
    sys.modules["coach.utils.supabase_client"].get_supabase = lambda: supabase
    sys.modules["coach.utils.health"].record_health = lambda *a, **k: None
    return _load("coach.analytics.daily", "coach/analytics/daily.py")
```

**Closest existing test** (`tests/test_audit_resilience.py` lines 193-205):
```python
def test_b3_missing_pmc_does_not_score_tsb_optimal():
    day = date(2026, 5, 30)
    wellness = [{"date": day.isoformat(), "hrv_rmssd": 55.0, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50}]
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["ctl"] is None and m["tsb"] is None
    assert m["readiness_factors"]["tsb"] == 50
```

**New test to add** — place immediately after `test_b3_missing_pmc_does_not_score_tsb_optimal` (RESEARCH.md Code Examples §3, D-06):
```python
def test_b3_readiness_label_not_null():
    """ANALYTICS-04: compute_for must write readiness_label non-null and
    readiness_score 0-100 even when PMC is absent (no activities)."""
    day = date(2026, 5, 30)
    wellness = [{"date": day.isoformat(), "hrv_rmssd": 55.0, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50}]
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["ctl"] is None  # PMC absent (no activities)
    assert m["readiness_label"] in {"ready", "caution", "rest"}, (
        f"readiness_label must be non-null string, got: {m['readiness_label']!r}"
    )
    assert isinstance(m["readiness_score"], int), (
        f"readiness_score must be int, got: {type(m['readiness_score'])}"
    )
    assert 0 <= m["readiness_score"] <= 100, (
        f"readiness_score must be 0-100, got: {m['readiness_score']}"
    )
```

**Key constraint**: use `activities: []` (empty list) to force the None-PMC path. Adding activities would produce a valid PMC and not exercise the None-handling. (RESEARCH.md Pitfall 4)

---

## Shared Patterns

### Supabase client access
**Source:** `coach/utils/supabase_client.py` — `get_supabase()` with `@lru_cache(maxsize=1)`
**Apply to:** `scripts/verify_analytics.py`
**Rule:** Always call `load_dotenv()` before first use. In scripts, place it at module level after stdlib imports, before any `coach.*` imports.

### sys.modules injection for test isolation
**Source:** `tests/test_audit_resilience.py` lines 91-103 (`_make_daily_module`)
**Apply to:** New test method `test_b3_readiness_label_not_null`
**Rule:** Never import `coach.analytics.daily` directly in tests. Use `_make_daily_module(sb)` which injects the fake via `sys.modules["coach.utils.supabase_client"].get_supabase = lambda: sb`. Call `_make_daily_module(sb)` fresh for each test — do not reuse across tests.

### Error handling in scripts
**Source:** `scripts/backfill_metrics.py` lines 30-33
```python
try:
    compute_for(cur)
except Exception as e:
    print(f"  FAIL {cur}: {e}")
```
**Apply to:** `scripts/verify_analytics.py` — wrap each section query in try/except so a missing table or None row in one section doesn't crash the remaining sections.

---

## No Analog Found

None. Both deliverables have strong analogs in the codebase.

---

## Metadata

**Analog search scope:** `scripts/`, `tests/`
**Files scanned:** `scripts/smoke_test.py`, `scripts/backfill_metrics.py`, `tests/test_audit_resilience.py` (lines 1-240)
**Pattern extraction date:** 2026-06-05
