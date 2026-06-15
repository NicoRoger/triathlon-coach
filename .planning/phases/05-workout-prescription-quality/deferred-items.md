# Deferred Items — Phase 05

## Pre-existing test isolation failure (out of scope)

**Found during:** Plan 05-04 Task 2 execution  
**File:** `tests/test_live_behavior.py::test_verify04_session_analysis_routes_to_gemini`  
**Issue:** `test_fitness_test.py` stubs `coach.utils` as a plain `types.ModuleType` (module-level code). When the full suite runs in alphabetical order, `test_fitness_test` executes before `test_live_behavior`. The stub `coach.utils` in `sys.modules` is not a real Python package, so subsequent `from coach.utils.llm_client import ...` in `test_live_behavior` fails with `'coach.utils' is not a package`.

**Root cause:** `test_fitness_test.py` lines 26-33 register stubs for `"coach"` and `"coach.utils"` in `sys.modules`. These stubs persist for the duration of the test session.

**Fix:** `test_fitness_test.py` should use `importlib` isolation or `unittest.mock.patch` for `sys.modules` entries instead of polluting the global `sys.modules` dict. The test `test_verify04_session_analysis_routes_to_gemini` should either use `_load()` pattern or ensure `test_fitness_test.py` cleans up its stubs via autouse fixture.

**Impact:** 1 test failure in full suite run. Test passes when run in isolation.

**Pre-existing on:** `22b91a2` (base of Phase 5) — confirmed by running `python -m pytest tests/ -q` on main branch.

**Suggested fix:** Add cleanup in `test_fitness_test.py` to restore original `sys.modules` entries after tests run, or use `monkeypatch.setitem(sys.modules, ...)` pattern with pytest fixtures.
