---
phase: 11-mcp-auth-hardening
reviewed: 2026-06-08T15:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - workers/mcp-server/src/index.ts
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-08T15:00:00Z
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

The four targeted fixes (J2/J3/J4/J6) are mechanically correct — the changes compile and satisfy the stated acceptance criteria. However the adversarial review found three pre-existing critical defects that the phase did not address, plus four warnings including one introduced by an inconsistency in the J6 fix.

---

## Critical Issues

### CR-01: XSS via `redirectUri` reflected verbatim into HTML error page

**File:** `workers/mcp-server/src/index.ts:335`
**Issue:** When `new URL(redirectUri)` throws (malformed URI), the raw `redirectUri` value is interpolated directly into the HTML body returned by `htmlPage()`. An attacker who constructs a request to `/oauth/callback?redirect_uri=<script>alert(1)</script>` will receive a response containing executable script. The `htmlPage()` helper performs no HTML escaping. Although the OAuth callback is not exposed to unauthenticated third parties in a typical single-user deployment, `OPTIONS` preflight and `GET` requests to `/oauth/callback` are fully unauthenticated — any browser tab or Cloudflare worker can trigger this path.

**Fix:**
```typescript
// Add a minimal HTML escape helper
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// In the catch block at line 332:
return htmlPage("Autorizzazione completata", `
  <h1>✅ Autorizzazione completata</h1>
  <p>Puoi chiudere questa finestra e tornare su Claude.ai.</p>
  <p style="font-size:12px;color:#94a3b8">Redirect non disponibile: ${escapeHtml(redirectUri)}</p>
`);
```

---

### CR-02: OAuth PKCE code_challenge accepted but never verified — CSRF + code-substitution attack vector

**File:** `workers/mcp-server/src/index.ts:284-296`
**Issue:** The OAuth metadata advertises `"code_challenge_methods_supported": ["S256"]` (line 266), the authorization endpoint reads `code_challenge` from query parameters and passes it through to the callback (line 284-290), but the token endpoint (lines 341-372) never retrieves or validates the challenge. A conforming OAuth 2.0 PKCE client (Claude.ai is expected to be one) sends a `code_verifier` at the token endpoint; the server must verify `SHA-256(code_verifier) == code_challenge`. Without this check the PKCE mechanism provides zero protection: the authorization code can be intercepted and exchanged by any client that knows the code, defeating the purpose of the entire flow. The HMAC-on-timestamp provides a freshness guarantee but not a binding between the code and the client that initiated the flow.

**Fix:** Either (a) store the `code_challenge` alongside the timestamp in a signed code (extend the code format to `${ts}.${codeChallenge}.${hmacSig}`) and verify it at the token endpoint, or (b) remove `S256` from `code_challenge_methods_supported` and document that this is a simplified single-user flow that relies on TLS + HMAC freshness only. Option (b) is simpler for a single-user deployment.

```typescript
// Option B — remove the false PKCE advertisement:
code_challenge_methods_supported: [],  // S256 not implemented; do not advertise
```

---

### CR-03: DB-sourced `sport` value interpolated into Supabase query without whitelist validation

**File:** `workers/mcp-server/src/index.ts:723-726`
**Issue:** In `getSessionReviewContext`, the `sport` field is read directly from the database row (`activity.sport || "all"`) and then interpolated into two Supabase PostgREST query strings without validation:

```typescript
const sport = activity.sport || "all";
// line 726:
sb(env, `planned_sessions?planned_date=eq.${activityDate}&sport=eq.${sport}`),
// line 729:
getActivityHistory(sport, historyDays, env),
```

`getActivityHistory` does validate against `VALID_SPORTS` and would throw on an unexpected value, but the `planned_sessions` query on line 726 uses `sport` directly. More importantly, if the database contains a crafted `sport` value (e.g., `run&status=eq.planned` or a string containing newlines), it would corrupt the PostgREST query string. The `sport` field in the `activities` table is DB-sourced, not directly from API callers — but indirect injection through a compromised or corrupted DB record is a realistic risk for a path that calls the service role key.

**Fix:**
```typescript
// After line 723:
const sport = VALID_SPORTS.has(activity.sport) ? activity.sport : "all";
// Now both queries use a validated value.
```

---

## Warnings

### WR-01: J6 fix introduces inconsistency — `get_physiology_zones` fetches `zones` field but `getDashboardData` fetches a different column subset

**File:** `workers/mcp-server/src/index.ts:864,1090`
**Issue:** The J6 fix correctly aligns the `WHERE` clause between the two queries. However, `get_physiology_zones` (line 864) uses no `select=` clause, returning all columns, while `getDashboardData` (line 1090) uses `select=discipline,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m,lthr`. This means the dashboard omits `hr_zones_s`, `valid_from`, `valid_to`, and any other columns the table may contain. The deduplication loop in `getDashboardData` (lines 1094-1099) uses `z.discipline`, which is included in both, so dedup works correctly. The real risk is that the dashboard silently shows stale zones if `valid_from`/`valid_to` are needed for the age indicator (the `age_days` field that `get_physiology_zones` computes is also absent in dashboard data). This is a data completeness issue, not a crash, but it means the two "current zones" representations visible to the athlete are structurally different.

**Fix:** Either add `valid_from` to the dashboard `select` clause (allows UI to show age), or document that the dashboard zones view is intentionally minimal.

---

### WR-02: `sleep()` function is defined but never called — dead code

**File:** `workers/mcp-server/src/index.ts:1115`
**Issue:** A `sleep()` helper is defined at the bottom of the file but has no callers. The comment in `forceGarminSync` explicitly explains why polling was removed. This dead function survived the Phase 11 fixes.

**Fix:** Delete lines 1115-1117.

---

### WR-03: OAuth token endpoint uses `!tsNum` to reject timestamp zero — rejects epoch timestamp (Unix epoch 0 is falsy)

**File:** `workers/mcp-server/src/index.ts:356`
**Issue:** The condition `if (!tsNum || ...)` treats `tsNum === 0` as invalid. `Date.now()` never returns 0 in practice, but the real issue is that `parseInt(ts, 10)` returns `NaN` for non-numeric input, and `!NaN` is `true`, so the guard correctly catches that case. The issue is subtler: `parseInt("0", 10)` returns `0`, `!0` is `true`, and the code would return `"code expired or invalid"` for a code whose timestamp is exactly Unix epoch 0 — a non-issue in production but a logic inconsistency that could mask bugs in test fixtures. More importantly, `parseInt` will silently parse a string like `"1234abc"` as `1234`, which could potentially allow a partially-crafted timestamp to pass validation. The HMAC signature would still catch a forged code, so this is defense-in-depth rather than a bypass.

**Fix:**
```typescript
const tsNum = Number(ts);
if (!Number.isFinite(tsNum) || tsNum <= 0 || Date.now() - tsNum > 5 * 60 * 1000) {
```

---

### WR-04: `daysAgoISO` and `daysFromISO` compute in UTC while `todayRomeISO` uses Europe/Rome — boundary skew up to 2 hours

**File:** `workers/mcp-server/src/index.ts:533-543`
**Issue:** `todayRomeISO()` returns the current date in the Europe/Rome timezone (UTC+1 in winter, UTC+2 in summer). `daysAgoISO(n)` and `daysFromISO(n)` subtract/add UTC days using `setUTCDate`. At 23:00 UTC in summer (01:00 Rome), `todayRomeISO()` returns "tomorrow" in Rome time, while `daysAgoISO(7)` returns "7 UTC days ago". The resulting date windows will be shifted by one day relative to what the athlete sees in Rome time. Queries like `planned_sessions?planned_date=gte.${daysAgoISO(7)}&planned_date=lte.${today}` can have a 1-day asymmetry between the lower and upper bounds late at night.

This affects `getWeeklyContext`, `getRaceContext`, `getUpcomingPlan`, `getActivityHistory`, `queryLog`, `getDashboardData`, and `getTechniqueHistory`.

**Fix:**
```typescript
function daysAgoISO(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);  // local time, but Workers run UTC — better to align with todayRomeISO
  // Correct approach: compute based on Rome time
  const romeToday = todayRomeISO();
  const t = new Date(romeToday + "T00:00:00+02:00");  // approximate; or:
  // Use Intl.DateTimeFormat similarly to todayRomeISO but offset by n days
  return t.toISOString().split("T")[0];
}
```
A simpler pattern: compute all date strings relative to `todayRomeISO()` with arithmetic on a `Date` object initialized from that string.

---

## Info

### IN-01: `codeChallenge` parameter read and echoed through callback but serves no function

**File:** `workers/mcp-server/src/index.ts:284,289`
**Issue:** The authorization endpoint reads `code_challenge` and includes it in the form action URL passed to the callback, but the callback endpoint (line 304) does not read or store it. The value is silently dropped. This is consistent with CR-02 (PKCE not implemented) but the forwarding gives a false impression that the parameter is being processed.

**Fix:** Remove `code_challenge` from the forwarded params until PKCE is properly implemented, or implement it (see CR-02).

---

### IN-02: `args.resolved_at` accepted without validation in `updateConstraint`

**File:** `workers/mcp-server/src/index.ts:1012`
**Issue:** `args.resolved_at` is passed directly to Supabase as a `TIMESTAMPTZ` value without format validation. An invalid string (e.g., `"not-a-date"`) will be rejected by PostgreSQL, which will return a 4xx, which is caught by `if (!updateResp.ok)` and thrown as an error. The behavior is safe but the error message will be a raw Supabase error rather than a helpful validation message.

**Fix:**
```typescript
if (args.resolved_at !== undefined) {
  const d = new Date(args.resolved_at);
  if (isNaN(d.getTime())) throw new Error(`Invalid resolved_at: not a valid timestamp`);
}
```

---

_Reviewed: 2026-06-08T15:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
