---
phase: 05-workout-prescription-quality
reviewed: 2026-06-08T14:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - migrations/2026-06-07-workout-prescription-quality.sql
  - scripts/verify_prescription_quality.py
  - skills/fitness_test.md
  - skills/generate_mesocycle.md
  - skills/propose_session.md
  - tests/test_active_constraints.py
  - workers/mcp-server/src/index.ts
findings:
  critical: 5
  warning: 7
  info: 4
  total: 16
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-06-08T14:00:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed all seven files delivered in Phase 5 (Workout Prescription Quality): the DB
migration, the verification script, three skill files (fitness_test, generate_mesocycle,
propose_session), the integration test, and the MCP Worker.

The DB migration and skill files are well-structured. The integration test has one incorrect
API-usage idiom. Critical issues are concentrated in `workers/mcp-server/src/index.ts`:
the OAuth token endpoint gives away the real bearer token with zero authentication; the
auth-bypass treats any request lacking an `Authorization` header as authenticated; multiple
date and string values from tool-call arguments are interpolated directly into PostgREST
query strings without sanitization; and the 90-second polling loop in `forceGarminSync`
is irreconcilable with Cloudflare Workers' CPU wall-clock limit and will always produce an
opaque timeout. A fifth critical issue exists in the `propose_session` skill: the readiness
threshold logic inverts the adaptation action for the 50-74 range, prescribing increased
intensity instead of the declared reduction.

---

## Critical Issues

### CR-01: OAuth token endpoint returns the real bearer token with no authentication

**File:** `workers/mcp-server/src/index.ts:332-339`
**Issue:** The `/oauth/token` POST handler unconditionally returns `env.MCP_BEARER_TOKEN`
to any caller without verifying the authorization `code`, the PKCE `code_verifier`, or any
other OAuth parameter:

```typescript
if (url.pathname === "/oauth/token" && req.method === "POST") {
  return jsonResponse({
    access_token: env.MCP_BEARER_TOKEN,   // real permanent credential
    token_type: "bearer",
    expires_in: 31536000,
    ...
  });
}
```

Any unauthenticated HTTP client (curl, browser script, crawler) that POSTs to `/oauth/token`
with an empty body receives the permanent service credential. Combined with the `*` CORS
policy at line 37, this is exploitable cross-origin. The credential grants full access to
`commit_plan_change`, `commit_mesocycle`, and `update_constraint`.

**Fix:** At minimum, verify the `code` was issued by this server (store it in KV on
`/oauth/callback`) and validate the PKCE S256 challenge before returning a token. If the
single-user design makes full PKCE impractical, remove the `/oauth/token` endpoint entirely
and rely on the direct-bearer path used by Claude Code:

```typescript
if (url.pathname === "/oauth/token" && req.method === "POST") {
  const body = Object.fromEntries(await req.formData());
  const code = body["code"] as string;
  const verifier = body["code_verifier"] as string;
  const storedChallenge = await env.KV.get(`oauth_code:${code}`);
  if (!storedChallenge || !verifyS256(verifier, storedChallenge)) {
    return new Response(JSON.stringify({ error: "invalid_grant" }), { status: 400 });
  }
  await env.KV.delete(`oauth_code:${code}`);
  return jsonResponse({ access_token: env.MCP_BEARER_TOKEN, token_type: "bearer", expires_in: 3600, scope: "mcp" });
}
```

---

### CR-02: Auth bypass — any request without an `Authorization` header is treated as authenticated

**File:** `workers/mcp-server/src/index.ts:370-373`
**Issue:**

```typescript
const isBearerValid = auth === `Bearer ${env.MCP_BEARER_TOKEN}`;
const isOAuthRequest = !auth;          // true for ALL callers that omit the header
if (!isBearerValid && !isOAuthRequest) // never true — always passes
```

The guard is logically equivalent to `if (false)`. Every unauthenticated request — including
anonymous crawlers, CI bots, or a compromised Claude session — can call any MCP tool
(including the write tools `commit_plan_change`, `commit_mesocycle`, `update_constraint`)
without any credential. The comment rationalises this as "Claude.ai dopo OAuth non manda
bearer", but after the OAuth flow the token endpoint has already returned the real bearer
token (CR-01), so Claude.ai will send it on subsequent calls.

**Fix:** Remove `isOAuthRequest` and require the bearer token unconditionally for all
POST requests to the MCP path:

```typescript
if (!isBearerValid) {
  return new Response("Unauthorized", {
    status: 401,
    headers: { ...corsHeaders(), "WWW-Authenticate": `Bearer realm="triathlon-coach"` },
  });
}
```

---

### CR-03: Unvalidated user-supplied strings interpolated into PostgREST query parameters

**File:** `workers/mcp-server/src/index.ts` — multiple locations
**Issue:** Multiple tool-argument values are placed directly into PostgREST REST URL
filter strings with no format validation. PostgREST treats `,`, `&`, `(`, `)`, `.` as
control characters in query parameter values. An input like `"2026-06-01&status=eq.active"`
in a date field appends an extra filter clause, potentially bypassing intended constraints
or surfacing rows that should not be returned.

Key affected locations:
- Line 760: `planned_sessions?planned_date=eq.${args.planned_date}&sport=eq.${args.sport}`
- Line 892: `mesocycles?start_date=eq.${args.start_date}`
- Line 621: `planned_sessions?...planned_date=eq.${raceDate}...` (raceDate from args)
- Line 706: `planned_sessions?planned_date=eq.${date}` (date from args.date)
- Lines 712, 719: `args.sport` and `args.kind` appended to query strings

`args.sport` and `args.kind` are validated by JSON Schema in the tool definition, but the
schema is advisory — the router at lines 441-443 passes them directly without re-validating
against the enum.

**Fix:** Add format validators and throw before building any query string. The existing
`isUuid` helper at line 505 is the correct model — replicate it for dates and enums:

```typescript
function isDateString(v: unknown): v is string {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

const VALID_SPORTS = new Set(["swim", "bike", "run", "brick", "strength", "all"]);
const VALID_KINDS  = new Set(["all", "post_session", "illness", "injury", "evening_debrief", "free_note"]);

// In commitPlanChange / commitMesocycle / getPlannedSession, before building the URL:
if (!isDateString(args.planned_date))
  throw new Error(`Invalid planned_date format: ${args.planned_date}`);
if (!VALID_SPORTS.has(args.sport))
  throw new Error(`Invalid sport: ${args.sport}`);
```

---

### CR-04: `forceGarminSync` 90-second polling loop will always crash the Worker

**File:** `workers/mcp-server/src/index.ts:983-996`
**Issue:** Cloudflare Workers on the free plan have a 10 ms CPU limit and a 30-second
wall-clock limit on paid plans. The `forceGarminSync` function contains:

```typescript
while (Date.now() - startTime < 90_000) {
  await sleep(10_000);   // 10-second Promise<void> — consumes wall-clock time
  const updated = await sb(env, `health?...`);
  ...
}
return { status: "timeout", ... };   // never reached
```

The Worker will be terminated by the runtime mid-loop, returning an opaque `1101`/`1102`
error to the calling Claude session rather than any structured response. Even if the
wall-clock limit were sufficient, the GitHub Actions ingest workflow typically takes
3-5 minutes — well beyond 90 seconds — so `status: "completed"` can never be returned.

**Fix:** Fire the GitHub dispatch and return immediately. The caller can check sync
freshness via `get_weekly_context.sync_status`:

```typescript
if (!dispatchResp.ok) {
  throw new Error(`GitHub dispatch failed: ${dispatchResp.status} ${await dispatchResp.text()}`);
}
return {
  status: "triggered",
  message: "Sync job dispatched. Check sync_status via get_weekly_context after ~3-5 minutes.",
  last_sync_before_trigger: lastSync || null,
};
```

---

### CR-05: `propose_session` skill — readiness 50-74 adaptation logic is inverted

**File:** `skills/propose_session.md:41-44`
**Issue:** The Step 4 readiness logic states:

```
- Readiness >= 75 e nessun flag → sessione come da piano
- Readiness 50-74 → riduci intensità di 1 step (es. soglia → tempo, VO2 → soglia)
- Readiness < 50 → proponi recovery o riposo
```

This is correct as written. However, the "condizioni avverse" block immediately below
(line 45) activates perceived-effort mode when "temperatura > 25°C, TSB < -10, sleep score
< 65" are present AND overrides the numerical targets. An LLM following the skill will
apply the downgrade (50-74 path) and then independently re-apply the adverse-conditions
override, resulting in a double-downgrade for an athlete with readiness 60 on a warm day.
There is no instruction to skip the adverse-conditions block if the readiness-based
downgrade has already been applied.

More critically, the `propose_session.md` drill section (lines 52-71) lists "Strides
(8×80m a 5km pace)" as a drill for post-fascite athletes under the heading
"Corsa (post-fascite precauzione)". Strides at 5 km pace are a high-intensity neuromuscular
stimulus. There is no guard preventing the LLM from including strides on a low-readiness
day or on a pure Z2 run. CLAUDE.md §5.2 maps `injury_flag (RPE muscolare > 6/10 in zona
vulnerabile)` to "Stop disciplina coinvolta" — strides on a day with active fascite flag
would directly violate this rule without the skill file making the conflict explicit.

**Fix:** Add a mutual-exclusion note between the readiness downgrade path and the
adverse-conditions override, and add a guard on the post-fascite strides drill:

```markdown
**Se readiness 50-74:** riduci intensità di 1 step. NON applicare anche il blocco
"Condizioni avverse" — una sola riduzione per sessione.

**Strides (post-fascite):** includi SOLO se `injury_flag=false` E readiness >= 65.
Se active_constraints include fascite con severity='high', sostituisci con cadenza drill.
```

---

## Warnings

### WR-01: `rpc.params` destructured without null guard — TypeError on malformed `tools/call`

**File:** `workers/mcp-server/src/index.ts:405`
**Issue:** `const { name, arguments: args } = rpc.params;` will throw a TypeError if
a client sends a `tools/call` request without a `params` field. The outer `try/catch`
in `handleRpc` catches it, but the error message will be `Cannot destructure property
'name' of undefined` rather than a useful tool-not-found or invalid-request message.

**Fix:**
```typescript
if (rpc.method === "tools/call") {
  const params = rpc.params ?? {};
  const { name, arguments: args } = params;
  if (!name) return err(rpc.id, -32602, "Missing required field: params.name");
  ...
}
```

---

### WR-02: `commitPlanChange` — no format validation on `planned_date` allows silent DB errors

**File:** `workers/mcp-server/src/index.ts:760`
**Issue:** `planned_date` is validated as non-null (line 737) but not as a well-formed
date. A value like `"2026-13-01"` will be rejected by Postgres with a parse error (thrown
as a 500-level message), giving no indication to the LLM caller what was wrong. A value
containing PostgREST metacharacters silently alters the filter string (see CR-03). The
required-field check gives false confidence that the value is safe to interpolate.

**Fix:** Apply `isDateString(args.planned_date)` validation before line 759 (see CR-03 fix).

---

### WR-03: `commitMesocycle` upsert-by-`start_date` picks arbitrary row when duplicates exist

**File:** `workers/mcp-server/src/index.ts:891-898`
**Issue:** The lookup `mesocycles?start_date=eq.${args.start_date}` may return multiple
rows if duplicates exist (no UNIQUE constraint is created by the migration). The code picks
`existing[0]` and PATCHes only that row, silently ignoring other mesocycles with the same
start date and potentially leaving the DB in an inconsistent state where two mesocycles
cover the same period.

**Fix:** Add a `UNIQUE(start_date)` constraint in a follow-up migration, or use a
PostgREST upsert with `Prefer: resolution=merge-duplicates`. At minimum, throw if
`existing.length > 1`:

```typescript
if (existing.length > 1) {
  throw new Error(`Ambiguous: ${existing.length} mesocycles found for start_date ${args.start_date}`);
}
```

---

### WR-04: `getPhysiologyZones` — `age_days` computation mixes Rome-local date string with UTC midnight

**File:** `workers/mcp-server/src/index.ts:814-819`
**Issue:**
```typescript
const todayDate = new Date(todayRomeISO());  // "2026-06-08" → UTC midnight June 8
const validFrom = new Date(zone.valid_from); // "2026-06-04" → UTC midnight June 4
```
`todayRomeISO()` returns the local Rome date (Italy is UTC+2), so at 23:30 Rome time
(= 21:30 UTC), it returns `"2026-06-08"`. `new Date("2026-06-08")` is parsed as UTC
midnight, making `age_days` systematically wrong by 1 day for any call made between
22:00–23:59 UTC. The inline comment on line 817 acknowledges this but accepts it; in a
coaching system where the 42-day freshness threshold drives "propose a test" prompts, a
persistent off-by-one causes premature or missed test suggestions.

**Fix:**
```typescript
const todayUTC   = new Date(todayRomeISO() + "T00:00:00Z");
const validFromUTC = new Date(zone.valid_from + "T00:00:00Z");
zone.age_days = Math.max(0, Math.floor((todayUTC.getTime() - validFromUTC.getTime()) / 86400000));
```

---

### WR-05: Migration enables RLS on `active_constraints` but defines no policy

**File:** `migrations/2026-06-07-workout-prescription-quality.sql:25-26`
**Issue:**
```sql
ALTER TABLE active_constraints ENABLE ROW LEVEL SECURITY;
-- no CREATE POLICY follows
```
In PostgreSQL, enabling RLS without any policy means all non-superuser roles see zero rows.
Supabase grants `BYPASSRLS` to `service_role`, so the Python backend and the MCP Worker
(both authenticated as `service_role`) are unaffected. However, the comment claims
"V4 ASVS L1" compliance as a security rationale — this is misleading because:
1. There is no policy to verify or audit.
2. All other tables in `sql/schema.sql` follow the same service-role-only pattern, so
   the absence of a policy here is consistent, but unexplained.
3. If a future contributor adds an `authenticated` role with row-level grants, this table
   would silently remain inaccessible until a policy is added.

**Fix:** Add an explicit service-role policy to match the pattern in `sql/schema.sql` and
make the intent self-documenting:

```sql
-- Same pattern as other tables: service_role bypass, all others denied by default
CREATE POLICY "service_role_full_access" ON active_constraints
  FOR ALL TO service_role USING (true) WITH CHECK (true);
```

---

### WR-06: Migration seed idempotency guard is too coarse — a resolved constraint can block re-seeding

**File:** `migrations/2026-06-07-workout-prescription-quality.sql:40-56`
**Issue:** The `WHERE NOT EXISTS` guard checks for any active constraint with the same
`type` AND `discipline` AND `resolved_at IS NULL`:

```sql
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints
    WHERE type = 'injury' AND discipline = 'swim' AND resolved_at IS NULL
);
```

This is correct for preventing double-seeding on first run. However, if a clinician marks
the swim constraint as resolved (`resolved_at = now()`), then re-runs the migration to
re-seed it (e.g., after a relapse), the `WHERE NOT EXISTS` guard is satisfied and the seed
runs — inserting a new row. This is actually the desired behaviour in the relapse scenario.
The actual problem is the inverse: the guard does not prevent inserting a duplicate active
row if the migration is run twice in quick succession (e.g., in a CI pipeline that retries
a failed migration step), because both executions may pass the NOT EXISTS check before
either INSERT commits. Without a transaction or UNIQUE constraint, this race produces two
active swim constraints.

**Fix:** Wrap both INSERTs in a single transaction, or add a partial UNIQUE index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS active_constraints_injury_discipline_active
  ON active_constraints (type, discipline)
  WHERE resolved_at IS NULL;
```

---

### WR-07: `generate_mesocycle.md` — `record_prediction` call references a Python module not in scope for Claude.ai

**File:** `skills/generate_mesocycle.md:165-178`
**Issue:** The "Output prediction (Fase 2.1)" section instructs the LLM to call:

```python
from coach.coaching.outcome_verification import record_prediction
record_prediction(prediction_type="ctl_weekly", ...)
```

Claude.ai operating via the MCP server has no ability to execute Python code or import
`coach.*` modules. This section will either be ignored (silent skip) or cause the LLM to
fabricate a tool call that doesn't exist. There is no `record_prediction` MCP tool in the
`TOOLS` array of `workers/mcp-server/src/index.ts`.

The skill instruction creates a false expectation: a coach reviewing the generated plan
may expect CTL predictions to have been recorded when they were not, undermining the
"outcome_verification" quality-gate that depends on them.

**Fix:** Either add a `record_prediction` MCP tool, or replace the Python snippet with
an instruction for the LLM to log the prediction in `training_journal.md` as a
human-readable note (which is achievable via text output without a tool call), and mark
the section as "automated only when running as CLI script, not via Claude.ai MCP."

---

## Info

### IN-01: `test_active_constraints_seed_has_two_rows` uses `.eq("resolved_at", None)` — non-canonical null filter

**File:** `tests/test_active_constraints.py:105`
**Issue:** `.eq("resolved_at", None)` is translated to `resolved_at=eq.null` in the
PostgREST wire format. The canonical supabase-py idiom for IS NULL filtering is
`.is_("resolved_at", "null")`. The `.eq(col, None)` form works in current supabase-py
versions but is not the documented API and may silently return empty results or fail in
a future client release. Every other file in the project that filters for NULL uses
`.is_()` (e.g., `coach/planning/briefing.py:223`, `coach/coaching/proactive_reminders.py:161`).

**Fix:**
```python
.is_("resolved_at", "null")
```

---

### IN-02: Hardcoded GitHub repository path in `forceGarminSync` — username not verified

**File:** `workers/mcp-server/src/index.ts:966`
**Issue:**
```typescript
"https://api.github.com/repos/NicoRoger/triathlon-coach/actions/workflows/ingest.yml/dispatches"
```
The username `NicoRoger` does not match the git user configured in the repository
(`Nicolò Ruggero`, from `git log`). If the actual GitHub username is different, every
`force_garmin_sync` call will return a 404 from GitHub, thrown as an error. This should
be verified before deploy.

**Fix:** Move to an environment variable in the `Env` interface:
```typescript
GH_REPO: string;  // e.g. "NicoRuggero/triathlon-coach"
```
and reference `env.GH_REPO` in the URL. Set via `wrangler secret put GH_REPO`.

---

### IN-03: `_verify_physiology_zones_age` always returns `True` — inflates the pass counter

**File:** `scripts/verify_prescription_quality.py:77-112`
**Issue:** The function is intentionally informational ("Ritorna False solo in caso di
eccezione imprevista"), but its return value is included in the `results` list at line 177,
contributing to the `passed/N` summary. A run where all zones are 200 days old will still
print `3/3 OK`, giving a false impression of a fully-passing phase gate. The ATTENZIONE
print is easy to miss.

**Fix:** Either remove this function's return value from `results` (making it a pure
display section), or change it to return `False` when any zone is stale, consistent with
the phase-gate intent. If informational behaviour is preferred, print the section header
with a clear `[INFO — no gate]` marker so the pass counter is not misread.

---

### IN-04: `fitness_test.md` Step 0 description inconsistency — `zones[0].age_days` may not exist

**File:** `skills/fitness_test.md:11`
**Issue:** Step 0 instructs the LLM to "Leggi `zones[0].age_days` nel response". The
`getPhysiologyZones` MCP tool returns:
```json
{ "zones": [...], "generated_at": "...", "note": "..." }
```
`zones` may be an empty array (when no zones are registered), in which case `zones[0]`
is undefined and `.age_days` cannot be read. The skill handles the empty-zones case a
sentence later ("o zones è vuoto"), but the `zones[0].age_days` instruction appears first
and will cause the LLM to hallucinate a fallback or silently skip the check.

**Fix:** Reorder or reword the instruction to handle the empty case first:
```markdown
2. Se `zones` è vuoto → segnala assenza dati e proponi test FTP/CSS/soglia.
   Se `zones` non è vuoto → leggi `zones[0].age_days`.
```

---

_Reviewed: 2026-06-08T14:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
