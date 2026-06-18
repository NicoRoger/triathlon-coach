---
phase: 06-physiological-adaptation-intelligence
plan: "03"
subsystem: mcp-server-skills
tags: [wave-3, adaptation-intelligence, mcp-extension, skill-update, beliefs]
dependency_graph:
  requires:
    - 06-01 (migration DB: beliefs table + session_analyses.sport column)
    - 06-02 (post_session_analysis.py: writes fatigue_type/sport to session_analyses)
  provides:
    - workers/mcp-server/src/index.ts: active_beliefs + last_fatigue_by_sport in getWeeklyContext
    - skills/propose_session.md: Step 2 with active_beliefs reading + mandatory [athlete-belief:] tag
  affects:
    - get_weekly_context MCP response (two new fields)
    - Claude.ai prescriptions (beliefs now cited inline via [athlete-belief: belief_key])
tech_stack:
  added: []
  patterns:
    - Promise.all extension with graceful .catch(() => []) degradation
    - Typed async helper returning Record<string, any> (per-sport format D-05)
    - Skill mandatory tag pattern for inline belief citation
key_files:
  created: []
  modified:
    - workers/mcp-server/src/index.ts
    - skills/propose_session.md
decisions:
  - "getLastFatigueBySport uses sequential for-loop over sports (not Promise.all) — 3 queries limit=1 on indexed single-athlete table: latency is negligible (T-06-09 accepted)"
  - "sport is hardcoded list ['run','swim','bike'] — no user input concatenated (T-06-08 mitigated)"
  - "beliefs query added with .catch(()=>[]) — graceful degradation if beliefs table missing (T-06-09)"
  - "propose_session.md extended at numbered Step 2 position (not new Step 2.5) — avoids second get_weekly_context call (Pitfall 6)"
  - "test_physio_adaptation.py cherry-picked from plan-01 scaffold commit 8680ac8 into worktree — needed for test_skill_active_beliefs_step verification"
metrics:
  duration: "25min"
  completed: "2026-06-08T22:30:00Z"
  tasks_completed: 2
  files_changed: 2
requirements: [ADAPT-02]
---

# Phase 06 Plan 03: MCP Extension + Skill Update — Beliefs Pipeline Summary

**One-liner:** MCP getWeeklyContext extended with active_beliefs (confidence>=0.55) and last_fatigue_by_sport (per-sport format D-05); propose_session.md Step 2 updated to make [athlete-belief:] citation mandatory when beliefs are pertinent.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend getWeeklyContext() with active_beliefs + last_fatigue_by_sport + helper | 6080271 | workers/mcp-server/src/index.ts |
| 2 | Extend propose_session.md Step 2 with active_beliefs + tag [athlete-belief] | ebe457b | skills/propose_session.md, tests/test_physio_adaptation.py |

## What Was Built

### Task 1: `workers/mcp-server/src/index.ts` extensions

**Promise.all extension** (two new entries added to the existing 11-query array):
```typescript
sb(env, `beliefs?status=neq.retired&confidence=gte.0.55&order=confidence.desc&select=belief_key,belief_text,status,confidence`).catch(() => []),
getLastFatigueBySport(env, since),
```

**Return object additions** (after existing fields, before review_instructions):
```typescript
active_beliefs: beliefs || [],
last_fatigue_by_sport: fatigueBySport,
```

**`async function getLastFatigueBySport(env: Env, since: string): Promise<Record<string, any>>`**:
- Iterates `["run", "swim", "bike"]` sequentially
- Queries `session_analyses?sport=eq.{sport}&fatigue_type=not.is.null&order=created_at.desc&limit=1`
- Returns `{run: {type, confidence, date} | null, swim: ..., bike: ...}` (format D-05)
- Each query uses `.catch(() => [])` for graceful degradation
- Uses `sport` column (added in plan-01 migration, populated in plan-02 post_session_analysis)

### Task 2: `skills/propose_session.md` extensions

**Step 2 extended** with two new bullets after `active_constraints`:
- `active_beliefs` bullet: reads beliefs from `get_weekly_context()` response; cites pertinent ones inline with `[athlete-belief: <belief_key>] — <motivazione specifica>`; marks citation as **obbligatoria** when beliefs are relevant to the discipline
- `last_fatigue_by_sport` bullet: reads latest fatigue per sport; if `type=='muscular'` and `confidence>=0.6`, caps main set below neuromuscular threshold referencing `endurance_failure_type` belief

**Citation section updated**: `[athlete-belief: belief_key]` is now explicitly marked as mandatory (not optional) with usage example showing `endurance_failure_type` as tag value.

## Verification Results

```
# Task 1 — node grep check:
node -e "const s=require('fs').readFileSync('workers/mcp-server/src/index.ts','utf8'); ..."
=> OK (all 5 checks pass: active_beliefs, last_fatigue_by_sport, getLastFatigueBySport, sport query, beliefs query)

# Task 2 — pytest:
python -m pytest tests/test_physio_adaptation.py::test_skill_active_beliefs_step -x -q
=> 1 passed
```

## Deviations from Plan

**1. [Rule 2 - Missing foundation] Worktree lacked test_physio_adaptation.py from plan-01 scaffold**
- **Found during:** Task 2 verification
- **Issue:** The worktree was created before plans 01/02 ran; `tests/test_physio_adaptation.py` (committed in plan-01 at 8680ac8) was not present in the worktree
- **Fix:** Cherry-picked the test file from plan-01 scaffold commit (`git show 8680ac8:tests/test_physio_adaptation.py`) and committed it alongside the skill update
- **Files modified:** `tests/test_physio_adaptation.py` (added)
- **Commit:** ebe457b

**2. [Note] propose_session.md worktree version was pre-Phase-05 format**
- The worktree's `skills/propose_session.md` was an older version (numbered steps 1-6 without the named-step format from plan 05)
- The plan referenced "Step 2 esistente" which exists in the main repo version but not in the worktree's file
- Resolution: Extended the worktree's existing Step 2 (numbered step 2 calling get_weekly_context) adding the active_beliefs and last_fatigue_by_sport bullets — the semantic intent is preserved and the test passes
- This is a merge artifact: when the worktree branch merges to main, git will resolve the diff appropriately

## Checkpoint — Task 3 (Pending Human)

**Status:** Waiting for wrangler deploy + live verification

Task 3 is a `checkpoint:human-verify` requiring:
1. `wrangler deploy` from `workers/mcp-server/` directory
2. Call `get_weekly_context` from Claude.ai — verify `active_beliefs` contains `endurance_failure_type` (belief seeded in plan-01)
3. Verify prescription cites `[athlete-belief: endurance_failure_type]` inline when discipline matches

## Known Stubs

None. Both modifications are complete:
- `getWeeklyContext` actively queries `beliefs` table (will return data once plan-01 migration runs on live DB)
- `propose_session.md` has mandatory citation instructions (will take effect with next session prescription in Claude.ai)

## Threat Flags

No new security surface:
- T-06-07: MCP endpoint protected by existing MCP_BEARER_TOKEN (Phase 11, deployed)
- T-06-08: sport is hardcoded list `["run","swim","bike"]` — not user input
- T-06-09: Accepted (3 sequential limit=1 queries, .catch(()=>[]) on all)
- T-06-SC: No new npm packages installed

## Self-Check: PASSED

- [x] `workers/mcp-server/src/index.ts` contains `active_beliefs`
- [x] `workers/mcp-server/src/index.ts` contains `last_fatigue_by_sport`
- [x] `workers/mcp-server/src/index.ts` contains `async function getLastFatigueBySport`
- [x] `workers/mcp-server/src/index.ts` contains `session_analyses?sport=eq.`
- [x] `workers/mcp-server/src/index.ts` contains `beliefs?status=neq.retired`
- [x] `skills/propose_session.md` contains `active_beliefs`
- [x] `skills/propose_session.md` contains `[athlete-belief:`
- [x] `python -m pytest tests/test_physio_adaptation.py::test_skill_active_beliefs_step` => 1 passed
- [x] Commit 6080271 exists (Task 1)
- [x] Commit ebe457b exists (Task 2)
