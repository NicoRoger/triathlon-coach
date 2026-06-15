---
phase: 11-mcp-auth-hardening
plan: 01
subsystem: api
tags: [cloudflare-workers, typescript, mcp, json-rpc]

requires:
  - phase: 05-audit-resilience
    provides: CR-01/CR-02/CR-04/WR-01/WR-03/WR-04 fixes already in workers/mcp-server/src/index.ts
provides:
  - J2: req.json() try-catch → -32700 Parse error on malformed body
  - J3: getRaceContext queries `races` table (not `planned_sessions`)
  - J4: existingResp.ok guard before .json() in commitPlanChange and commitMesocycle
  - J6: getDashboardData physiology_zones query aligned with get_physiology_zones
affects: [11-02-deploy]

tech-stack:
  added: []
  patterns: ["JSON-RPC error response: {jsonrpc:'2.0', id:null, error:{code:-32700, message:'Parse error'}}"]

key-files:
  created: []
  modified:
    - workers/mcp-server/src/index.ts

key-decisions:
  - "Cherry-picked J2/J3/J4/J6 commits onto orchestrator branch (worktree base was stale — pre-Phase 5 fixes)"
  - "TypeScript strict mode: `let rpc: JsonRpcRequest` declared before try-catch to satisfy out-of-scope variable rule"

patterns-established:
  - "JSON-RPC parse error pattern: catch req.json() → status 400 with error code -32700"
  - "Supabase fetch guard: always check resp.ok before calling .json()"

requirements-completed: [MCP-01, MCP-02]

duration: 30min
completed: 2026-06-08
---

# Phase 11-01: MCP Server Bug Fixes (J2/J3/J4/J6) Summary

**Four targeted bug fixes applied to `workers/mcp-server/src/index.ts`: JSON-RPC parse error guard, getRaceContext table correction, Supabase fetch ok-guards, and physiology_zones query alignment — TypeScript compiles clean (exit 0)**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-08T13:29:00Z
- **Completed:** 2026-06-08T13:58:00Z
- **Tasks:** 5
- **Files modified:** 1

## Accomplishments
- J2: `req.json()` wrapped in try-catch — malformed JSON body returns `{code:-32700, message:"Parse error"}` with status 400 instead of unhandled exception
- J3: `getRaceContext` now queries `races` table with `race_date` field — previously queried `planned_sessions?session_type=eq.race` which always returned null for real race dates
- J4: `existingResp.ok` verified before `.json()` in both `commitPlanChange` and `commitMesocycle` — prevents silent failure masking on Supabase 4xx/5xx responses
- J6: `getDashboardData` physiology_zones query updated to `or=(valid_to.is.null,valid_to.gte.${today})&valid_from=lte.${today}` — matches `get_physiology_zones` logic, zones with future valid_to now appear in dashboard
- TypeScript: `npx tsc --noEmit` exits 0 after all changes

## Task Commits

Each task was committed atomically (cherry-picked onto `audit-resilience-2026-06-01`):

1. **Task 1: J2 guard req.json() with try-catch** - `970dc6e` (fix)
2. **Task 2: J3 getRaceContext uses races table** - `4ec59db` (fix)
3. **Task 3: J4 existingResp.ok guard** - `cdcb444` (fix)
4. **Task 4: J6 align getDashboardData zones query** - `22085d2` (fix)
5. **Task 5: TypeScript check** - verified clean, no separate commit needed

## Files Created/Modified
- `workers/mcp-server/src/index.ts` — 4 targeted fixes, ~16 lines changed total

## Decisions Made
- Worktree agent branched from stale base (`7b1dcf4` — pre-Phase 5), so cherry-picked the 4 fix commits onto the orchestrator branch rather than merging the worktree (which would have regressed CR-01/CR-02/WR-01 etc.)
- `let rpc: JsonRpcRequest` declared before try-catch (not `const`) to satisfy TypeScript's definite-assignment rule for out-of-scope usage

## Deviations from Plan

**Worktree base mismatch:** The isolation worktree was forked from an older commit (`7b1dcf4`, DR snapshot 2026-06-05) instead of the current tip (`4498e2c`). All 4 fix commits cherry-picked cleanly onto the correct base with no conflicts.

## Issues Encountered
- Worktree base stale — resolved by cherry-pick (all patches applied cleanly, zero conflicts)

## Next Phase Readiness
- `workers/mcp-server/src/index.ts` ready for deploy — all J1-J6 fixes present
- Plan 02: `wrangler deploy` from `workers/mcp-server/` → Cloudflare

---
*Phase: 11-mcp-auth-hardening*
*Completed: 2026-06-08*
