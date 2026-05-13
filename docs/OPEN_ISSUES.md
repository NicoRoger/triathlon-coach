# Open Issues & Testing Checklist

Bugs found during initial rollout. Each entry has status, fix applied, and what to verify next time the area is touched.

---

## Fixed — Needs regression test

### BUG-001 — `/dashboard-data` route unreachable (404)
- **Symptom**: Login on dashboard always failed; bearer token rejected even when correct
- **Root cause**: The `if (!isMcpPath) → 404` guard in `workers/mcp-server/src/index.ts` fired before the `/dashboard-data` handler, making it unreachable
- **Fix**: Moved `/dashboard-data` block above the `isMcpPath` check (commit `160ac43`)
- **Test**: After any MCP worker deploy, `curl -H "Authorization: Bearer <TOKEN>" https://mcp-server.nicorugg.workers.dev/dashboard-data` must return JSON, not 404

---

### BUG-002 — `subjective_log` rejects `proactive_response`, `brief_response`, `video_analysis`
- **Symptom**: Telegram bot error `23514 check constraint subjective_log_kind_check` when saving proactive check-in replies or brief responses
- **Root cause**: The DB CHECK constraint on `subjective_log.kind` only included 6 values; the bot was inserting 3 kinds not in the list
- **Fix**: Migration `2026-05-13-subjective-log-kinds.sql` + `sql/schema.sql` updated
- **Migration to run**: `migrations/2026-05-13-subjective-log-kinds.sql`
- **Test**: Reply to a proactive check-in on Telegram → no error, message saved; reply to morning brief → saved as `brief_response`; send video → saved as `video_analysis`

---

### BUG-003 — `get_weekly_context` missing race data
- **Symptom**: Claude.ai weekly review and mesocycle planning said "non ho una gara target" even though the `races` table is populated
- **Root cause**: `getWeeklyContext()` in `workers/mcp-server/src/index.ts` ran 10 parallel Supabase queries but never queried the `races` table; it was only queried in `getDashboardData()`
- **Fix**: Added `races?race_date=gte.${today}` query to `getWeeklyContext`, exposed as `upcoming_races` in response (commit `12b1782`)
- **Test**: Call `get_weekly_context` via Claude.ai → response JSON must include `upcoming_races` with Lavarone entry; weekly review must reference the race date automatically

---

### BUG-004 — Wrong Lavarone race date in seed
- **Symptom**: Race date was `2026-09-06` in the seed migration, actual date is `2026-08-29`
- **Source**: Confirmed on lavaronetriathlon.com
- **Fix**: `migrations/2026-05-13-fix-lavarone-date.sql` + seed file corrected
- **Migration to run**: `migrations/2026-05-13-fix-lavarone-date.sql`
- **Test**: `SELECT race_date FROM races WHERE name = 'Lavarone Cross Sprint'` → `2026-08-29`

---

### BUG-005 — Gemini 2.0 Flash has free-tier quota = 0
- **Symptom**: `GeminiClient` raised `429 RESOURCE_EXHAUSTED` with `limit: 0` on `gemini-2.0-flash`
- **Root cause**: The Google Cloud project associated with the API key does not have free-tier quota allocated for `gemini-2.0-flash`; only newer models (`gemini-2.5-flash`) are available
- **Fix**: Changed `GeminiClient.MODEL` to `gemini-2.5-flash`; also switched from deprecated `google-generativeai` to `google-genai` SDK
- **Test**: Set `GEMINI_API_KEY` and run `python -m coach.coaching.post_session_analysis --recent --days 1` → analysis saved in `session_analyses`, model logged as `gemini-2.5-flash`

---

## Known limitations — Not bugs

### LIMIT-001 — `get_physiology_zones` "not loaded yet" in Claude.ai
- **Symptom**: Claude.ai shows error `'triathlon-coach:get_physiology_zones' has not been loaded yet` on first call
- **Explanation**: Claude.ai lazy-loads MCP tool schemas. On first use in a session it needs an internal `tool_search` call to discover parameters. This resolves automatically — Claude retries after loading the schema.
- **Workaround if persistent**: Disconnect and reconnect the MCP connector in Claude.ai Settings → Connectors → triathlon-coach
- **Not fixable** in MCP server code

### LIMIT-002 — Goal Board empty without mesocycles
- **Symptom**: Excalidraw Goal Board in dashboard shows only the axis and no content
- **Explanation**: The board is generated from `mesocycles`, `races`, and `planned_sessions`. If `mesocycles` is empty, only race diamonds appear (if races are present).
- **Fix**: Run `/generate_mesocycle` in Claude.ai to populate the first training block

### LIMIT-003 — `physiology_zones` empty until first fitness test
- **Symptom**: Claude.ai reports no current zones; zone-based session proposals are generic
- **Explanation**: Zones auto-populate when `fitness_test_processor.py` detects an activity with a matching test name. First test planned: June 2026.
- **No action needed** until first test

---

## Pending migrations to run in Supabase

| Migration | Status | SQL |
|-----------|--------|-----|
| `2026-05-12-mesocycles-unique.sql` | ⏳ Pending | `ALTER TABLE mesocycles ADD CONSTRAINT mesocycles_start_date_unique UNIQUE (start_date)` |
| `2026-05-13-subjective-log-kinds.sql` | ⏳ Pending | DROP + recreate `subjective_log_kind_check` with all 9 kinds |
| `2026-05-11-seed-lavarone-race.sql` | ⏳ Pending | INSERT Lavarone race (date: 2026-08-29) |
| `2026-05-13-fix-lavarone-date.sql` | ⏳ Pending | UPDATE if race was already inserted with wrong date |
