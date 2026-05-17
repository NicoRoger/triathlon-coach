# Open Issues & Testing Checklist

Bugs found during initial rollout. Each entry has status, fix applied, and regression test.

**Status key**
- ✅ Fully resolved — code fix deployed, no further action needed
- ⚠️ Code fixed — DB migration still needs to be run in Supabase
- 📋 Limitation — by design or external dependency, not fixable in code

---

## BUG-001 — `session_analyses` table always empty ✅
- **Symptom**: Post-session AI analyses were never saved; table stayed empty for weeks
- **Root cause**: `ingest.yml` job env was missing `ANTHROPIC_API_KEY`. `LLMClient.__init__` raised `RuntimeError("ANTHROPIC_API_KEY not set")`, silently caught in the except clause, returning `None`
- **Fix**: Added `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` to `ingest.yml` job-level env
- **Test**: After a Garmin sync, check `session_analyses` table has a new row; `model_used` should be `gemini-2.5-flash` (after BUG-006 fix)

---

## BUG-002 — `plan_modulations` never triggered ✅
- **Symptom**: `plan_modulations` table always empty; mid-week auto-adjustments never proposed
- **Root cause**: `post_session_analysis.py` called the LLM and saved the result, but never called any function from `modulation.py`. The modulation module was fully implemented but completely unwired.
- **Fix**: Added `should_trigger_modulation()` + `generate_modulation_proposal()` + `propose_modulation()` call at the end of `analyze_session()` in `post_session_analysis.py`
- **Test**: After a session with HRV z-score < -1.5 or critical keywords in analysis, a row should appear in `plan_modulations` with `status='proposed'`; Telegram should show inline buttons ✅/❌

---

## BUG-003 — `/dashboard-data` route unreachable (404) ✅
- **Symptom**: Dashboard login always failed; bearer token rejected even when correct
- **Root cause**: The `if (!isMcpPath) → 404` guard in `workers/mcp-server/src/index.ts` fired before the `/dashboard-data` handler, making it unreachable
- **Fix**: Moved `/dashboard-data` block above the `isMcpPath` check (commit `160ac43`)
- **Test**: After any MCP worker deploy, `curl -H "Authorization: Bearer <TOKEN>" https://mcp-server.nicorugg.workers.dev/dashboard-data` must return JSON, not 404

---

## BUG-004 — `subjective_log` rejects `proactive_response`, `brief_response`, `video_analysis` ⚠️
- **Symptom**: Telegram bot error `23514 check constraint subjective_log_kind_check` when saving proactive check-in replies or brief responses
- **Root cause**: The DB CHECK constraint on `subjective_log.kind` only included 6 values; the bot was inserting 3 kinds not in the constraint list
- **Fix**: Migration `2026-05-13-subjective-log-kinds.sql` + `sql/schema.sql` updated
- **Migration to run**: `migrations/2026-05-13-subjective-log-kinds.sql`
- **Test**: Reply to a proactive check-in on Telegram → no error, message saved as `proactive_response`; swipe-reply to morning brief → saved as `brief_response`; send video → saved as `video_analysis`

---

## BUG-005 — `get_weekly_context` missing race data ✅
- **Symptom**: Claude.ai weekly review said "non ho una gara target" even though the `races` table is populated
- **Root cause**: `getWeeklyContext()` ran 10 parallel Supabase queries but never included the `races` table; races were only queried in `getDashboardData()`
- **Fix**: Added `races?race_date=gte.${today}` query to `getWeeklyContext`, exposed as `upcoming_races` (commit `12b1782`)
- **Test**: Call `get_weekly_context` via Claude.ai → response JSON includes `upcoming_races` with Lavarone entry; weekly review references race date and plans countdown

---

## BUG-006 — Wrong Lavarone race date in seed ⚠️
- **Symptom**: Race date seeded as `2026-09-06`; actual date is `2026-08-29`
- **Source**: Confirmed on lavaronetriathlon.com
- **Fix**: `migrations/2026-05-13-fix-lavarone-date.sql` created; seed file `2026-05-11-seed-lavarone-race.sql` corrected
- **Migration to run**: `migrations/2026-05-13-fix-lavarone-date.sql` (if race already inserted with wrong date), otherwise just run the corrected seed
- **Test**: `SELECT race_date FROM races WHERE name = 'Lavarone Cross Sprint'` → `2026-08-29`

---

## BUG-007 — Gemini 2.0 Flash has free-tier quota = 0 ✅
- **Symptom**: `GeminiClient` raised `429 RESOURCE_EXHAUSTED` with `limit: 0` on `gemini-2.0-flash`
- **Root cause**: The Google Cloud project for the API key has no free-tier quota for `gemini-2.0-flash`; `gemini-2.5-flash` is available instead
- **Fix**: Changed `GeminiClient.MODEL` to `gemini-2.5-flash`; also migrated from deprecated `google-generativeai` to `google-genai` SDK; added `thinking_budget=0` to disable chain-of-thought (not useful for this task, wastes tokens)
- **Test**: Run `python -m coach.coaching.post_session_analysis --recent --days 1` with `GEMINI_API_KEY` set → analysis saved, `model_used = gemini-2.5-flash`, `cost_usd = 0.0`

---

## Known limitations — Not bugs

### LIMIT-001 — `get_physiology_zones` "not loaded yet" in Claude.ai 📋
- **Symptom**: Error `'triathlon-coach:get_physiology_zones' has not been loaded yet` on first call in a session
- **Explanation**: Claude.ai lazy-loads MCP tool schemas. Resolves automatically when Claude calls `tool_search` internally before retrying. Not fixable in MCP server code.
- **Workaround if persistent**: Disconnect and reconnect in Claude.ai Settings → Connectors → triathlon-coach

### LIMIT-002 — Goal Board empty without mesocycles 📋
- **Symptom**: Excalidraw Goal Board in dashboard shows only the timeline axis, no content
- **Explanation**: Board is generated from `mesocycles`, `races`, `planned_sessions`. Empty until first mesocycle is committed.
- **Action**: Run `/generate_mesocycle` in Claude.ai

### LIMIT-003 — `physiology_zones` empty until first fitness test 📋
- **Symptom**: Claude.ai reports no current zones; session proposals use estimated values from `CLAUDE.md`
- **Explanation**: Zones auto-populate when `fitness_test_processor.py` detects a matching activity name. First test planned June 2026.
- **No action needed** until first test is performed

---

## Pending migrations — run in Supabase SQL editor

| Migration file | Bug / Feature | Status |
|----------------|---------------|--------|
| `migrations/2026-05-11-seed-lavarone-race.sql` | BUG-006 | ⏳ Run if races table is empty |
| `migrations/2026-05-12-mesocycles-unique.sql` | — | ⏳ Run once |
| `migrations/2026-05-13-subjective-log-kinds.sql` | BUG-004 | ⏳ Run once |
| `migrations/2026-05-13-fix-lavarone-date.sql` | BUG-006 | ⏳ Run if seed was already applied with wrong date |
| `migrations/2026-05-14-subjective-log-severity.sql` | Phase 1.5 | ⏳ Run once (adds severity/expected_duration_days/body_location) |
| `migrations/2026-05-14-sent-reminders.sql` | Phase 1.6 | ⏳ Run once (proactive reminders dedup table) |
| `migrations/2026-05-14-predictions-outcomes.sql` | Phase 2.1 | ⏳ Run once (outcome tracking engine) |
| `migrations/2026-05-14-season-year.sql` | Phase 2.7 | ⏳ Run once (multi-race architecture) |

---

## Cognitive MVP Plan — Progress

Piano completo in `~/.claude/plans/spicy-weaving-twilight.md`.

### Phase 1 — Quick wins ✅ COMPLETED (2026-05-14)

| Modulo | Status | Commit |
|--------|--------|--------|
| 1.1 Hybrid LLM routing (Gemini/Anthropic/Claude Pro) | ✅ | cb68357 |
| 1.2 Anthropic prompt caching (ephemeral) | ✅ | cb68357 |
| 1.3 `/manual_activity` Telegram handler | ✅ | 8c30eb3 |
| 1.4 Outlier validation (HR/pace/duration/cross-field) | ✅ | c5000b6 |
| 1.5 Injury/illness severity end-to-end | ✅ | d7b339d |
| 1.6 Proactive Telegram reminders | ✅ | f82791e |

**Risparmio costi atteso**: €1.50/mese → €0.30/mese (-80%).

### Phase 2 — Adaptive architecture ✅ COMPLETED (2026-05-14)

| Modulo | Status | Commit |
|--------|--------|--------|
| 2.1 Outcome tracking engine (predictions + outcomes + verifier) | ✅ | 86456dd |
| 2.5 Risk modeling (overreaching/injury/recovery) + brief integration | ✅ | 509ba55 |
| 2.6 Fitness test lifecycle (scheduler + pre-test prediction) | ✅ | 1a35b84 |
| 2.7 Multi-race architecture (season_year) | ✅ | 86456dd |
| 2.2 Pattern extraction prescriptive output | ✅ | (this commit) |
| 2.3 Athlete beliefs template + integration | ✅ | (this commit) |
| 2.4 Citation tags obbligatorie in skill | ✅ | (this commit) |

Pattern_extraction ora richiede output strutturato `[Osservazione] (n=X, conf=Y) → Prescrizione: ... Expected outcome: ...`.

athlete_beliefs.md aggiornato automaticamente da outcome_verification.py ogni domenica notte.

Skill weekly_review, generate_mesocycle, propose_session richiedono citation tags `[source: ...]` per ogni decisione strutturale e `[athlete-belief: ...]` quando applicano beliefs.

### Phase 3 — Professional coach (after Phase 2)

Hypothesis testing, multi-horizon planning, sport-specific modules, decision provenance, pre-test/post-test calibration.

### Phase 4 — Cognitive MVP (final)

Outcome engine (refactor cognitive layer) + decision priority + uncertainty framework + Bayesian belief engine. Vedi piano completo in `~/.claude/plans/spicy-weaving-twilight.md`.
