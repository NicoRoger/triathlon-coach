# CONCERNS
_Last updated: 2026-06-05_ | _Focus: concerns_

## Summary

The codebase is a single-athlete coaching system with a well-structured Python backend, a Cloudflare Worker MCP server, and GitHub Actions for automation. It shows evidence of active maintenance (a dedicated resilience audit branch with 100 tests), but carries a few high-severity reliability gaps — notably a trivially-bypassable MCP auth layer and unclean temporary-file handling — along with medium debt in the form of broad exception swallowing across ingest pipelines and an oversized `briefing.py` god-module. No hardcoded secrets were found; the observability posture is basic but functional for a single-user system.

---

## High Severity

### H1 — MCP server auth bypass
- **Severity:** HIGH
- **Location:** `workers/mcp-server/src/index.ts` lines 356–362
- **Description:** The auth guard accepts unauthenticated requests if the `Authorization` header is simply missing (`const isOAuthRequest = !auth`). Any anonymous HTTP POST to the `/` or `/mcp` path with no `Authorization` header is allowed through, granting read access to athlete health data and the ability to propose plan changes. The OAuth `/token` endpoint (line 319–326) also returns the real bearer token unconditionally without any authorization code verification.
- **Fix direction:** Require a validated OAuth state/code before issuing the token. Replace the `isOAuthRequest = !auth` bypass with session-cookie or signed-state validation. Until then, restrict Cloudflare Worker origin to Claude.ai IPs or add a Cloudflare Access rule.

### H2 — Garmin OAuth tokens written to unclean temp dir
- **Severity:** HIGH
- **Location:** `coach/ingest/garmin.py` lines 64–75 (`_restore_garmin_session`)
- **Description:** `tempfile.mkdtemp` creates a directory containing decoded OAuth1/OAuth2 token files. The directory is never deleted (no `shutil.rmtree`, no `try/finally`, no `atexit`). On ephemeral GitHub Actions runners this is inconsequential, but the path is also written into `os.environ["GARMINTOKENS"]`, making it visible to any child process for the life of the run. More critically, if the function is ever called from a long-lived process or local dev environment, token files accumulate on disk indefinitely.
- **Fix direction:** Wrap `_restore_garmin_session` in a `try/finally` that calls `shutil.rmtree(tokendir, ignore_errors=True)`, or use `tempfile.TemporaryDirectory` as a context manager and rework the caller to not need the path after login.

### H3 — Strava `while True` pagination without page cap
- **Severity:** HIGH
- **Location:** `coach/ingest/strava.py` lines 105–121
- **Description:** The activity fetch loop has no maximum page guard. If the Strava API returns a malformed response or a pagination bug causes an infinite sequence of non-empty batches, the job runs until GitHub Actions timeout (15 min), consuming tokens and potentially writing duplicate data.
- **Fix direction:** Add `if page > MAX_PAGES: logger.error(...); break` with `MAX_PAGES = 50` (or similar). Already exists safely on the Garmin side via `range(days_back, -1, -1)`.

---

## Medium Severity

### M1 — Broad exception swallowing throughout ingest pipeline
- **Severity:** MEDIUM
- **Location:** `coach/ingest/garmin.py` (lines 415, 438, 444, 450, 457, 499, 512), `coach/ingest/strava.py` (line 119, 132), `coach/planning/briefing.py` (lines 268, 367, 428, 514, 550, 590, 637, 720)
- **Description:** Over 15 `except Exception` / bare `except` handlers across the ingest and briefing paths log and continue silently. While per-activity isolation is intentional, some of these catch blocks swallow errors at the entire-day or entire-function level without incrementing a failure counter or setting a health flag. A persistent upstream API breakage can be invisible until the watchdog fires after 8h.
- **Fix direction:** Track per-run failure counts and surface them in `record_health` metadata. Consider re-raising after N consecutive failures so the CI step shows red. The existing `# noqa: BLE001` markers show awareness of the pattern — enforce a project rule that blind-except blocks must always call `record_health(..., success=False)`.

### M2 — `briefing.py` is a 726-line god module
- **Severity:** MEDIUM
- **Location:** `coach/planning/briefing.py`
- **Description:** The file contains 27 functions spanning DB queries, rule-based interpretation, Telegram delivery, and race-section rendering. It has no clear internal boundary between data-fetching and rendering, making sections hard to test in isolation. There is also a `briefing_v1.py` file that is no longer imported anywhere (dead code).
- **Fix direction:** Extract Telegram delivery into `coach/utils/telegram_logger.py` (partially done) and split rendering sections into a `coach/planning/sections/` sub-package. Delete `briefing_v1.py`.

### M3 — No rate-limit or retry handling on LLM calls
- **Severity:** MEDIUM
- **Location:** `coach/utils/llm_client.py` (all `call` methods)
- **Description:** Anthropic and Gemini calls have no retry with exponential backoff for transient errors (429, 503). A single Gemini rate-limit during `post_session_analysis` raises, falls back to Anthropic Haiku (correctly), but this doubles cost unexpectedly and is not reflected in the budget cap logic. The Anthropic client similarly raises immediately on any API error.
- **Fix direction:** Add a `tenacity`-based retry decorator (max 3 attempts, exponential backoff) for status 429/503 before triggering the provider fallback path.

### M4 — CORS wildcard on MCP server
- **Severity:** MEDIUM
- **Location:** `workers/mcp-server/src/index.ts` line 37
- **Description:** `Access-Control-Allow-Origin: *` is set globally, including on the `/dashboard-data` endpoint which returns athlete health data. Combined with the auth bypass in H1, any browser page can make unauthenticated cross-origin requests to the dashboard endpoint if the auth header is absent.
- **Fix direction:** Restrict to `https://claude.ai` and the dashboard origin once the auth bypass (H1) is fixed.

### M5 — `physiology_zones` UNIQUE constraint added retroactively, not in baseline schema
- **Severity:** MEDIUM
- **Location:** `migrations/2026-06-01-resilience-audit.sql`, `sql/schema.sql`
- **Description:** The migration comment explicitly notes: "la tabella è vuota finché non si esegue il primo test → nessun conflitto". The constraint was missing from `schema.sql` and only added in the resilience migration. `fitness_test_processor.py` would silently fail the `upsert on_conflict="discipline,valid_from"` at the first real test run because the target columns had no unique index. This is a latent bug for any fresh DB setup from `schema.sql` alone.
- **Fix direction:** Add the constraint to `sql/schema.sql` so fresh setups are consistent with migrated ones. Add a smoke test that runs `fitness_test_processor` against a stub DB with the constraint absent to catch regressions.

### M6 — Budget pricing table hardcoded and manually maintained
- **Severity:** MEDIUM
- **Location:** `coach/utils/budget.py` line 25 ("Pricing table — Anthropic maggio 2026")
- **Description:** Model pricing is hardcoded in a dict. When Anthropic adjusts pricing or adds new model tiers, the cost estimates silently become wrong, causing under- or over-counting against the €5/month hard cap. Gemini calls are always logged as `cost_usd=0.0` even though Gemini Flash exceeds the free tier after 15 RPM.
- **Fix direction:** Add a `PRICING_LAST_UPDATED` constant and a startup warning if it is older than 90 days. Log a note in the Gemini client when monthly Gemini token count approaches free-tier limits.

---

## Low Severity

### L1 — `briefing_v1.py` is dead code
- **Severity:** LOW
- **Location:** `coach/planning/briefing_v1.py` (175 lines)
- **Description:** No import of `briefing_v1` exists anywhere in the codebase. It duplicates Telegram delivery logic now handled by `telegram_logger.py`.
- **Fix direction:** Delete the file.

### L2 — `coach/cognition/` sub-packages are empty shells
- **Severity:** LOW
- **Location:** `coach/cognition/inference/__init__.py`, `coach/cognition/prescription/__init__.py`
- **Description:** Both are empty `__init__.py` files. `coach/cognition/prediction/__init__.py` re-exports from `coach/coaching/` modules. The `cognition` layer has no implementation of its own, making the package hierarchy misleading.
- **Fix direction:** Either populate the layer with actual abstractions or flatten back to `coach/coaching/` and remove the empty directories to reduce cognitive overhead.

### L3 — `get_analysis_client()` marked DEPRECATED but still present
- **Severity:** LOW
- **Location:** `coach/utils/llm_client.py` lines 284–292
- **Description:** The function is marked "DEPRECATED — usa get_client_for_purpose" but not yet removed and could be called by external scripts.
- **Fix direction:** Grep for callers, remove them, then delete the function.

### L4 — `daily.py` has a `TODO` for `sleep_avg_7d`
- **Severity:** LOW
- **Location:** `coach/analytics/daily.py` line 123 (`sleep_avg_7d=None, # TODO se serve`)
- **Description:** The field is always `None` in the readiness calculation. The `_score_sleep` function falls back to `sleep_score_today` anyway, so this is not currently breaking, but the missing 7-day average reduces the smoothing that would catch data outliers.
- **Fix direction:** Compute the rolling 7d sleep score average from `daily_wellness` and pass it through.

### L5 — `outcome_verification.py` calls `sb.rpc("execute_sql", ...)` as primary path
- **Severity:** LOW
- **Location:** `coach/coaching/outcome_verification.py` line 318
- **Description:** The primary query for `prediction_accuracy` is via a raw `execute_sql` RPC, which requires a custom Postgres function to exist. The fallback queries the view directly. If the RPC does not exist, the error is silently swallowed and beliefs are not updated — which is the expected path today since no RPC is defined in `schema.sql`.
- **Fix direction:** Make the PostgREST view query the primary path and remove the RPC call, or define the RPC in `schema.sql`.

### L6 — No structured logging / no metrics beyond api_usage table
- **Severity:** LOW
- **Location:** All `coach/` modules
- **Description:** All logging is `logging.basicConfig` text-format to stdout. There is no structured JSON logging, no request-ID propagation across the ingest pipeline, and no metrics other than the `api_usage` DB table. Debugging multi-step failures (ingest → analytics → briefing) requires correlating timestamps across three separate GitHub Actions log streams.
- **Fix direction:** Add a `run_id = uuid4()` at the start of each workflow entrypoint and include it in all log records via a `logging.Filter`. Consider switching to `structlog` for JSON output compatible with GitHub Actions annotations.

---

## Gaps & Unknowns

- **Supabase RLS (Row Level Security):** The service key bypasses RLS by design, but it is unknown whether RLS policies exist on sensitive tables (`subjective_log`, `daily_wellness`). If the anon key is ever used (fallback in `supabase_client.py` line 20), data exposure depends on RLS being correctly configured. Not verifiable from code alone.
- **Garmin session expiry:** The `python-garminconnect` library uses OAuth tokens restored from an env var. Token refresh behavior on expiry is not documented in the codebase; a silent expiry would cause `sync_wellness` to return 0 records without a clear error.
- **MCP server deployment state:** The `dist/` directory in `dashboard/` is committed; it is unclear whether the Cloudflare Worker `wrangler.toml` points to the correct entry point and whether the deploy is automated or manual.
- **Test coverage of `briefing.py`:** The `test_audit_resilience.py` suite tests many individual analytics functions, but there are no tests for the full `build_brief()` or `send_to_telegram()` paths. Regressions in section rendering are only caught in production.
