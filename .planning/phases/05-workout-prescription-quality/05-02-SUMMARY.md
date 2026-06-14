---
phase: 05-workout-prescription-quality
plan: "02"
subsystem: mcp-worker
tags: [mcp, cloudflare-worker, age_days, active_constraints, update_constraint, progression_plan, WORKOUT-02, WORKOUT-03, WORKOUT-04, WORKOUT-05]
dependency_graph:
  requires:
    - migrations/2026-06-07-workout-prescription-quality.sql (Plan 01 — active_constraints table + progression_plan column)
  provides:
    - workers/mcp-server/src/index.ts (extended with age_days, active_constraints, current_progression_step, update_constraint, progression_plan)
  affects:
    - Claude.ai MCP connector (all tools updated live)
    - skills/fitness_test.md (can now read age_days to check FTP freshness D-06)
    - skills/propose_session.md (can now read active_constraints for constraint-aware prescriptions D-15/D-16)
tech_stack:
  added: []
  patterns:
    - age_days computed from valid_from (DATE as UTC midnight, integer floor diff)
    - Promise.all 12-element destructuring extension
    - deriveProgressionStep pure helper (null-safe graceful return)
    - isUuid guard (ASVS V5) before PATCH fetch
    - Supabase REST PATCH with Prefer=return=representation
    - .catch(() => []) for graceful fallback on missing table
key_files:
  created: []
  modified:
    - workers/mcp-server/src/index.ts
decisions:
  - "age_days uses new Date(todayRomeISO()) minus new Date(valid_from) — both parse as UTC midnight so difference is exact integer days (Pitfall 1 in RESEARCH.md)"
  - "deriveProgressionStep returns null (not throws) when mesocycle or progression_plan or start_date are absent — Pitfall 6 in RESEARCH.md"
  - "active_constraints query wrapped in .catch(() => []) after initial commit to handle graceful fallback when table migration is not yet applied (deviation Rule 1 fix)"
  - "update_constraint validates UUID via existing isUuid() helper before PATCH fetch — T-05-03 mitigated (ASVS V5 Input Validation)"
metrics:
  duration_s: null
  completed_date: "2026-06-08"
  tasks_completed: 3
  tasks_total: 3
  files_created: 0
  files_modified: 1
---

# Phase 05 Plan 02: MCP Worker Extension Summary

Wave 2 MCP Worker extension — age_days per physiology zone, active_constraints + current_progression_step in weekly context, update_constraint tool with UUID guard, progression_plan persisted in commit_mesocycle, Worker deployed live.

## One-liner

Worker MCP `index.ts` esteso con 5 nuovi campi/tool: `age_days` per zona fisiologica (da `valid_from`), `active_constraints` (vincoli medici attivi da DB), `current_progression_step` (derivato da `mesocycles.progression_plan`), tool `update_constraint` con guard UUID (ASVS V5), fix `commit_mesocycle` per persistere `progression_plan` — deployato live (Version ID: e4129eec-def7-4f03-9c29-c5bfd453f2ea).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | get_physiology_zones age_days + commit_mesocycle progression_plan | d82e58c | workers/mcp-server/src/index.ts |
| 2 | get_weekly_context active_constraints + current_progression_step + update_constraint | 18192ff | workers/mcp-server/src/index.ts |
| Fix | active_constraints query wrapped in .catch(() => []) for graceful fallback | ee387ef | workers/mcp-server/src/index.ts |
| 3 | wrangler deploy — Worker live | (human) | Version ID: e4129eec-def7-4f03-9c29-c5bfd453f2ea |

## Artifacts Produced

### workers/mcp-server/src/index.ts — changes

**get_physiology_zones: age_days field**

- After building the `current` zones array, computes `age_days` per zone.
- `todayDate = new Date(todayRomeISO())` — both strings are "YYYY-MM-DD" parsing as UTC midnight.
- `zone.age_days = Math.max(0, Math.floor((todayDate.getTime() - new Date(zone.valid_from).getTime()) / (1000*60*60*24)))` when `valid_from` present; `null` otherwise.
- Live verification: `get_physiology_zones('run')` returned `age_days: 9`.

**commit_mesocycle: progression_plan persisted**

- Added `if (args.progression_plan !== undefined) payload.progression_plan = args.progression_plan;` following the existing conditional pattern for optional fields.
- TOOLS entry `commit_mesocycle` updated with `progression_plan` in `inputSchema.properties` (not in `required`).

**deriveProgressionStep pure helper**

- Returns `null` when mesocycle, progression_plan, or start_date are absent (null-safe).
- Otherwise computes `weekNumber` from `start_date` delta and maps `progression_plan[sessionType]['week'+weekNumber]` to steps.

**get_weekly_context: 2 new fields**

- Promise.all extended to 12 elements — 12th query: `active_constraints?resolved_at=is.null&order=created_at.asc`.
- Return object extended: `active_constraints: constraints || []` and `current_progression_step: deriveProgressionStep(mesocycles?.[0] || null, today)`.
- Query wrapped in `.catch(() => [])` for graceful fallback (deviation fix ee387ef).
- Live verification: 2 active constraints present (spalla dx + fascite plantare), `current_progression_step: null` (correct — no mesocycle with progression_plan yet).

**update_constraint tool (new)**

- TOOLS array entry: `update_constraint` with `required: ["id"]`, accepts optional `resolved_at`.
- callTool switch case added before `default:`.
- Implementation: UUID validation via `isUuid(args.id)` BEFORE any fetch — throws `Invalid constraint id: must be a valid UUID` if check fails (T-05-03 mitigated).
- PATCH to `active_constraints?id=eq.${args.id}` with `Prefer: return=representation`.
- Returns `{ status: "resolved", id, resolved_at }`.

## Verification Results

```
npx tsc --noEmit → no errors (Tasks 1 and 2)

wrangler deploy output:
  Current Deployment ID: e4129eec-def7-4f03-9c29-c5bfd453f2ea

Live MCP verification (Claude.ai):
  get_physiology_zones('run') → age_days: 9 ✅
  get_weekly_context → active_constraints: [2 entries] ✅
  get_weekly_context → current_progression_step: null (correct) ✅
```

## Success Criteria

- [x] index.ts esteso, tsc pulito
- [x] Worker deployato live con i nuovi campi/tool verificabili da Claude.ai
- [x] update_constraint valida UUID prima della query

## Must-Have Truths Verified

- [x] `get_physiology_zones` espone `age_days` per ogni disciplina (calcolato da `valid_from`) — age_days=9 per 'run'
- [x] `get_weekly_context` restituisce `active_constraints` (resolved_at IS NULL) come array — 2 vincoli attivi
- [x] `get_weekly_context` restituisce `current_progression_step` derivato da mesocycles.progression_plan — null (corretto, nessun mesociclo ha progression_plan)
- [x] Esiste il tool `update_constraint(id, resolved_at)` che valida l'UUID prima della PATCH
- [x] `commit_mesocycle` persiste `progression_plan` (non più ignorato silenziosamente)
- [x] Il Worker aggiornato è live via wrangler deploy (Version ID: e4129eec-def7-4f03-9c29-c5bfd453f2ea)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] active_constraints query fallback on missing table**

- **Found during:** Post-commit testing (between Task 2 and human checkpoint)
- **Issue:** The new `active_constraints` query in the 12-element Promise.all had no error handling. If the migration has not yet been applied to Supabase, the query throws and crashes the entire `getWeeklyContext` response.
- **Fix:** Wrapped the query fetch in `.catch(() => [])` so `constraints` falls back to `[]` gracefully, consistent with the defensive pattern used elsewhere in the Promise.all chain.
- **Files modified:** workers/mcp-server/src/index.ts
- **Commit:** ee387ef

## Known Stubs

None. All fields are wired to live DB data: `age_days` from `physiology_zones.valid_from`, `active_constraints` from DB table, `current_progression_step` from `mesocycles.progression_plan`. `current_progression_step` returning `null` is correct behavior (not a stub) — it means no active mesocycle has a `progression_plan` set yet; will be populated when Plan 03 skill prompts guide the athlete through `commit_mesocycle`.

## Threat Flags

None. No new network endpoints or auth paths beyond those described in the plan's threat model. All threats mitigated as planned:

- T-05-03 (Tampering via update_constraint id): mitigated via `isUuid()` guard before PATCH.
- T-05-04 (SQL injection via resolved_at): not applicable — Supabase REST with URL-encoded params and JSON body, no raw SQL.
- T-05-05 (Elevation of Privilege — constraint resolution): accepted (single-user system behind same auth).

## Self-Check: PASSED

- [x] workers/mcp-server/src/index.ts: FOUND (modified)
- [x] Commit d82e58c: FOUND (Task 1 — age_days + progression_plan)
- [x] Commit 18192ff: FOUND (Task 2 — active_constraints + update_constraint)
- [x] Commit ee387ef: FOUND (Fix — .catch fallback)
- [x] Worker live: Version ID e4129eec-def7-4f03-9c29-c5bfd453f2ea (human-verified)
