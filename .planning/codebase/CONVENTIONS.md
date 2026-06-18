# Coding Conventions
_Last updated: 2026-06-05_ | _Focus: quality_

## Summary

The Python codebase (`coach/`) follows a consistent style: `from __future__ import annotations` on every module, `logging.getLogger(__name__)` for all logging, and `dataclasses` + Pydantic for data types. TypeScript is used exclusively in Cloudflare Workers (`workers/`) and follows a simple interface-first style with no test suite. No linter config files (`.flake8`, `pyproject.toml`, `setup.cfg`) are present — conventions are enforced by review and by `noqa: BLE001` suppression comments on broad except clauses.

---

## Language Conventions

### Python (`coach/`, `scripts/`)

**Module header (every file):**
```python
"""One-line summary — detail on second line if needed.

Optional philosophy/design note.
"""
from __future__ import annotations
```
All Python source files use `from __future__ import annotations`. This is the only consistent import.

**Imports order (observed):**
1. `from __future__ import annotations`
2. Standard library (alphabetical)
3. Third-party (`pydantic`, `supabase`, etc.)
4. Internal (`coach.*`) — relative imports are NOT used; all imports are absolute

**Type annotations:**
- All function signatures are annotated
- `Optional[X]` preferred over `X | None` (pre-3.10 compat via `__future__`)
- `# type: ignore` used sparingly (2–3 occurrences in `coach/coaching/pattern_extraction.py` and `coach/ingest/garmin.py`)

### TypeScript (`workers/`)

**Style:**
- Interface-first: domain types declared as `interface` at top of file
- No type aliases for simple types
- Arrow functions for handlers, named functions for utilities
- JSDoc block comments on exported functions/classes

---

## Naming Conventions

**Python:**
- Files: `snake_case.py` (e.g., `fitness_test_processor.py`, `belief_engine.py`)
- Functions: `snake_case` — private helpers prefixed with `_` (e.g., `_score_tsb`, `_fetch_activities_window`)
- Classes: `PascalCase` (e.g., `WellnessHistory`, `TrainingState`, `FitnessTestProcessor`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `HRV_WARNING_Z`, `CTL_TIME_CONSTANT`, `BUDGET_BLOCKED`)
- Dataclasses: used for pure-data value objects (e.g., `DailyTSS`, `PMCPoint`, `ReadinessReport`)
- Pydantic models: used for DB-bound schemas in `coach/models/schemas.py`

**TypeScript (`workers/`):**
- Files: `index.ts` (single entry point per worker)
- Interfaces: `PascalCase` with `I`-prefix absent
- Handler functions: `handle<Command>` pattern (e.g., `handleBrief`, `handleLog`)

---

## Code Organization Patterns

**Module-level logger (Python):**
Every `coach/` module declares a logger immediately after imports:
```python
logger = logging.getLogger(__name__)
```
Script entry points (`if __name__ == "__main__":`) call `logging.basicConfig` locally:
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
```

**Dataclass for value objects, Pydantic for DB models:**
- `@dataclass` (sometimes `frozen=True`) for pure computation types: `coach/analytics/pmc.py`, `coach/analytics/readiness.py`
- `pydantic.BaseModel` (via `BaseDBModel`) for DB mirror types: `coach/models/schemas.py`

**Constants at module top:**
Domain thresholds and configuration constants are declared at the top of each module, before any function definitions. Example from `coach/analytics/readiness.py`:
```python
HRV_WARNING_Z = -1.0
HRV_CRITICAL_Z = -2.0
HRV_WARNING_CONSECUTIVE_DAYS = 2
TSB_DEEP_NEGATIVE = -25.0
```

**Pure/deterministic modules explicitly documented:**
Modules that contain no LLM calls or side effects note this in their docstring:
> "Modulo deterministico, testabile, mai chiamato dall'LLM."

This pattern appears in `coach/analytics/pmc.py`, `coach/analytics/readiness.py`, and `coach/utils/validators.py`.

**`if __name__ == "__main__":` entry points:**
Most `coach/` modules include a runnable entry point with `logging.basicConfig`. This doubles as a smoke-test for developers.

---

## Error Handling Patterns

**Validation errors (domain logic):** Raise `ValueError` with descriptive message:
```python
raise ValueError("FTP must be positive")
```
Used in `coach/analytics/pmc.py` for invalid inputs to TSS estimators.

**Infrastructure errors (ingest, networking):** Broad `except Exception` with `# noqa: BLE001` suppression, logged via `logger.exception` or `logger.warning`, then either re-raised or silently continued depending on criticality:
```python
except Exception as e:  # noqa: BLE001
    logger.exception("Analytics daily failed")
    raise
```
vs.
```python
except Exception as exc:  # noqa: BLE001
    logger.warning("Garmin endpoint failed: %s", exc)
```

**Budget errors:** Custom exception `BudgetExceededError` in `coach/utils/budget.py`, raised explicitly and caught at call sites.

**Null/None safety:** The `or 0` pattern (not `.get(key, 0)`) is the preferred idiom when a dict value can be `None` while the key exists:
```python
int(activity.get("duration_s") or 0)  # correct
activity.get("duration_s", 0)         # BUG: doesn't protect against value=None
```
This is codified in `tests/test_regressions.py`.

**Empty list vs None:** Prefer `is None` checks over truthiness when an empty list is a valid value:
```python
result = data.get("lapDTOs")
if result is None:
    result = data.get("splits")
```
Also codified in `tests/test_regressions.py`.

---

## Logging Conventions

**Logger declaration:** `logger = logging.getLogger(__name__)` in every module.

**Log levels used:**
- `logger.info(...)` — normal operational events (sync completed, record upserted)
- `logger.warning(...)` — non-fatal anomalies (Garmin endpoint unavailable, validation warning)
- `logger.exception(...)` — unexpected exceptions (logs traceback automatically)

**Format (entry points):** `"%(asctime)s %(levelname)s %(message)s"`

**Telegram as secondary log channel:** `coach/utils/telegram_logger.py` provides `send_and_log_message()` for user-visible alerts (budget warnings, critical flags). This is NOT a replacement for `logging` — both are used.

---

## Comment and Documentation Style

**Module docstrings:** Every `coach/` module has a multi-line docstring explaining purpose, design philosophy, and cross-references to related files or CLAUDE.md sections.

**Inline comments:** Used to explain non-obvious logic, cite methodology references, and document bug fixes:
```python
# Bug fix audit A5: precedenza operatori. Prima era
#   `... np_w > max_power if max_power else False` → parsato come ...
```

**Regression fix headers in tests:** Each regression test block is prefixed with a structured comment:
```python
# ===========================================================================
# FIX: <short description>
# Commit: <hash> (<date>)
# Bug: <what happened>
# ===========================================================================
```

**Reference citations:** Core analytics modules cite academic/methodological references:
```python
# Coggan, "Training and Racing with a Power Meter" (TSS/IF/CTL/ATL)
# Friel, "Triathlete's Training Bible"
```

---

## Formatting

No formatter config files detected (no `.flake8`, `pyproject.toml`, `setup.cfg`, `biome.json`). Observed style:
- 4-space indentation (Python)
- Line length: not enforced mechanically; long lines appear in docstrings and SQL strings
- Trailing commas in multi-line function calls and dict literals (common but not universal)
- Section dividers in larger files: `# ============================================================================`

---

## Gaps & Unknowns

- No linter or formatter is configured (no `ruff`, `black`, `isort`, `flake8` config found). Conventions are informal and enforced only by code review.
- TypeScript workers (`workers/telegram-bot/src/index.ts`, `workers/mcp-server/src/`) have no linting config and no automated test coverage.
- No `mypy` or `pyright` config found; type checking is not enforced in CI.
- The `coach/cognition/` package (`inference/`, `prediction/`, `prescription/`) contains only `__init__.py` files — these are stubs with no implementation.
