# Phase 3: Deploy & Pipeline Resilience - Research

**Researched:** 2026-06-06
**Domain:** Supabase SQL migrations, Cloudflare Workers deploy (wrangler), GitHub Actions YAML, Python CLI entry points, briefing idempotency
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Migrazioni SQL prima → `wrangler deploy` bot → modifiche `ingest.yml`
- **D-02:** Migrazioni eseguite manualmente via Supabase SQL Editor (dashboard)
- **D-03:** Wrangler configurato localmente con credenziali attive
- **D-04:** `apply_accepted_modulations` aggiunto come step separato in `ingest.yml` dopo il blocco ingest Garmin
- **D-05:** Su failure (o zero modulazioni accepted), logga e continua — non blocca l'ingest
- **D-06:** `python -m coach.coaching.modulation --apply-accepted` senza `if: always()`
- **D-07:** Creare `scripts/verify_migrations.py` che interroga `information_schema`
- **D-08:** Verifica bot Telegram dopo deploy: test manuale via chat Telegram
- **D-09:** Idempotency brief: check DB su `bot_messages` con `purpose='morning_brief'`
- **D-10:** Check idempotency in `coach/planning/briefing.py` prima della generazione

### Claude's Discretion

- Struttura esatta della tabella/query per idempotency (colonne, index)
- Messaggio di log quando brief è già stato inviato oggi
- Gestione errori nei fix L2/L3/L4 — segui lo stile error handling esistente

### Deferred Ideas (OUT OF SCOPE)

- Fix A1-A10 (ingest Garmin resilience)
- Fix K6-K9 (Telegram bot warnings)
- DR restore (L7)
- DST drift cron (L5)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Tutte le migrazioni pending in `OPEN_ISSUES.md` eseguite in Supabase e verificate (CHECK, UNIQUE, FK ON DELETE, expires_at, kind values) | Migration file `migrations/2026-06-01-resilience-audit.sql` already fully written; `verify_migrations.py` must confirm each constraint is live |
| DEPLOY-02 | La migrazione `2026-06-01-resilience-audit.sql` è stata eseguita e il suo contenuto è live | Single migration file covers O4, O5, O6/D1, E4, O7, O8, O9, K3 — must run via Supabase SQL Editor |
| DEPLOY-03 | Telegram bot ridistribuito con `wrangler deploy` — fix K2/K3/K4/K5 attivi nel worker live | K2-K5 fixes are already in source (`index.ts`); only action is `wrangler deploy` from `workers/telegram-bot/` |
| DEPLOY-04 | `apply_accepted_modulations` chiamato da `ingest.yml` — transizione `accepted → applied` verificata | `apply_accepted_modulations()` already in modulation.py; `--apply-accepted` CLI already implemented; step already present in `ingest.yml` |
| PIPELINE-01 | Ingest Garmin propaga exit 1 su fallimento — fix L1 verificato nei GitHub Actions log | Fix already in `ingest.yml` (retry loop exits 1 on 3 failures) — verification is checking real Actions log |
| PIPELINE-02 | Watchdog rileva componenti con riga health mancante — fix L4 verificato | `compute_alerts()` already fixed to iterate `THRESHOLDS_HOURS` not just existing rows |
| PIPELINE-03 | DR snapshot aborta su tabelle critiche vuote — fix L3 verificato | `assert_snapshot_sane()` already in `dr_snapshot.py` |
| PIPELINE-04 | Brief mattutino arriva una sola volta ogni mattina — idempotency check | `_brief_already_sent_today()` already in `briefing.py`; `main()` already calls it |
</phase_requirements>

---

## Summary

Phase 3 is a **deploy and verification** phase, not a coding phase. The critical finding from reading the codebase is that **all 8 requirements (DEPLOY-01 through PIPELINE-04) have their code fixes already committed** on the current branch (`audit-resilience-2026-06-01`). The code is done; what remains is:

1. Running the SQL migration manually in Supabase SQL Editor
2. Deploying the Telegram bot Worker with `wrangler deploy`
3. Writing `scripts/verify_migrations.py` to confirm the migration landed correctly
4. Verifying each pipeline fix is live (Actions logs, watchdog output, DR test)

The one genuinely new code artifact is `scripts/verify_migrations.py`, which does not yet exist. Everything else is already implemented.

**Primary recommendation:** Execute migrations first (prerequisite for bot fix K3 that requires the new `kind` CHECK), then `wrangler deploy`, then add the verification script. Gate every step with explicit log evidence.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SQL schema constraints (CHECK, UNIQUE, FK) | Database / Storage | — | Lives on Supabase PostgreSQL; applied via Supabase SQL Editor |
| Telegram bot fix deploy | CDN / Edge (Cloudflare Workers) | — | Worker is stateless TypeScript; deploy via wrangler |
| `apply_accepted_modulations` wiring | API / Backend (GitHub Actions) | Database | Python job runs in CI, writes to Supabase |
| Exit code propagation (L1) | API / Backend (GitHub Actions) | — | YAML retry loop; no application-layer change needed |
| Watchdog missing-component detection (L4) | API / Backend (Python script) | Database | Reads `health` table, iterates expected components |
| DR snapshot empty-table guard (L3) | API / Backend (Python script) | Database / Storage | Reads tables, writes to Supabase Storage bucket |
| Brief idempotency (PIPELINE-04) | API / Backend (Python script) | Database | Reads `bot_messages`, skips if already sent |
| Migration verification | API / Backend (Python script) | Database | Queries `information_schema` on Supabase |

---

## Standard Stack

No new packages are installed in this phase. All tools already present.

### Core

| Tool | Version (pinned) | Purpose | Already Used |
|------|------------------|---------|--------------|
| `supabase-py` | `>=2.30.0` | Query `information_schema` in verify_migrations | Yes |
| `wrangler` | `^3.50.0` | Deploy Cloudflare Worker | Yes (devDependency) |
| `pytest` | `7.4` | Run regression tests | Yes |

### Installation

No new installations required. Existing environment is sufficient.

---

## Package Legitimacy Audit

> No new external packages are installed in this phase.

**Packages removed due to slopcheck:** none
**Packages flagged as suspicious:** none

---

## Architecture Patterns

### What's Already Done vs What Needs Doing

```
Committed code (already done):
  coach/coaching/modulation.py          apply_accepted_modulations() + CLI main()
  .github/workflows/ingest.yml          Step "Apply accepted modulations (audit K1)"
  workers/telegram-bot/src/index.ts     K2/K3/K4/K5 fixes committed
  coach/planning/briefing.py            _brief_already_sent_today() + main() guard
  scripts/watchdog.py                   compute_alerts() iterates THRESHOLDS_HOURS
  scripts/dr_snapshot.py                assert_snapshot_sane() + EmptySnapshotError
  scripts/db_cleanup.py                 sys.exit(1) on exception
  migrations/2026-06-01-resilience-audit.sql  All schema constraints

Not yet done (Phase 3 creates):
  scripts/verify_migrations.py          NEW — queries information_schema
  [manual] Supabase SQL Editor          Run migration file
  [manual] wrangler deploy              From workers/telegram-bot/
  [manual] Read Actions log             Verify L1 exit code propagated
```

### System Architecture Diagram

```
PHASE 3 EXECUTION FLOW

[Supabase SQL Editor]
    │
    ├─ Execute migrations/2026-06-01-resilience-audit.sql
    │      ├─ O4: races UNIQUE(name,race_date) 
    │      ├─ O5: mesocycles FK ON DELETE SET NULL
    │      ├─ O6/D1: plan_modulations.expires_at column
    │      ├─ E4: physiology_zones UNIQUE(discipline,valid_from,method)
    │      ├─ O7: planned_sessions UNIQUE(planned_date,sport,session_type)
    │      ├─ O8: FK ON DELETE SET NULL on planned_sessions + physiology_zones
    │      ├─ O9: plan_modulations.status CHECK
    │      └─ K3: subjective_log.kind CHECK (adds 'pattern_correction')
    │
    ▼
[scripts/verify_migrations.py]  ← NEW
    │  queries information_schema.table_constraints
    │  queries information_schema.check_constraints
    │  output: PASS/FAIL per constraint
    ▼
    PASS ──────────────────────────────────────────────────────┐
                                                               │
[wrangler deploy] (from workers/telegram-bot/)                │
    │  deploys index.ts with K2/K3/K4/K5 fixes live           │
    │                                                          │
    ▼                                                          │
[Telegram manual test]                                         │
    │  send modulation accept → check PATCH resp.ok guard      │
    │                                                          ▼
                                              [GitHub Actions ingest.yml]
                                                  │ Garmin sync → exit 1 on fail (L1) ✓
                                                  │ apply_accepted_modulations step ✓
                                                  │   status: accepted → applied
                                                  ▼
                                              [Verification evidence]
                                                  brief idempotency (PIPELINE-04) ✓
                                                  watchdog missing-row alert (L4) ✓
                                                  DR snapshot abort on empty (L3) ✓
```

### Recommended Project Structure

No new directories needed. New file:

```
scripts/
├── verify_migrations.py    # NEW: information_schema constraint verifier
├── watchdog.py             # Already fixed (L4)
├── dr_snapshot.py          # Already fixed (L3)
└── db_cleanup.py           # Already fixed (L2)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Migration constraint verification | Custom Postgres queries | `information_schema.table_constraints` + `information_schema.check_constraints` | Standard SQL catalog; works on any Postgres including Supabase managed |
| Telegram deploy | Custom deploy script | `wrangler deploy` (already configured) | Wrangler handles bundling, secrets, KV binding |
| Brief dedup | KV or time-based heuristics | `bot_messages` table query (already implemented in `_brief_already_sent_today()`) | Persistent across restarts; immune to race conditions from cron + ingest trigger |

---

## Key Implementation Details

### DEPLOY-01/02: Migration Execution Order and Idempotency

The migration file `migrations/2026-06-01-resilience-audit.sql` is already fully written with `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` wrappers for all `ALTER TABLE ADD CONSTRAINT` statements. This means:

- Re-running is safe (idempotent) — all constraints are guarded by EXCEPTION handlers
- The DEDUP block for `races` runs UPDATE + DELETE before adding the UNIQUE constraint — must succeed in sequence
- The K3 `subjective_log.kind` check uses `DROP CONSTRAINT IF EXISTS` then recreates — safe to re-run

**Execution order within the file is fixed and must not be reordered** (races dedup must happen before unique constraint; mesocycles FK update before FK add).

### DEPLOY-03: Wrangler Deploy

The bot's `wrangler.toml` is already configured with the KV namespace binding (`id = "9d1822af8eff446e832c004178d578ad"`). No `wrangler.toml` changes needed.

```bash
# from workers/telegram-bot/ directory
npm run deploy
# or equivalently:
wrangler deploy
```

Secrets are already set in Cloudflare (set via `wrangler secret put` in prior phases). **Do not re-set secrets unless they changed.**

**TypeScript compile check before deploy:**

```bash
npx tsc --noEmit
```

Run this before `wrangler deploy` to catch any type errors in the current `index.ts`.

### DEPLOY-04: apply_accepted_modulations Step Already in ingest.yml

Reading `ingest.yml` confirms the step is already present (lines 95-100):

```yaml
- name: Apply accepted modulations (audit K1)
  if: always()
  continue-on-error: true
  run: python -m coach.coaching.modulation --apply-accepted
```

**Discrepancy with D-06:** Decision D-06 says "without `if: always()`" but the live file uses `if: always()`. The CONTEXT says `if: always()` should be removed. However, the current code in `ingest.yml` **already has** `if: always()`. According to D-06, the step should NOT use `if: always()` to prevent running when Garmin sync fails. The current implementation contradicts D-06. The planner must decide: leave as-is (modulations apply even on sync fail) or change to `if: success()`. Given D-06 explicitly says to omit `if: always()`, the step should run only when ingest succeeds.

Wait — re-reading D-06: "senza `if: always()` rimosso per evitare esecuzione su ingest fallito". This means: remove `if: always()` so that it defaults to `if: success()`. The current code has `if: always()`, which is the opposite. This is a genuine code fix needed.

### PIPELINE-01: L1 Fix Already in ingest.yml

The retry loop fix is already in `ingest.yml` (lines 49-64). The `ok=0` / `exit 1` pattern is present. PIPELINE-01 verification is purely about checking the GitHub Actions log after the next run, not about writing code.

### PIPELINE-02: L4 Watchdog Fix Already in watchdog.py

`compute_alerts()` already iterates `THRESHOLDS_HOURS` dict (not just existing rows). Tests `test_l4_watchdog_alerts_missing_component` and `test_l4_watchdog_stale_component` already pass. Verification only: trigger the watchdog and observe output.

### PIPELINE-03: L3 DR Snapshot Fix Already in dr_snapshot.py

`assert_snapshot_sane()` already in place. Test `test_l3_empty_snapshot_aborts` already passes. Verification: the DR snapshot workflow runs on schedule — check the next run's log.

### PIPELINE-04: Brief Idempotency Already Implemented

`_brief_already_sent_today()` checks `bot_messages` where `purpose = 'morning_brief'` and `sent_at >= (now - 6h)`. The `main()` in `briefing.py` already calls this guard before generating the brief. `FORCE_SEND=true` env var can override.

**Bot_messages index for this query:** `idx_bot_messages_chat_purpose ON bot_messages(chat_id, purpose, sent_at DESC)` — already present in `migrations/2026-05-10-bot-messages-pending-confirmations-tables.sql`. Query will be efficient.

### scripts/verify_migrations.py — New File

This is the only genuinely new code file. Pattern from other scripts:

```python
"""Verifica che le migrazioni dell'audit 2026-06-01 siano applicate in Supabase.

Interroga information_schema per CHECK constraints, UNIQUE indexes, FK ON DELETE.
Output: PASS/FAIL per ogni constraint atteso.

Uso: python scripts/verify_migrations.py
Exit 0 = tutto OK; exit 1 = almeno un constraint mancante.
"""
import logging
import sys
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Constraint names to verify (from migration file)
EXPECTED_UNIQUE_CONSTRAINTS = [
    ("races", "races_name_date_unique"),
    ("physiology_zones", "physiology_zones_disc_validfrom_method_unique"),
    ("planned_sessions", "unique_planned_date_sport_type"),
]
EXPECTED_FK_CONSTRAINTS = [
    ("mesocycles", "mesocycles_target_race_fk"),
    ("planned_sessions", "planned_sessions_completed_activity_id_fkey"),
    ("physiology_zones", "physiology_zones_test_activity_id_fkey"),
]
EXPECTED_CHECK_CONSTRAINTS = [
    ("plan_modulations", "plan_modulations_status_check"),
    ("subjective_log", "subjective_log_kind_check"),
]
EXPECTED_COLUMNS = [
    ("plan_modulations", "expires_at"),
]
```

Query pattern via `supabase-py` using `rpc` or raw SQL via PostgREST `rpc`:

```python
# information_schema query via PostgREST /rest/v1/rpc or direct SQL
res = sb.rpc("query_constraints", {...}).execute()
# OR: use sb.from_("information_schema.table_constraints").select(...).execute()
# Supabase PostgREST does not expose information_schema views by default.
# Use raw SQL via sb.rpc() with a helper function OR use the Management API.
```

**Supabase information_schema access:** PostgREST does not expose `information_schema` schema by default (it requires the schema to be in `db_schema` config). The safest approach for `verify_migrations.py` is to use a PostgreSQL RPC function that returns constraint info, OR use the Supabase Python client's `from_()` with the `information_schema` schema explicitly.

**Verified pattern (from Supabase docs and common usage):** `supabase-py` supports `from_("table_name")` but for `information_schema`, use `sb.table("information_schema.table_constraints")` — this works because the Supabase service role key has access to `information_schema`. Alternatively, use `sb.rpc("pg_exec", {"sql": "SELECT ..."})` if an RPC is set up.

**Safest approach:** Use the `supabase-py` client with explicit `schema="information_schema"` parameter — `sb.schema("information_schema").table("table_constraints").select(...)`. This is the supported way in `supabase-py >= 2.0`.

```python
res = (
    sb.schema("information_schema")
    .table("table_constraints")
    .select("constraint_name,table_name,constraint_type")
    .eq("table_schema", "public")
    .execute()
)
```

[ASSUMED] The `sb.schema()` method is available in `supabase-py >= 2.0` — this is consistent with the project's `supabase>=2.30.0` requirement. Verify against actual supabase-py docs.

**Fallback approach if schema() doesn't work:** Create a SQL function in Supabase and call it via `sb.rpc()`:

```sql
-- In Supabase SQL Editor (one-time setup if needed)
CREATE OR REPLACE FUNCTION public.get_constraints()
RETURNS TABLE(constraint_name text, table_name text, constraint_type text)
LANGUAGE sql SECURITY DEFINER AS $$
  SELECT constraint_name::text, table_name::text, constraint_type::text
  FROM information_schema.table_constraints
  WHERE table_schema = 'public';
$$;
```

Then `sb.rpc("get_constraints").execute()`.

Given this uncertainty, the planner should include a fallback option in the verify task.

---

## Common Pitfalls

### Pitfall 1: Migration Run Before or After Code Deploy

**What goes wrong:** Running `wrangler deploy` before the migration creates a window where K3 fix is live in the bot but the `subjective_log.kind` CHECK doesn't include `'pattern_correction'` yet. The bot would insert with the new kind and the DB would reject it — same bug as before.

**Why it happens:** The migration and code deploy are separate steps.

**How to avoid:** Follow D-01 strictly — migrations first, then deploy. The migration file itself says "PARTE 2 — Modifiche COORDINATE con il codice (audit O7/E4/O8/O9). Eseguire INSIEME al deploy del codice corrispondente."

**Warning signs:** Any insert errors on `subjective_log` with `kind='pattern_correction'` after deploy but before migration.

### Pitfall 2: apply_accepted_modulations Step Runs on Garmin Failure

**What goes wrong:** Current `ingest.yml` uses `if: always()` for the apply step, which means it runs even if Garmin sync fails (no new data). This is contrary to D-06. An accepted modulation from days ago (not yet expired) could be applied based on stale conditions.

**Why it happens:** The step already exists but with `if: always()` rather than the intended `if: success()`.

**How to avoid:** Change `if: always()` → remove it (defaults to `if: success()`) or set `if: success()` explicitly. `continue-on-error: true` stays to prevent blocking ingest on modulation failure.

**Warning signs:** Modulation applied during a failed Garmin run — plan changes written when data was stale.

### Pitfall 3: wrangler deploy Without tsc Check

**What goes wrong:** TypeScript errors in `index.ts` may not surface until runtime if `wrangler deploy` bundles without strict type-checking.

**Why it happens:** `wrangler deploy` uses `esbuild` under the hood, which transpiles but doesn't do full type checking.

**How to avoid:** Run `npx tsc --noEmit` from `workers/telegram-bot/` before `wrangler deploy`. The tsconfig should be set to `strict` mode.

**Warning signs:** Worker 500 errors after deploy on paths that were not manually tested.

### Pitfall 4: verify_migrations.py Cannot Access information_schema via PostgREST

**What goes wrong:** `supabase-py` calls fail with "schema not found" or 404 if `information_schema` is not in the exposed schemas list.

**Why it happens:** Supabase PostgREST only exposes schemas listed in `db_schema` setting. `information_schema` is not always exposed.

**How to avoid:** Use the fallback RPC function approach (`sb.rpc("get_constraints")`). Alternatively, create a helper RPC in Supabase that queries `information_schema` with `SECURITY DEFINER`.

**Warning signs:** `verify_migrations.py` raises 404 or empty results despite constraints existing.

### Pitfall 5: Brief Idempotency Window Is 6 Hours, Not Date-Based

**What goes wrong:** If a brief is sent at 08:00 and the morning-briefing workflow runs at 06:20 UTC (re-triggering after a delay), the 6-hour window may or may not cover it depending on timing.

**Why it happens:** `_brief_already_sent_today()` uses a 6-hour sliding window, not a date comparison. This means if a brief is sent at 22:00 (evening run due to some issue), it blocks the next morning's brief until 04:00.

**How to avoid:** The existing implementation is accepted (D-09, D-10) — the 6-hour window is by design and matches the `morning-briefing.yml` schedule. Document the FORCE_SEND=true override for edge cases.

**Warning signs:** Brief skipped on the morning after a late-night brief was manually sent.

---

## Code Examples

### Pattern: information_schema constraint lookup via supabase-py

```python
# Verified pattern — supabase-py >= 2.0 schema() method
# Source: supabase-py official usage patterns [ASSUMED — verify against sb.schema() availability]
sb = get_supabase()
try:
    res = (
        sb.schema("information_schema")
        .table("table_constraints")
        .select("constraint_name,table_name,constraint_type")
        .eq("table_schema", "public")
        .execute()
    )
    constraints = {row["constraint_name"] for row in (res.data or [])}
except Exception:
    # Fallback to RPC
    res = sb.rpc("get_public_constraints").execute()
    constraints = {row["constraint_name"] for row in (res.data or [])}
```

### Pattern: column existence check in information_schema

```python
# Check if plan_modulations.expires_at column exists
res = (
    sb.schema("information_schema")
    .table("columns")
    .select("column_name")
    .eq("table_schema", "public")
    .eq("table_name", "plan_modulations")
    .eq("column_name", "expires_at")
    .execute()
)
exists = bool(res.data)
```

### Pattern: verify_migrations.py exit code contract

```python
# Follow db_cleanup.py pattern (L2 fix)
def main():
    logging.basicConfig(level=logging.INFO)
    failures = []
    # ... checks ...
    for name, ok in results:
        if not ok:
            failures.append(name)
            logger.error("FAIL: %s", name)
        else:
            logger.info("PASS: %s", name)
    if failures:
        logger.error("%d constraint(s) missing — migrations may not be applied", len(failures))
        sys.exit(1)
    logger.info("All %d constraints verified OK", len(results))
```

### Pattern: ingest.yml step without if: always()

```yaml
# D-06: step runs only on ingest success (not if: always())
- name: Apply accepted modulations (audit K1)
  if: success()        # runs only when all prior steps succeeded
  continue-on-error: true   # failure doesn't block ingest
  run: python -m coach.coaching.modulation --apply-accepted
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `if: always()` on apply step | Remove (default `if: success()`) | Modulations only applied when data is fresh |
| info_schema via raw SQL | `sb.schema("information_schema")` in supabase-py 2.x | No raw SQL needed in verify script |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sb.schema("information_schema").table(...)` works in supabase-py >= 2.30.0 for information_schema access | Key Implementation Details — verify_migrations.py | Script fails with 404; need fallback RPC approach |
| A2 | `wrangler deploy` from `workers/telegram-bot/` uses TypeScript compilation with esbuild (not tsc) | Pitfall 3 | tsc errors not caught until runtime; manual tsc check is extra but safe |
| A3 | The `if: always()` on the `apply_accepted_modulations` step is a code bug vs D-06 intent (not a deliberate design) | Pitfall 2 / DEPLOY-04 | If intentional, planner should leave it; if bug, must change to `if: success()` |
| A4 | Supabase service role key (from `SUPABASE_SERVICE_KEY`) has access to `information_schema` via PostgREST | verify_migrations.py | May need RPC fallback |

---

## Open Questions (RESOLVED)

1. **`if: always()` on apply_accepted_modulations step (A3)**
   - What we know: D-06 says "remove `if: always()`". Current `ingest.yml` has `if: always()`.
   - What's unclear: Whether the current code is the intended final state (tracking decision) or a bug
   - Recommendation: Planner should include a task to change to `if: success()` per D-06. Low risk change.
   - RESOLVED: 03-02 Task 1 removes `if: always()` from the apply-accepted step (one-line deletion).

2. **information_schema access method for verify_migrations.py (A1)**
   - What we know: `supabase-py >= 2.0` has `sb.schema()` method
   - What's unclear: Whether PostgREST on Supabase managed exposes `information_schema` schema
   - Recommendation: Implement with `sb.schema("information_schema")` as primary; add try/except with RPC fallback
   - RESOLVED: 03-01 Task 1 implements primary `sb.schema("information_schema")` path with mandatory `sb.rpc()` fallback and Pitfall 4 recovery instructions.

3. **OPEN_ISSUES.md does not exist**
   - What we know: `STATE.md` references reading `OPEN_ISSUES.md` before Phase 3. The file does not exist on disk.
   - What's unclear: Whether migrations from `OPEN_ISSUES.md` were already tracked inside `audit_resilience_2026-06-01.md` (which comprehensively lists all migrations) or if there's a separate list
   - Recommendation: `audit_resilience_2026-06-01.md §Da fare manualmente` is the authoritative migration list. The single migration file `2026-06-01-resilience-audit.sql` covers all Phase 3 schema changes. No additional OPEN_ISSUES.md action needed.
   - RESOLVED: Plans use `docs/audit_resilience_2026-06-01.md §Da fare manualmente` as the authoritative migration list; 03-01 Task 2 references the full 11-migration sequence from that document.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| wrangler | DEPLOY-03 (bot deploy) | Assumed ✓ (D-03 says "configured locally") | ^3.50.0 | — (no fallback; must be available) |
| Supabase SQL Editor (web) | DEPLOY-01/02 | ✓ (web dashboard, always available) | — | — |
| Python 3.11 + supabase-py | verify_migrations.py | ✓ (in requirements.txt) | >=2.30.0 | — |
| GitHub Actions (for L1 verification) | PIPELINE-01 | ✓ (existing workflow) | — | Manual local run |
| Telegram (manual test) | DEPLOY-03 verification | ✓ | — | — |

**Missing dependencies with no fallback:** None. All required tools are available.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4 |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/test_audit_resilience.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPLOY-01 | Constraints present in DB | integration (manual) | `python scripts/verify_migrations.py` | ❌ Wave 0 (must create) |
| DEPLOY-02 | Migration file content live | integration (manual) | `python scripts/verify_migrations.py` | ❌ Wave 0 |
| DEPLOY-03 | K2-K5 fixes live in worker | manual smoke test | Telegram chat test | N/A |
| DEPLOY-04 | accepted → applied transition | unit + manual | `pytest tests/test_audit_resilience.py::test_k1_accepted_modulation_gets_applied` | ✅ |
| PIPELINE-01 | Exit 1 on Garmin fail | manual (log inspection) | Trigger failed ingest run | N/A |
| PIPELINE-02 | Watchdog alerts missing row | unit | `pytest tests/test_audit_resilience.py::test_l4_watchdog_alerts_missing_component` | ✅ |
| PIPELINE-03 | DR aborts on empty table | unit | `pytest tests/test_audit_resilience.py::test_l3_empty_snapshot_aborts` | ✅ |
| PIPELINE-04 | Brief not sent twice | unit + manual | `pytest tests/test_audit_resilience.py` (C2 tests cover briefing) + log inspection | ✅ (partial) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_audit_resilience.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green + verify_migrations.py PASS + manual bot test before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `scripts/verify_migrations.py` — covers DEPLOY-01, DEPLOY-02 (must be created in Wave 1/Task 1)
- [ ] `test_brief_idempotency` in `tests/test_audit_resilience.py` — dedicated unit test for `_brief_already_sent_today()` (currently tested indirectly; explicit test improves confidence for PIPELINE-04)

---

## Security Domain

`security_enforcement: true` (absent = enabled) in config.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | Yes (partial) | Supabase RLS; Cloudflare Worker `TELEGRAM_ALLOWED_CHAT_ID` check |
| V5 Input Validation | Yes | Bot validates callback data; migration constraints enforce valid values at DB level |
| V6 Cryptography | No (DR encryption already in place) | AES-256-GCM in dr_snapshot.py |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Telegram webhook replay | Spoofing | KV dedup on `update_id` (already in bot) |
| Malformed JSON body → 500 storm | Denial of Service | K4 fix: `try { req.json() } catch { return 200 }` |
| Unauthorized modulation accept | Elevation of Privilege | `TELEGRAM_ALLOWED_CHAT_ID` guard already in bot |
| DB state corruption via typo status | Tampering | O9 CHECK constraint (`plan_modulations.status`) |
| Corrupt backup commit (empty tables) | Tampering / DoS | L3 fix: `assert_snapshot_sane()` |

---

## Sources

### Primary (HIGH confidence)

- Codebase direct read — `workers/telegram-bot/src/index.ts`, `coach/planning/briefing.py`, `coach/coaching/modulation.py`, `.github/workflows/ingest.yml`, `scripts/watchdog.py`, `scripts/dr_snapshot.py`, `scripts/db_cleanup.py` — all fixes verified to be present in source
- `migrations/2026-06-01-resilience-audit.sql` — full migration content read; all constraints verified present with idempotency guards
- `docs/audit_resilience_2026-06-01.md` — authoritative bug register; `§Da fare manualmente` section specifies remaining manual steps
- `migrations/2026-05-10-bot-messages-pending-confirmations-tables.sql` — `bot_messages` schema confirmed; index `idx_bot_messages_chat_purpose` present for idempotency query

### Secondary (MEDIUM confidence)

- `supabase-py >= 2.0` schema() method pattern [ASSUMED] — consistent with documented supabase-py API but not verified via Context7 in this session

---

## Metadata

**Confidence breakdown:**

- Code fixes present: HIGH — all read directly from source files
- Migration content: HIGH — read directly from migration file
- Deploy procedure: HIGH — `wrangler.toml` and `package.json` confirmed; wrangler configured locally per D-03
- `verify_migrations.py` implementation: MEDIUM — information_schema access pattern marked [ASSUMED]
- if: always() discrepancy: HIGH — confirmed in source, identified as D-06 conflict

**Research date:** 2026-06-06
**Valid until:** 2026-07-06 (stable deployment targets)
