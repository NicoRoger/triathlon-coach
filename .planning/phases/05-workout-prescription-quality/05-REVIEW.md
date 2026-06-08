---
phase: 05-workout-prescription-quality
reviewed: 2026-06-08T12:10:50Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - scripts/verify_prescription_quality.py
  - workers/mcp-server/src/index.ts
  - migrations/2026-06-07-workout-prescription-quality.sql
  - tests/test_active_constraints.py
findings:
  critical: 4
  warning: 6
  info: 3
  total: 13
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-06-08T12:10:50Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed four files delivered in Phase 5 (Workout Prescription Quality): the verification
script, the MCP server Worker, the DB migration, and the integration tests.

The migration and test files are well-structured. The critical issues are concentrated in
`workers/mcp-server/src/index.ts`: the OAuth token endpoint issues a real bearer token with no
authentication, the auth bypass accepting any request with an empty `Authorization` header, and
multiple unvalidated date string injections into Supabase REST filter parameters.
`forceGarminSync` will also always time-out inside a Cloudflare Worker due to the 30-second
CPU wall that makes the 90-second polling loop impossible.

---

## Critical Issues

### CR-01: OAuth token endpoint returns real bearer token with no authentication

**File:** `workers/mcp-server/src/index.ts:332-339`
**Issue:** The `/oauth/token` POST handler issues `env.MCP_BEARER_TOKEN` (the real, permanent
service credential) to any caller — without verifying the authorization code, PKCE verifier,
`client_id`, or any other OAuth parameter. Any unauthenticated HTTP client that POSTs to
`/oauth/token` receives the permanent bearer token. Combined with the `*` CORS policy, this
is exploitable from any browser origin.

```
POST https://<worker>/oauth/token          # no body required
→ { "access_token": "<MCP_BEARER_TOKEN>", ... }
```

**Fix:** At minimum, verify that the supplied `code` was previously issued (store it in KV on
`/oauth/callback`) and that the PKCE `code_verifier` matches `code_challenge` from the
authorisation request (S256). If the single-user design makes full PKCE impractical, remove
the `/oauth/token` endpoint and rely exclusively on the direct-bearer path used by Claude Code.

```typescript
if (url.pathname === "/oauth/token" && req.method === "POST") {
  const body = await req.formData(); // or req.json()
  const code = body.get("code");
  const verifier = body.get("code_verifier");
  const storedChallenge = await env.KV.get(`oauth_code:${code}`);
  if (!storedChallenge || !verifyS256(verifier, storedChallenge)) {
    return new Response("invalid_grant", { status: 400 });
  }
  await env.KV.delete(`oauth_code:${code}`);
  return jsonResponse({ access_token: env.MCP_BEARER_TOKEN, ... });
}
```

---

### CR-02: Auth bypass — any request without Authorization header is treated as authenticated

**File:** `workers/mcp-server/src/index.ts:370-373`
**Issue:** The comment says "Claude.ai dopo OAuth non manda bearer" but the implementation
treats the **absence of any `Authorization` header** as proof of OAuth-authenticated origin.
This means any anonymous client (curl, browser, crawler) that simply omits the header can
call all MCP tools — including `commit_plan_change` and `commit_mesocycle` — with no
credential at all.

```typescript
const isOAuthRequest = !auth; // line 371 — true for ALL unauthenticated callers
if (!isBearerValid && !isOAuthRequest) {  // line 373 — never false; always passes
```

**Fix:** Remove the `isOAuthRequest` bypass. After the OAuth flow, the token endpoint returns
`env.MCP_BEARER_TOKEN`, so Claude.ai will send `Authorization: Bearer <token>` on all
subsequent tool calls. Require the bearer token unconditionally:

```typescript
if (!isBearerValid) {
  return new Response("Unauthorized", { status: 401, headers: { ...corsHeaders(),
    "WWW-Authenticate": `Bearer realm="triathlon-coach"` } });
}
```

---

### CR-03: Unvalidated date strings interpolated directly into Supabase REST filter parameters

**File:** `workers/mcp-server/src/index.ts` — multiple locations
**Issue:** User-supplied date strings are interpolated directly into PostgREST query strings
without format validation. The affected parameters are:

- `args.planned_date` (line 760) — `planned_sessions?planned_date=eq.${args.planned_date}&sport=eq.${args.sport}`
- `args.start_date` (line 892) — `mesocycles?start_date=eq.${args.start_date}`
- `args.resolved_at` (line 935) — used directly in the PATCH body (JSON, lower risk) but also logged
- `args.date` → `getPlannedSession` (line 439 → 706) — `planned_sessions?planned_date=eq.${date}`
- `raceDate` (line 621) — `planned_sessions?...planned_date=eq.${raceDate}&...`
- `activityDate` (line 670) — derived from `activity.started_at` (DB-sourced, lower risk)
- `sport` value in `getActivityHistory` (line 712) — partially mitigated by enum check in the tool schema, but the schema is advisory; the router calls `args.sport || "all"` without re-validating

An input like `2026-06-01&status=eq.active` in `planned_date` appends an extra PostgREST
filter, potentially leaking rows that should not be visible or bypassing intended filters.
While Supabase's service key + RLS mitigates data mutation risk, filter injection can still
be used for data exfiltration or bypassing the "resolved_at IS NULL" active-constraints filter.

**Fix:** Add an `isDate(v: string): boolean` validator (YYYY-MM-DD) and a `isSport` guard,
and throw before building any query string:

```typescript
function isDateString(v: unknown): v is string {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);
}

// In commitPlanChange, before building the URL:
if (!isDateString(args.planned_date))
  throw new Error(`Invalid planned_date: ${args.planned_date}`);
```

Apply the same pattern for `start_date`, `end_date`, `race_date`, and `args.date`.
The existing `isUuid` helper shows the correct model — replicate it for date strings.

---

### CR-04: `forceGarminSync` contains a 90-second polling loop — will always time out in a Cloudflare Worker

**File:** `workers/mcp-server/src/index.ts:983-996`
**Issue:** Cloudflare Workers have a CPU time limit of 30 seconds (paid plan) / 10 ms (free
plan). The loop polls for up to 90 seconds with 10-second sleeps:

```typescript
while (Date.now() - startTime < 90_000) {
  await sleep(10_000);   // awaits a Promise<void> for 10 s, consuming wall-clock time
  ...
}
```

Cloudflare Workers do not support wall-clock sleeping beyond the CPU limit. The Worker will
be killed mid-loop, returning an opaque 1101/1102 error to Claude rather than the structured
`{ status: "timeout" }` response. The GitHub Actions workflow is also unlikely to complete
in 90 seconds, making even a successful execution always return `status: "timeout"`.

**Fix:** Remove the polling loop. Fire the GitHub dispatch and return immediately with
`status: "triggered"`. Let the caller check sync status via `get_weekly_context` /
`sync_status` after a delay:

```typescript
if (!dispatchResp.ok) {
  throw new Error(`GitHub dispatch failed: ${dispatchResp.status} ...`);
}
return {
  status: "triggered",
  message: "Sync job dispatched. Check sync_status in get_weekly_context after ~3 minutes.",
  last_sync_before_trigger: lastSync || null,
};
```

---

## Warnings

### WR-01: `rpc.params` accessed without null guard — crashes on `tools/call` with missing params

**File:** `workers/mcp-server/src/index.ts:405`
**Issue:** `const { name, arguments: args } = rpc.params;` will throw a TypeError if a client
sends a `tools/call` request without a `params` field (valid in malformed but common
hand-crafted payloads). The outer `try/catch` in `handleRpc` will catch it and return a
JSON-RPC internal error, but the stack trace will reference a null-destructure rather than
a descriptive message.

**Fix:**
```typescript
if (rpc.method === "tools/call") {
  const params = rpc.params ?? {};
  const { name, arguments: args } = params;
  if (!name) return err(rpc.id, -32602, "Missing tool name in params");
  ...
}
```

---

### WR-02: `commitPlanChange` — no date format validation on `planned_date` allows silent DB errors or filter injection

**File:** `workers/mcp-server/src/index.ts:760`
**Issue:** `planned_date` is validated as non-null (line 737) but its format is never checked.
A value like `"2026-13-01"` or `"today"` will either be rejected by Postgres with a parse
error surfaced as a 500-level throw, or — if it contains special characters — silently
alter the PostgREST filter string (see CR-03). The required-field check gives false
confidence that the field is safe.

**Fix:** Validate with `isDateString(args.planned_date)` before the fetch call (as described
in CR-03 fix).

---

### WR-03: `commitMesocycle` — `start_date` not validated, and upsert-by-`start_date` is fragile

**File:** `workers/mcp-server/src/index.ts:891-895`
**Issue:** Two issues:
1. `args.start_date` is interpolated directly into the lookup URL without format validation
   (`mesocycles?start_date=eq.${args.start_date}`).
2. The upsert logic fetches `mesocycles?start_date=eq.<value>` and picks `existing[0]`.
   If two mesocycles share the same `start_date` (possible if manually inserted), the
   PATCH updates only the first one returned, silently ignoring the others and potentially
   corrupting the mesocycle state.

**Fix:** Validate `start_date` and `end_date` with `isDateString`. For the upsert, prefer a
database-side `INSERT ... ON CONFLICT (start_date) DO UPDATE` via a `Prefer: resolution=merge-duplicates`
header, or add a UNIQUE constraint on `mesocycles.start_date` in a migration.

---

### WR-04: `getPhysiologyZones` — date arithmetic mixes Rome-local string with UTC `new Date()`

**File:** `workers/mcp-server/src/index.ts:814-819`
**Issue:**
```typescript
const todayDate = new Date(todayRomeISO());   // e.g. "2026-06-08" → parsed as UTC midnight
const validFrom = new Date(zone.valid_from);  // "2026-06-04" → also UTC midnight
```
`todayRomeISO()` returns the local Rome date string (e.g., `"2026-06-08"`). When passed to
`new Date()`, it is parsed as UTC midnight, not Rome midnight. During DST-overlap hours
(midnight–02:00 Rome time = 22:00–00:00 UTC the previous day), `todayRomeISO()` returns
the next day while `new Date(todayRomeISO())` points to the previous UTC midnight, making
`age_days` off by one. The comment on line 817 acknowledges this but accepts it; this is a
latent bug that will manifest as incorrect staleness warnings.

**Fix:** Compute both dates consistently in UTC:
```typescript
const todayUTC = new Date(todayRomeISO() + "T00:00:00Z");
const validFromUTC = new Date(zone.valid_from + "T00:00:00Z");
zone.age_days = Math.max(0, Math.floor((todayUTC.getTime() - validFromUTC.getTime()) / 86400000));
```

---

### WR-05: Migration RLS policy is missing — `ENABLE ROW LEVEL SECURITY` without a permissive policy locks out all queries

**File:** `migrations/2026-06-07-workout-prescription-quality.sql:25-26`
**Issue:** The migration enables RLS on `active_constraints`:
```sql
ALTER TABLE active_constraints ENABLE ROW LEVEL SECURITY;
```
No `CREATE POLICY` statement follows. In PostgreSQL, enabling RLS without defining any
policy means **all rows are hidden from all roles** (including `service_role` unless it has
`BYPASSRLS`). Supabase grants `BYPASSRLS` to `service_role` by default, so the Python
client (which uses `SUPABASE_SERVICE_KEY`) is unaffected. However, the MCP Worker also uses
`SUPABASE_SERVICE_KEY` as both `apikey` and `Authorization`, so it too bypasses RLS. The
test `test_active_constraints_seed_has_two_rows` also uses the service client. This means
the RLS policy serves no security purpose as written — no anon or authenticated-role
access is possible because no policy exists, but the only callers are service_role (which
bypasses RLS anyway).

This is a correctness/completeness defect: the RLS comment claims "V4 ASVS L1" compliance,
but there is no policy defining what service_role or authenticated users can do, making the
"protection" nominal. The other tables (e.g., `planned_sessions`) presumably have policies
in `sql/schema.sql` — this table does not.

**Fix:** Add a permissive service-role policy for consistency with the rest of the schema,
or document explicitly that this table is intended to be service-role-only:
```sql
CREATE POLICY "service_role_full_access" ON active_constraints
  FOR ALL TO service_role USING (true) WITH CHECK (true);
```

---

### WR-06: `verify_prescription_quality.py` — `_verify_active_constraints` fetches all rows without pagination

**File:** `scripts/verify_prescription_quality.py:45-49`
**Issue:** The query selects all rows from `active_constraints` with no `.limit()`:
```python
res = (
    sb.table("active_constraints")
    .select("id,type,discipline,description,severity,created_at,resolved_at")
    .execute()
)
```
The Supabase Python client defaults to a server-side row limit (typically 1,000). This is
fine for a medical-constraint table that will never grow large. The issue is that
`_verify_mesocycles_progression_plan` (line 126) applies `.lte` / `.gte` filters but also
fetches without pagination. If these tables ever accumulate many rows, the verify script
silently truncates and produces misleading results.

More importantly, the `.execute()` call is not inside a loop for retries and the script
has no timeout — a network partition will hang indefinitely. This is a script (not a
scheduled job), so it is a low-severity robustness issue.

**Fix:** Add `.limit(100)` to `active_constraints` and `.limit(5)` to mesocycles, and
document the assumption. For network resilience, set a timeout via `supabase.postgrest.timeout`.

---

## Info

### IN-01: `test_active_constraints_seed_has_two_rows` uses `.eq("resolved_at", None)` — may not filter correctly

**File:** `tests/test_active_constraints.py:105`
**Issue:** `.eq("resolved_at", None)` in the supabase-py client is translated to
`resolved_at=eq.null` in the PostgREST query string. PostgREST accepts this, but the
semantically correct filter for IS NULL is `.is_("resolved_at", "null")`. The `.eq(col, None)`
form may work with the current supabase-py version but is not the officially documented
idiom and could silently return zero rows if the client library changes behaviour in a
patch release.

**Fix:**
```python
.is_("resolved_at", "null")
```

---

### IN-02: Hardcoded GitHub repository path in `forceGarminSync`

**File:** `workers/mcp-server/src/index.ts:966`
**Issue:** The repository path `NicoRoger/triathlon-coach` is hardcoded:
```typescript
"https://api.github.com/repos/NicoRoger/triathlon-coach/actions/workflows/ingest.yml/dispatches"
```
If the repo is renamed or transferred, this silently fails with a 404, but the error is
caught and re-thrown only for non-OK status codes — which is correct. However, the
username `NicoRoger` does not match the git user in the repository metadata (`Nicolò Ruggero`).
Verify the exact GitHub username to avoid a silent 404 on first call.

**Fix:** Move to an environment variable `GH_REPO` (e.g., `"NicoRoger/triathlon-coach"`)
in the `Env` interface, or at minimum add a comment confirming the exact GitHub username.

---

### IN-03: `_verify_physiology_zones_age` always returns `True` (never `False`) regardless of zone staleness

**File:** `scripts/verify_prescription_quality.py:77-112`
**Issue:** The function docstring says "Ritorna False solo in caso di eccezione imprevista"
and the summary counter at `main()` line 182 includes its return value in `passed/N`. This
means even if all zones are >42 days old, the counter reports `2/3 OK` (or `3/3 OK`) with
no distinction — the physiology-zones section always contributes a pass. The ATTENZIONE
print is informational only and the return value is always `True` on success.

This is intentional per the docstring, but it means the aggregate `passed/N` score is
misleading: it counts a "no-op informational check" as a passed gate. A reader could
interpret `3/3 OK` as meaning physiology zones are fresh, when they may be 200 days old.

**Fix:** Either remove the physiology-zones return value from the `results` list (making it
a pure print section), or change the function to return `False` when any zone exceeds 42
days, consistent with the WORKOUT-03 spirit of the phase gate:

```python
stale = any(age_days > 42 for (_, age_days) in zone_ages)
return not stale
```

---

_Reviewed: 2026-06-08T12:10:50Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
