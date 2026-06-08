---
phase: 05-workout-prescription-quality
fixed_at: 2026-06-08T15:00:00Z
review_path: .planning/phases/05-workout-prescription-quality/05-REVIEW.md
iteration: 1
findings_in_scope: 12
fixed: 12
skipped: 0
status: all_fixed
---

# Phase 05: Code Review Fix Report

**Fixed at:** 2026-06-08T15:00:00Z
**Source review:** `.planning/phases/05-workout-prescription-quality/05-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 12
- Fixed: 12
- Skipped: 0

Note: WR-02 (`commitPlanChange` date format validation) was fixed as part of CR-03 (same
`isDateString` guard applied in `commitPlanChange`). It is counted as fixed but shares its
commit with CR-03.

---

## Fixed Issues

### CR-01: OAuth token endpoint returns the real bearer token with no authentication

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `4d18150`
**Applied fix:** The `/oauth/callback` handler now generates a short-lived HMAC-SHA256
signed code (`timestamp.hmac_hex`) keyed on `MCP_BEARER_TOKEN`. The `/oauth/token` endpoint
verifies the HMAC and rejects codes older than 5 minutes with `invalid_grant`. No KV storage
required; the HMAC replaces the previously meaningless `btoa("auth_code_${Date.now()}")`.
Token `expires_in` reduced from 31536000 to 3600 seconds.

---

### CR-02: Auth bypass — any request without an Authorization header is treated as authenticated

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `bcc3e5b`
**Applied fix:** Removed `isOAuthRequest = !auth` and the `if (!isBearerValid && !isOAuthRequest)`
guard. Replaced with `if (!isBearerValid)` — bearer token is now required unconditionally for
all MCP POST requests. Claude.ai obtains the token via the now-secured `/oauth/token` endpoint.

---

### CR-03: Unvalidated user-supplied strings interpolated into PostgREST query parameters

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `81200f5`
**Applied fix:** Added `isDateString()` (regex `/^\d{4}-\d{2}-\d{2}$/`) and `VALID_SPORTS`/
`VALID_KINDS` Set constants following the existing `isUuid()` pattern. Applied validation
guards before any URL construction in:
- `getPlannedSession` (date parameter)
- `getRaceContext` (raceDate parameter)
- `getActivityHistory` (sport parameter)
- `queryLog` (kind parameter)
- `commitPlanChange` (planned_date — also covers WR-02)
- `commitMesocycle` (start_date and end_date)

---

### CR-04: `forceGarminSync` 90-second polling loop will always crash the Worker

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `9ef1da4`
**Applied fix:** Removed the `while (Date.now() - startTime < 90_000)` polling loop entirely.
After the GitHub Actions dispatch succeeds, the function returns immediately with
`{status: "triggered", message: "...check via get_weekly_context after ~3-5 minutes",
last_sync_before_trigger}`. The `sleep()` helper is now unused but preserved.

---

### CR-05: `propose_session` skill — readiness 50-74 adaptation logic allows double-downgrade and unguarded strides

**Files modified:** `skills/propose_session.md`
**Commit:** `a498766`
**Applied fix (requires human verification — logic rule):**
1. Readiness 50-74 bullet now explicitly states: "NON applicare anche il blocco Condizioni
   avverse — una sola riduzione per sessione."
2. The adverse-conditions block clarified as applicable "SOLO se readiness >= 75" (no
   intensity reduction already applied).
3. Strides drill (post-fascite) has an explicit guard: "includi SOLO se injury_flag = false
   E readiness >= 65. Se active_constraints include fascite con severity='high', sostituisci
   con cadenza drill."

---

### WR-01: `rpc.params` destructured without null guard

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `6646067`
**Applied fix:** Added `const params = rpc.params ?? {}` and an explicit `if (!name) return
err(rpc.id, -32602, "Missing required field: params.name")` check before calling the tool
router. The outer try/catch still catches unexpected errors.

---

### WR-02: `commitPlanChange` — no format validation on `planned_date`

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `81200f5` (shared with CR-03)
**Applied fix:** `isDateString(args.planned_date)` validation added in `commitPlanChange`
as part of the CR-03 validator sweep. Throws `"Invalid planned_date format: ... Expected YYYY-MM-DD."` before any URL construction.

---

### WR-03: `commitMesocycle` upsert-by-`start_date` picks arbitrary row when duplicates exist

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `b932b6b`
**Applied fix:** Added `if (existing.length > 1) throw new Error("Ambiguous: N mesocycles found for start_date X. Resolve duplicates before updating.")` before the `existing[0].id` access.

---

### WR-04: `getPhysiologyZones` — `age_days` computation mixes Rome-local date string with UTC midnight

**Files modified:** `workers/mcp-server/src/index.ts`
**Commit:** `9fa5666`
**Applied fix:** Both `todayRomeISO()` and `zone.valid_from` are now appended with
`"T00:00:00Z"` before `new Date(...)` parsing, pinning both to UTC midnight. Eliminates
the 1-day off-by-one during 22:00–23:59 UTC. Comment added explaining the rationale.

---

### WR-05: Migration enables RLS on `active_constraints` but defines no policy

**Files modified:** `migrations/2026-06-07-workout-prescription-quality.sql`
**Commit:** `58cd52f`
**Applied fix:** Added `CREATE POLICY IF NOT EXISTS "service_role_full_access" ON active_constraints FOR ALL TO service_role USING (true) WITH CHECK (true)` immediately after `ENABLE ROW LEVEL SECURITY`. Matches the pattern of other tables in `sql/schema.sql`. `IF NOT EXISTS` keeps the migration idempotent.

---

### WR-06: Migration seed idempotency guard is too coarse — race condition on concurrent runs

**Files modified:** `migrations/2026-06-07-workout-prescription-quality.sql`
**Commit:** `b3f153c`
**Applied fix:** Added `CREATE UNIQUE INDEX IF NOT EXISTS active_constraints_injury_discipline_active ON active_constraints (type, discipline) WHERE resolved_at IS NULL` before the seed INSERT statements. The partial UNIQUE index provides DB-level enforcement that WHERE NOT EXISTS alone cannot guarantee under concurrent execution.

---

### WR-07: `generate_mesocycle.md` — `record_prediction` call references a Python module not in scope for Claude.ai

**Files modified:** `skills/generate_mesocycle.md`
**Commit:** `b00a002`
**Applied fix:** Added a prominent NOTE at the start of the "Output prediction" section
clarifying that the Python snippet is CLI-only. When operating via MCP, Claude.ai should
log the prediction as a text note in `training_journal.md` using a specified format instead
of attempting a fabricated tool call.

---

_Fixed: 2026-06-08T15:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
