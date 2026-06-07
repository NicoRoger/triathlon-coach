---
phase: 03-deploy-pipeline-resilience
plan: "01"
subsystem: database
tags: [migrations, supabase, postgresql, verification, schema, constraints]

requires:
  - phase: 02-fitness-test-correctness
    provides: physiology_zones corrette in DB, prerequisito per le FK migrations

provides:
  - scripts/verify_migrations.py — verifier deterministico con exit-code contract (PASS=0, FAIL=1)
  - Vincoli schema live in Supabase: 3 UNIQUE, 3 FK ON DELETE, 2 CHECK, 1 colonna expires_at
  - RPC fallback SECURITY DEFINER: public.get_public_constraints() e public.get_public_columns()

affects:
  - 03-04 (live behavior verification — il bot K3 fix richiede subjective_log.kind CHECK live)
  - 03-02 (pipeline resilience — planned_sessions UNIQUE e FK devono essere live)

tech-stack:
  added: []
  patterns:
    - "RPC fallback pattern: sb.schema('information_schema') → sb.rpc('get_public_constraints') quando PostgREST non espone information_schema (PGRST106)"
    - "SECURITY DEFINER functions come proxy per accesso controllato a information_schema"
    - "Exit-code gate: script di verifica esce 1 se manca qualsiasi constraint — usabile come CI gate"

key-files:
  created:
    - scripts/verify_migrations.py
  modified: []

key-decisions:
  - "RPC fallback obbligatorio (non opzionale): information_schema non è esposta via PostgREST su Supabase — il fallback è la via primaria in produzione"
  - "SECURITY DEFINER RPCs create in Supabase SQL Editor: public.get_public_constraints() e public.get_public_columns() — prerequisito per il funzionamento del verifier"
  - "11 migration eseguite manualmente via Supabase SQL Editor in ordine dipendenze (resilience-audit.sql per ultimo)"

patterns-established:
  - "Pattern verify script: modulo Python con 4 costanti EXPECTED_*, primary path information_schema, fallback RPC, exit-code 0/1"

requirements-completed: [DEPLOY-01, DEPLOY-02]

duration: ~45min (human action inclusa)
completed: 2026-06-07
---

# Phase 03 Plan 01: Migrations Verification Summary

**Script verify_migrations.py creato e verificato live: tutti i 9 vincoli schema dell'audit di resilienza sono confermati presenti in Supabase con exit code 0.**

## Performance

- **Duration:** ~45 min (incluso task 2 human-action per SQL Editor)
- **Started:** 2026-06-07
- **Completed:** 2026-06-07
- **Tasks:** 3/3 completati
- **Files modified:** 1 (scripts/verify_migrations.py creato)

## Accomplishments

- Creato `scripts/verify_migrations.py` con 4 costanti di attesa (`EXPECTED_UNIQUE_CONSTRAINTS`, `EXPECTED_FK_CONSTRAINTS`, `EXPECTED_CHECK_CONSTRAINTS`, `EXPECTED_COLUMNS`), primary path `information_schema` via PostgREST, fallback `sb.rpc()`, exit code 0/1
- Eseguite tutte le 11 migration pending da `docs/OPEN_ISSUES.md` in Supabase SQL Editor (human-action), inclusa `2026-06-01-resilience-audit.sql` per ultima
- Verificato live: `python scripts/verify_migrations.py` esce 0 con tutti i 9 PASS (3 UNIQUE, 3 FK, 2 CHECK, 1 colonna expires_at)
- Creati i fallback RPC `public.get_public_constraints()` e `public.get_public_columns()` SECURITY DEFINER in Supabase (Pitfall 4 — PostgREST restituisce PGRST106 su information_schema)

## Task Commits

Ogni task è stato committato atomicamente:

1. **Task 1: Create scripts/verify_migrations.py** - `5ac0c91` (feat)
2. **Task 2: Execute pending migrations** - human action (SQL Editor, nessun commit codice)
3. **Task 3: Run verify_migrations.py** - verificato localmente, exit 0 — incluso nel commit metadata piano

**Plan metadata:** da creare (docs commit)

## Files Created/Modified

- `scripts/verify_migrations.py` — verifier deterministico: 4 costanti EXPECTED_*, primary PostgREST information_schema, fallback sb.rpc(), exit 0/1, logging PASS/FAIL per constraint

## Decisions Made

- **RPC fallback obbligatorio:** Supabase non espone `information_schema` via PostgREST (errore PGRST106). Il path primario nel codice è `sb.schema("information_schema")`, ma in produzione viene sempre usato il fallback `sb.rpc("get_public_constraints")` e `sb.rpc("get_public_columns")`. Le RPC SECURITY DEFINER sono state create in Supabase SQL Editor come prerequisito.
- **Ordine esecuzione migrations:** `2026-06-01-resilience-audit.sql` eseguito per ultimo — richiede che `races`, `mesocycles`, `physiology_zones`, `planned_sessions`, `plan_modulations`, `subjective_log` esistano già. Il DEDUP UPDATE+DELETE deve precedere il UNIQUE constraint all'interno del file.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Creazione RPC SECURITY DEFINER per fallback information_schema**

- **Found during:** Task 3 (run verify_migrations.py)
- **Issue:** PostgREST restituisce PGRST106 su `information_schema` — il path primario restituisce risultati vuoti invece di un errore esplicito, causando falsi PASS
- **Fix:** Create in Supabase SQL Editor `public.get_public_constraints()` e `public.get_public_columns()` SECURITY DEFINER come documentato in RESEARCH.md §"Pitfall 4"
- **Files modified:** nessun file su disco (cambio solo DB Supabase)
- **Verification:** `python scripts/verify_migrations.py` esce 0 con 9 PASS dopo la creazione delle RPC

**Total deviations:** 1 auto-fixed (Rule 3 — blocking issue)
**Impact on plan:** Previsto come contingenza in RESEARCH.md §"Pitfall 4". Nessun scope creep.

## Issues Encountered

- `information_schema` non esposta via PostgREST (PGRST106): risolto con RPC fallback SECURITY DEFINER come previsto da RESEARCH.md.
- Il path primario nel codice è corretto e ideale per ambienti con Postgres diretto — il fallback gestisce l'ambiente Supabase.

## Threat Surface Scan

Nessuna nuova superficie non coperta dalla threat_model del piano. Le RPC SECURITY DEFINER create (`get_public_constraints`, `get_public_columns`) sono read-only su `information_schema` con `table_schema='public'` — nessun accesso a dati sensibili, stesso perimetro del service role key già usato da tutti gli altri script.

## Self-Check

- [x] `scripts/verify_migrations.py` esiste in repo
- [x] Commit `5ac0c91` presente in git log
- [x] `python scripts/verify_migrations.py` ha restituito exit 0 con 9 PASS (confermato dall'atleta)
- [x] DEPLOY-01 e DEPLOY-02 soddisfatti: tutte le migration live, verifier conferma
