# Testing Patterns
_Last updated: 2026-06-05_ | _Focus: quality_

## Summary

The test suite covers only the Python `coach/` layer — there are no automated tests for the TypeScript Cloudflare Workers. Tests live in `tests/` and run with pytest. The suite has six test files targeting analytics core, budget logic, fitness test processing, and regression guards. External dependencies (Supabase, Telegram, Garmin) are always stubbed out using `sys.modules` injection or `unittest.mock.patch`.

---

## Test Framework

**Runner:** pytest 7.4+
**Config:** `pytest.ini` at repo root
```ini
[pytest]
testpaths = tests
```

**Assertion style:** Mix of pytest native asserts and `unittest.TestCase` subclasses (both are used).

**Run commands:**
```bash
PYTHONPATH=. pytest tests/ -v          # all tests (from Makefile: make test)
PYTHONPATH=. pytest tests/test_pmc.py -v   # single file
python -m pytest tests/ -v             # alternative invocation
```

Note: `PYTHONPATH=.` is required — the project has no `setup.py` or `pip install -e .`.

---

## Test File Organization

**Location:** All automated tests are in `tests/` (flat, no subdirectories in the automated suite).

**Manual tests:** `tests/manual/` contains markdown files describing manual curl-based integration tests (e.g., `tests/manual/test_force_sync.md`). These are not collected by pytest.

**Naming:**
```
tests/
├── test_audit_resilience.py   # Regression suite for 2026-06-01 audit
├── test_budget.py             # Budget cap + model selection logic
├── test_fitness_test.py       # FitnessTestProcessor — extractor, zones, idempotency
├── test_pmc.py                # PMC EWMA math — CTL/ATL/TSB validation
├── test_readiness.py          # Readiness scorer + deterministic flags
├── test_regressions.py        # Bug regression registry (one test per fixed bug)
└── test_telegram_advanced.py  # Telegram bot parser logic (Python reimplementation)
```

---

## Test Types

**Unit tests (pure functions):**
`tests/test_pmc.py` and `tests/test_readiness.py` test pure Python functions with no external dependencies. Inputs are constructed inline; no mocking needed.

**Regression tests:**
`tests/test_regressions.py` — each test class corresponds to one fixed bug, tagged with commit hash and date in a structured comment header. Uses `importlib.util` to load modules after stubbing `sys.modules`.

**Feature tests (with mocking):**
`tests/test_budget.py` and `tests/test_fitness_test.py` — test classes with `@patch` decorators or `MagicMock` injection. Cover state machines, error paths, and side effects (Supabase writes, Telegram alerts).

**Audit resilience tests:**
`tests/test_audit_resilience.py` — cross-cutting tests referencing IDs in `docs/audit_resilience_2026-06-01.md`. Uses a custom `_FakeQuery` class to simulate the Supabase fluent chain.

**Integration tests (skipped in CI):**
`tests/test_telegram_advanced.py` marks some tests `@pytest.mark.integration`. These require live credentials and are skipped automatically in CI.

---

## Mocking Patterns

### Pattern 1 — `sys.modules` stub injection (most common)

Used when the module under test imports from `coach.utils.*` which requires live credentials at import time.

```python
import sys, types

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = None
    return mod

for _n in ["coach", "coach.utils", "coach.utils.supabase_client", ...]:
    if _n not in sys.modules:
        sys.modules[_n] = _stub(_n)

sys.modules["coach.utils.supabase_client"].get_supabase = MagicMock(return_value=MagicMock())
```

Then the module under test is loaded via `importlib.util`:
```python
def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

pmc = _load("coach.analytics.pmc", "coach/analytics/pmc.py")
```

### Pattern 2 — `unittest.mock.patch` (for side effects)

Used in `tests/test_budget.py` to mock `get_month_spend_usd` (Supabase call) and `_send_budget_alert` (Telegram call):
```python
@patch("coach.utils.budget.get_month_spend_usd")
@patch("coach.utils.budget._send_budget_alert")
def test_degraded_level(self, mock_alert, mock_spend):
    mock_spend.return_value = 3.95
    level = check_budget_or_raise(0.10, "session_analysis")
    assert level == "DEGRADED"
    mock_alert.assert_called_once()
```

### Pattern 3 — `_FakeQuery` (fluent Supabase chain)

Used in `tests/test_audit_resilience.py` when the code under test makes chained Supabase calls (`.table().select().gte().lte().execute()`). A hand-written fake implements the full chain:
```python
class _FakeQuery:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self
    def execute(self): return MagicMock(data=self._rows)
```

### Pattern 4 — Factory helpers

Used in `tests/test_readiness.py` to create test fixtures with sensible defaults:
```python
def make_default_subj(**kw) -> SubjectiveState:
    base = dict(motivation=7, soreness=2, illness_flag=False, injury_flag=False, illness_recent_days=0)
    base.update(kw)
    return SubjectiveState(**base)
```

---

## What Is Tested

| Module | Test file | Coverage focus |
|--------|-----------|----------------|
| `coach/analytics/pmc.py` | `test_pmc.py`, `test_regressions.py` | EWMA math, edge cases, ISO string parsing |
| `coach/analytics/readiness.py` | `test_readiness.py`, `test_regressions.py` | Flag logic, score bounds, TSB=None guard |
| `coach/utils/budget.py` | `test_budget.py` | All 5 budget levels, model downgrade, emergency bypass |
| `coach/coaching/fitness_test_processor.py` | `test_fitness_test.py` | Zone calculators, activity matching, CLAUDE.md update |
| `coach/planning/briefing.py` | `test_audit_resilience.py` | Message freshness, idempotency checks |
| Telegram bot parser | `test_telegram_advanced.py` | Command parsing (Python reimplementation) |

---

## CI Integration

Tests run in GitHub Actions as part of the `ingest` workflow (`.github/workflows/ingest.yml`) on every scheduled trigger and `workflow_dispatch`. The CI environment sets secrets via `env:` block. Tests that require live credentials are skipped via `@pytest.mark.integration` (no credentials → automatic skip, not fail).

No dedicated test-only workflow exists — tests are a gate within the ingest workflow job.

---

## Test Coverage Gaps

**TypeScript workers — no tests:**
`workers/telegram-bot/src/index.ts` and `workers/mcp-server/src/` have no automated tests. The Telegram bot parser logic was partially reimplemented in Python in `tests/test_telegram_advanced.py` as a workaround. The TypeScript implementation itself is untested.

**Ingest pipeline (`coach/ingest/garmin.py`, `coach/ingest/strava.py`) — no unit tests:**
These modules are tested only via manual smoke tests (`tests/manual/`) or end-to-end CI runs. No mocked unit tests exist for the Garmin/Strava transformation logic.

**Planning layer (`coach/planning/briefing.py`, `coach/planning/briefing_v1.py`) — partial:**
Only `test_audit_resilience.py` covers briefing idempotency. The briefing content generation and DB query logic are not tested.

**Coaching modules — no tests:**
`coach/coaching/adaptive_planner.py`, `coach/coaching/modulation.py`, `coach/coaching/post_session_analysis.py`, `coach/coaching/weekly_analysis.py` — no test files exist for these.

**`coach/cognition/` — empty stubs:**
The `inference/`, `prediction/`, `prescription/` packages contain only `__init__.py` files. Nothing to test yet.

**Validators (`coach/utils/validators.py`) — no dedicated test:**
`validate_activity` and `validate_wellness` have no test file. Correctness is implicitly relied upon by the ingest pipeline.

---

## Gaps & Unknowns

- No coverage measurement is configured (no `pytest-cov`, no `.coveragerc`). Coverage percentage is unknown.
- No `conftest.py` exists — shared fixtures are implemented as module-level helper functions in each test file.
- The `@pytest.mark.integration` marker is used in `test_telegram_advanced.py` but not registered in `pytest.ini` — this may generate pytest warnings.
- No performance/benchmark tests exist.
