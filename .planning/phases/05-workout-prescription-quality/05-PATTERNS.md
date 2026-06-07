# Phase 5: Workout Prescription Quality — Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 7
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `skills/propose_session.md` | skill-prompt | request-response | `skills/generate_mesocycle.md` | exact |
| `skills/generate_mesocycle.md` | skill-prompt | request-response | `skills/propose_session.md` | exact |
| `skills/fitness_test.md` | skill-prompt | request-response | `skills/propose_session.md` | role-match |
| `workers/mcp-server/src/index.ts` | TypeScript Worker | request-response | self (existing `commitPlanChange`, `getWeeklyContext`, `getPhysiologyZones`) | exact |
| `migrations/2026-06-07-workout-prescription-quality.sql` | migration | CRUD | `migrations/2026-06-01-resilience-audit.sql` | exact |
| `tests/test_active_constraints.py` | test | request-response | `tests/test_audit_resilience.py` | exact |
| `scripts/verify_prescription_quality.py` | utility/script | request-response | `scripts/verify_analytics.py` | exact |

---

## Pattern Assignments

### `skills/propose_session.md` (skill-prompt, request-response)

**Analog:** `skills/generate_mesocycle.md` (lines 1–152) and current `skills/propose_session.md` (lines 1–67)

**Frontmatter pattern** (propose_session.md lines 1–4):
```markdown
---
name: propose_session
description: Dettaglia la sessione del giorno (o di una data specifica) con zone, durate, target. Usa quando l'atleta chiede "cosa faccio oggi", "dimmi la sessione" o quando il brief mattutino non basta.
---
```

**Ordered step / gate pattern** (generate_mesocycle.md lines 19–36 — the authoritative multi-step procedure):
```markdown
## Procedura
1. Leggi `CLAUDE.md` §Profilo, §Stato corrente
2. Leggi `docs/elite_training_reference.md` per volume/HR/struttura target elite
3. Leggi `docs/training_journal.md` ultime 4-6 settimane
4. Leggi `docs/athlete_beliefs.md` per beliefs strutturali + bias correction su predizioni
5. Leggi `docs/coaching_observations.md` per pattern prescrittivi attivi
6. Leggi `get_recent_metrics(28)` per CTL trend
7. Leggi `physiology_zones` per zone correnti
8. **Multi-race awareness**: chiama `get_weekly_context` e leggi `upcoming_races` — pianifica picchi per TUTTE le gare A/B della stagione, non solo la prossima
```
Copy this numbered-step format; insert the new STEP 0 GATE before step 1 (D-02). The gate must use bold/caps ("GATE FISIOLOGICO") to signal mandatory execution, matching the existing "**Multi-race awareness**" emphasis style.

**STEP 0 gate wording** (from RESEARCH.md Code Examples — authoritative text):
```markdown
### Step 0 — GATE FISIOLOGICO (obbligatorio, nessuna prescrizione senza questo)
Chiama `get_physiology_zones(discipline)` dove discipline è il sport della sessione.
- Se il response ha `zones: []` o `note: "Nessuna zona..."`: NON prescrivere. Proponi test fitness.
- Se `age_days > 42`: segnala che le zone potrebbero essere obsolete e suggerisci test.
- Estrai i valori precisi: `ftp_w`, `threshold_pace_s_per_km`, o `css_pace_s_per_100m`.
- Tutti i target numerici nella prescrizione DEVONO venire da questi valori.
```

**Citation pattern** (propose_session.md lines 50–66 — already present, preserve verbatim):
```markdown
## Citation obbligatoria (Fase 2.4)

Quando giustifichi la scelta di intensità/zone/struttura della sessione, cita la base scientifica con tag inline:

`[source: <autore> <anno>]`

Esempi:
- Z2 lungo → `[source: Seiler 2010]`
- Soglia → `[source: Coggan 2003]`
- Recovery <50% readiness → `[source: Halson 2014 recovery monitoring]`

Quando applichi una belief: `[athlete-belief: <descrizione>]`.
```

**"Cosa NON fare" pattern** (propose_session.md lines 62–67 — preserve and extend):
```markdown
## Cosa NON fare
- Mai prescrivere intensità/zone se le `physiology_zones` per quella disciplina
  sono `NULL` o oltre 12 settimane vecchie. Suggerisci test fitness invece.
- Mai ignorare flag attivi. Se `illness_flag` o `injury_flag` → recovery, fine.
- Mai inventare riferimenti scientifici. Se incerto, usa `[source: principio generale endurance]`.
```
Add to this list: "Mai leggere vincoli medici da CLAUDE.md statico — usa `get_weekly_context.active_constraints`."

**Output template pattern** (RESEARCH.md Code Examples — propose_session.md section):
```markdown
## Template output (OBBLIGATORIO — mai deviare da questa struttura)

🏃 [Sport] — [tipo sessione] — [durata totale]min

📊 Contesto mesociclo
Settimana [N]/3 del blocco [fase]
TSS accumulato: [X] / ~[Y] (target settimana)
Sessioni qualità questa settimana: [n] ([dettaglio])
Ruolo di oggi: [descrizione specifica]

⚠️ Vincoli attivi: [da active_constraints — se vuoto: "nessun vincolo attivo"]

Warm-up: [durata]min [zona] ([descrizione]). [Source tag]
Drill block: [drill specifici per disciplina/fase Nicolò]
Main set: [N×Xmin @ zona/target numerico preciso, rec Ymin zona]
Cool-down: [durata]min [zona]

Target TSS: ~[X]
Zone di riferimento: [valori da physiology_zones — watt/pace/s100m]
[⚠️ Condizioni avverse se ≥2 fattori: perceived effort Z4, ~[pace adattata]]
```

---

### `skills/generate_mesocycle.md` (skill-prompt, request-response)

**Analog:** self (current `skills/generate_mesocycle.md` lines 1–152)

**Step requiring change** (generate_mesocycle.md lines 19–36 — existing procedure):
```markdown
6. Leggi `get_recent_metrics(28)` per CTL trend
7. Leggi `physiology_zones` per zone correnti
8. **Multi-race awareness**: chiama `get_weekly_context` e leggi `upcoming_races`
```
Restructure: move `physiology_zones` read to Step 0 with the same GATE FISIOLOGICO pattern as `propose_session.md`. Replace step 7 reference with "già fatto in Step 0". Extend step 8 `get_weekly_context` read to also extract `active_constraints` (D-15).

**Commit flow pattern** (generate_mesocycle.md lines 74–79 — existing, preserve and extend):
```markdown
## Commit in DB
Dopo approvazione dell'atleta:
1. Chiama `commit_mesocycle` con `name`, `phase`, `start_date`, `end_date` (e `target_race_id` se applicabile)
   - Restituisce `mesocycle_id`
2. Chiama `commit_plan_change` per ogni sessione, passando il `mesocycle_id` ricevuto
3. Conferma: "Mesociclo {name} salvato — {n} sessioni pianificate fino al {end_date}"
```
Extend step 1: add `progression_plan` to the `commit_mesocycle` call. Add structured JSONB (D-09) to every `commit_plan_change` call in step 2.

**JSONB structured format** (CONTEXT.md §Specifics — canonical):
```json
{
  "structured": [
    {"name": "warmup",   "duration_s": 900,  "zone": "Z1-Z2", "notes": "progressivo"},
    {"name": "drill",    "reps": 4, "duration_s": 50, "zone": "Z1", "target_value": "fingertip drag"},
    {"name": "main_set", "reps": 6, "duration_s": 360, "zone": "Z4", "target_value": 210, "notes": "@ 105% FTP"},
    {"name": "cooldown", "duration_s": 600,  "zone": "Z1"}
  ]
}
```

**Output template** (generate_mesocycle.md lines 38–71 — existing, currently lists "Z2 corsa 60min" style):
The existing template shows synthetic descriptions ("Z2 corsa 60min"). For Phase 5, each session line in the template must be accompanied by a note: "ogni sessione sarà espansa con warmup/main/cooldown nel `structured` JSONB via `commit_plan_change`." Do not rewrite the planning table — only add the expansion note.

---

### `skills/fitness_test.md` (skill-prompt, request-response)

**Analog:** self (current `skills/fitness_test.md` lines 1–66)

**Existing "Quando proporre" pattern** (fitness_test.md lines 8–20 — preserve verbatim):
```markdown
## Quando proporre un test

Proponi test quando:
- 6+ settimane dall'ultimo test della disciplina (controlla `physiology_zones` via `get_physiology_zones`)
- TSB > 0 per almeno 2 giorni (atleta fresco)
- HRV z-score > -0.5 il giorno precedente e il giorno del test
- Non siamo in race week o deload week
- L'atleta ha confermato di sentirsi pronto
```

**FTP age check addition** (D-05/D-06 — insert as new section before "Quando proporre"):
```markdown
## Step 0 — Check FTP age (SEMPRE per sessioni bici)

1. Chiama `get_physiology_zones('bike')`
2. Leggi `zones[0].age_days` nel response
3. Se `age_days > 42` (6 settimane) o zones è vuoto:
   "FTP non aggiornato da [age_days] giorni (>6 settimane). Propongo un test FTP bici.
   Data ottimale: [calcola: post 1-2gg Z2/recovery, non in settimana di carico max, non entro 10gg da gara A]
   TSB target al test: >0 per almeno 2 giorni."
```
This wording comes from RESEARCH.md Code Examples (fitness_test.md section). The condition `age_days > 42` must use the numeric value from the DB response, not the static text "6 settimane" that currently exists in the file.

**"Come proporre" pattern** (fitness_test.md lines 22–32 — preserve verbatim):
```markdown
## Come proporre (OBBLIGATORIO — NON NEGOZIABILE)

Quando proponi un test, DEVI fare TUTTE queste cose:

1. **Spiega il protocollo** (warmup, set principale, cooldown, timing)
2. **Dai il nome ESATTO Garmin** da usare (vedi `docs/FITNESS_TEST_PROTOCOL.md`)
3. **Committa con `commit_plan_change`** usando:
   - `session_type = 'fitness_test'`
   - `structured` con lo schema completo da `docs/FITNESS_TEST_PROTOCOL.md`
4. **Comunica all'atleta**: "Il sistema leggerà automaticamente il risultato dopo il sync Garmin e aggiornerà le tue zone."
```

---

### `workers/mcp-server/src/index.ts` (TypeScript Worker, request-response)

**Analog:** self — patterns extracted from the existing tool implementations.

**TOOLS array entry pattern** (index.ts lines 53–211 — existing entries):
```typescript
{
  name: "update_constraint",
  description: "Marca un vincolo medico come risolto (resolved_at = now). Chiamare dopo valutazione clinica.",
  inputSchema: {
    type: "object",
    required: ["id"],
    properties: {
      id: { type: "string", description: "UUID del vincolo da risolvere" },
      resolved_at: { type: "string", format: "date-time", description: "Timestamp risoluzione (default: now)" },
    },
  },
},
```
Insert this entry into `TOOLS` after `commit_mesocycle` (line 211). All existing entries in TOOLS follow the same `{name, description, inputSchema}` flat object shape — copy exactly.

**`callTool` switch case pattern** (index.ts lines 413–445):
```typescript
case "update_constraint":
  return updateConstraint(args, env);
```
Insert before the `default:` case. Pattern: `case "<name>": return <camelCase>(args || {}, env);`

**`commitPlanChange` payload builder pattern** (index.ts lines 703–762 — exact pattern for `commitMesocycle` extension):
```typescript
// Pattern: optional fields added conditionally
if (args.target_tss !== undefined) payload.target_tss = args.target_tss;
if (args.target_zones !== undefined) payload.target_zones = args.target_zones;
if (args.structured !== undefined) payload.structured = args.structured;
```
Apply this exact pattern in `commitMesocycle` (lines 827–876): add `if (args.progression_plan !== undefined) payload.progression_plan = args.progression_plan;` after `if (args.notes !== undefined) payload.notes = args.notes;`.

**`sb()` helper pattern for fetch** (index.ts lines 451–460 — read-only):
```typescript
async function sb(env: Env, path: string): Promise<any> {
  const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    },
  });
  if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${await resp.text()}`);
  return resp.json();
}
```
For `updateConstraint`, use `fetch()` directly (PATCH) — same pattern as `commitPlanChange` lines 736–746:
```typescript
const updateResp = await fetch(`${env.SUPABASE_URL}/rest/v1/active_constraints?id=eq.${args.id}`, {
  method: "PATCH",
  headers: {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
  },
  body: JSON.stringify({ resolved_at: resolvedAt }),
});
if (!updateResp.ok) throw new Error(`Update failed: ${updateResp.status}`);
```

**`isUuid()` validation pattern** (index.ts line 490 — existing, use for `updateConstraint`):
```typescript
function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
```
Call `isUuid(args.id)` at the top of `updateConstraint` and throw if false. Pattern mirrors `commitPlanChange` required field validation (lines 704–707).

**`getWeeklyContext` Promise.all extension pattern** (index.ts lines 541–554 — existing destructuring):
```typescript
const [health, metrics, wellness, activities, subjective, plannedPast, plannedUpcoming, sessionAnalyses, modulations, mesocycles, races] =
  await Promise.all([
    getHealth(env),
    sb(env, `daily_metrics?...`),
    // ... 9 more queries
  ]);
```
Add a 12th element: `sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`)` at the end of the `Promise.all` array. Update the destructuring to add `constraints` as the 12th variable.

**Return object extension pattern** (index.ts lines 556–579 — existing `return {...}`):
```typescript
return {
  generated_at: new Date().toISOString(),
  // ... existing fields ...
  active_mesocycle: mesocycles?.[0] || null,
  upcoming_races: races || [],
  // ADD:
  active_constraints: constraints || [],
  current_progression_step: deriveProgressionStep(mesocycles?.[0] || null, today),
  review_instructions: [...],
};
```

**`deriveProgressionStep` helper pattern** (RESEARCH.md Pattern 3 — new helper, follows `todayRomeISO` style at lines 462–471):
```typescript
function deriveProgressionStep(mesocycle: any, today: string): any {
  if (!mesocycle || !mesocycle.progression_plan || !mesocycle.start_date) return null;
  const startDate = new Date(mesocycle.start_date);
  const todayDate = new Date(today);
  const weekNumber = Math.floor((todayDate.getTime() - startDate.getTime()) / (7 * 24 * 60 * 60 * 1000)) + 1;
  const plan = mesocycle.progression_plan;
  const result: any = {};
  for (const [sessionType, weeks] of Object.entries(plan as Record<string, any>)) {
    result[sessionType] = (weeks as any)[`week${weekNumber}`] || null;
  }
  return { week_number: weekNumber, steps: result };
}
```
Place adjacent to other pure helper functions (`todayRomeISO`, `daysAgoISO`, `clampInt`) — lines 462–492 area.

**`getPhysiologyZones` age_days extension** (index.ts lines 768–790 — modify the return):
```typescript
// After: const current: any[] = [];  for (const row of rows) { ... current.push(row); }
// ADD before return:
const todayDate = new Date(todayRomeISO());
for (const zone of current) {
  if (zone.valid_from) {
    const validFrom = new Date(zone.valid_from);  // DATE string "2026-06-04" parsed as UTC midnight
    const diffMs = todayDate.getTime() - validFrom.getTime();
    zone.age_days = Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
  } else {
    zone.age_days = null;
  }
}
```
Note: `todayRomeISO()` returns a `"YYYY-MM-DD"` string; `new Date("YYYY-MM-DD")` also parses as UTC midnight — both are UTC midnight, so the difference is exact days. See RESEARCH.md Pitfall 1 for why this is safe when both sides are treated as UTC midnight.

**`commit_mesocycle` inputSchema extension** (TOOLS array, lines 196–211):
```typescript
{
  name: "commit_mesocycle",
  // ... existing description ...
  inputSchema: {
    type: "object",
    required: ["name", "phase", "start_date", "end_date"],
    properties: {
      // ... existing properties ...
      notes: { type: "string" },
      // ADD:
      progression_plan: { type: "object", description: "JSONB: {run_threshold: {week1: '4x6min', week2: '5x6min', week3: '6x6min'}, ...}" },
    },
  },
},
```

---

### `migrations/2026-06-07-workout-prescription-quality.sql` (migration, CRUD)

**Analog:** `migrations/2026-06-01-resilience-audit.sql` (lines 1–160)

**Header comment pattern** (resilience-audit.sql lines 1–12):
```sql
-- Migration: Workout Prescription Quality 2026-06-07
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   Phase 5 — nuova tabella active_constraints: vincoli medici dinamici (D-12/D-13)
--   Phase 5 — mesocycles.progression_plan JSONB (D-27)
```

**`CREATE TABLE IF NOT EXISTS` pattern** (resilience-audit.sql idempotency convention; schema.sql pattern confirmed by test_o1_schema_create_table_idempotent):
```sql
CREATE TABLE IF NOT EXISTS active_constraints (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type            TEXT NOT NULL CHECK (type IN ('injury', 'medical', 'tactical')),
    discipline      TEXT NOT NULL CHECK (discipline IN ('swim', 'bike', 'run', 'all')),
    description     TEXT NOT NULL,
    severity        TEXT CHECK (severity IN ('high', 'medium', 'low')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

ALTER TABLE active_constraints ENABLE ROW LEVEL SECURITY;
```

**`ADD COLUMN IF NOT EXISTS` pattern** (resilience-audit.sql line 67):
```sql
ALTER TABLE plan_modulations
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
```
Apply same pattern for `mesocycles`:
```sql
ALTER TABLE mesocycles
    ADD COLUMN IF NOT EXISTS progression_plan JSONB;
```

**`DO $$ BEGIN ... EXCEPTION` pattern** (resilience-audit.sql lines 40–46 — for constraints):
```sql
DO $$
BEGIN
    ALTER TABLE active_constraints ADD CONSTRAINT active_constraints_rls_policy ...;
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;
```

**Seed idempotency pattern** (RESEARCH.md Pitfall 5 — use WHERE NOT EXISTS, not ON CONFLICT DO NOTHING, because there is no natural UNIQUE key):
```sql
INSERT INTO active_constraints (type, discipline, description, severity)
SELECT 'injury', 'swim',
       'borsite + tendinopatia CLB spalla destra: max Z1-Z2, zero Z4+, distanza 72h tra sessioni nuoto',
       'high'
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints WHERE type = 'injury' AND discipline = 'swim' AND resolved_at IS NULL
);

INSERT INTO active_constraints (type, discipline, description, severity)
SELECT 'injury', 'run',
       'fascite plantare sinistra: max +10% volume/settimana, cap 14-15km/settimana attuale, asintomatica da 14gg',
       'medium'
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints WHERE type = 'injury' AND discipline = 'run' AND resolved_at IS NULL
);
```

---

### `tests/test_active_constraints.py` (test, request-response)

**Analog:** `tests/test_audit_resilience.py` (lines 1–999)

**Module header pattern** (test_audit_resilience.py lines 1–7):
```python
"""Test di integrazione per Phase 5 — active_constraints e get_weekly_context extension.

Copertura: WORKOUT-03 (vincoli medici da DB, non da CLAUDE.md statico).
Verifica che la migration abbia creato active_constraints con i 2 seed
e che get_weekly_context restituisca active_constraints come array.

Esecuzione: python -m pytest tests/test_active_constraints.py -v
"""
from __future__ import annotations
```

**Import pattern** (test_audit_resilience.py lines 9–27):
```python
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
```

**`_load()` helper** (test_audit_resilience.py lines 31–37 — copy verbatim):
```python
def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod
```

**Source assertion pattern** (test_audit_resilience.py lines 759–789 — `test_o4_o6_migration_present` style):
```python
def test_migration_file_present():
    """Migration Phase 5 deve esistere e contenere active_constraints."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(encoding="utf-8")
    assert "active_constraints" in src
    assert "progression_plan" in src
    assert "WHERE NOT EXISTS" in src   # idempotent seed pattern

def test_migration_idempotent():
    """Migration deve usare IF NOT EXISTS per CREATE TABLE."""
    src = (ROOT / "migrations" / "2026-06-07-workout-prescription-quality.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS active_constraints" in src
    assert "ADD COLUMN IF NOT EXISTS progression_plan" in src
```

**FakeSupabase pattern** (test_audit_resilience.py lines 42–105 — `_FakeQuery` / `_FakeSupabase`):
For tests that query `active_constraints`, use the same `_FakeQuery` / `_FakeSupabase` pattern. The `active_constraints` table returns 2 seed rows; the `get_weekly_context` response must include `active_constraints` as a list.

**Structural assertion pattern** (test_audit_resilience.py lines 759–798):
```python
def test_active_constraints_seed_has_two_rows():
    """active_constraints deve contenere esattamente 2 vincoli attivi dopo la migration."""
    # Test eseguito contro DB di produzione via env vars — skippa se SUPABASE_URL non configurato
    import os
    if not os.getenv("SUPABASE_URL"):
        pytest.skip("SUPABASE_URL non configurato — test live skippato")
    from dotenv import load_dotenv
    load_dotenv()
    from coach.utils.supabase_client import get_supabase
    sb = get_supabase()
    res = sb.table("active_constraints").select("id,type,discipline").eq("resolved_at", None).execute()
    rows = res.data or []
    disciplines = {r["discipline"] for r in rows}
    assert "swim" in disciplines, "vincolo nuoto (spalla dx) deve esistere"
    assert "run" in disciplines, "vincolo corsa (fascite sx) deve esistere"
```

---

### `scripts/verify_prescription_quality.py` (utility, request-response)

**Analog:** `scripts/verify_analytics.py` (lines 1–221)

**Header + load_dotenv pattern** (verify_analytics.py lines 1–18):
```python
"""Verifica live della qualità delle prescrizioni Phase 5.

Script informativo: stampa sezioni leggibili per ispezione visiva di WORKOUT-03.
Nessun exit automatico — l'operatore legge l'output e decide.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)
```

**Section function pattern** (verify_analytics.py lines 26–90 — `_verify_hrv`):
```python
def _verify_active_constraints(sb) -> None:
    """Verifica WORKOUT-03: active_constraints ha i 2 seed e resolved_at IS NULL."""
    print("=== Active Constraints (WORKOUT-03) ===")
    try:
        res = (
            sb.table("active_constraints")
            .select("id,type,discipline,description,severity,created_at,resolved_at")
            .execute()
        )
        rows = res.data or []
        active = [r for r in rows if r.get("resolved_at") is None]
        print(f"Vincoli totali: {len(rows)} | Attivi: {len(active)}")
        for r in active:
            print(f"  [{r['severity'].upper()}] {r['discipline'].upper()}: {r['description'][:80]}")
        if len(active) < 2:
            print("ATTENZIONE: meno di 2 vincoli attivi — seed migration non eseguito?")
    except Exception as exc:
        print(f"ERRORE sezione active_constraints: {exc}")
    print()
```
Copy this exact structure (try/except, print sections, error handling) for each verify section.

**Main pattern** (verify_analytics.py lines 202–221):
```python
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()

    logger.info("verify_prescription_quality.py — Phase 5 WORKOUT check")
    print()

    _verify_active_constraints(sb)
    _verify_physiology_zones_age(sb)
    _verify_mesocycles_progression_plan(sb)
    _print_manual_checklist()


if __name__ == "__main__":
    main()
```

**Manual checklist pattern** (used in verify_physiology.py — same project):
```python
def _print_manual_checklist() -> None:
    print("=== Checklist manuale (WORKOUT-01/02/04/05) ===")
    items = [
        "[ ] WORKOUT-01: proponi sessione in Claude.ai — verifica warmup/main/cooldown nel output",
        "[ ] WORKOUT-02: cambia FTP in DB, richiedi sessione — verifica che i watt cambino",
        "[ ] WORKOUT-04: verifica TSS proposto vs mesocycles.progression_plan",
        "[ ] WORKOUT-05: verifica distribuzione 80/20 nel piano settimanale",
    ]
    for item in items:
        print(f"  {item}")
    print()
```

---

## Shared Patterns

### Mandatory `get_physiology_zones` GATE
**Source:** Proposed addition to `skills/propose_session.md` and `skills/generate_mesocycle.md`
**Apply to:** Both skill prompts — Step 0 before any prescription
```markdown
### Step 0 — GATE FISIOLOGICO (obbligatorio, nessuna prescrizione senza questo)
Chiama `get_physiology_zones(discipline)`.
- zones vuoto → NON prescrivere, proponi test
- age_days > 42 → segnala obsolescenza, suggerisci test
- Tutti i target numerici dalla risposta: ftp_w / threshold_pace_s_per_km / css_pace_s_per_100m
```

### Dynamic constraint reading (never CLAUDE.md static)
**Source:** D-16, enforced in skill prompts
**Apply to:** `propose_session.md` and `generate_mesocycle.md`
```markdown
## Passo obbligatorio — Vincoli medici
Leggi `get_weekly_context().active_constraints` (solo resolved_at IS NULL).
QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md.
Non prescrivere sessioni in contrasto con nessun vincolo attivo.
```

### Supabase PATCH pattern
**Source:** `workers/mcp-server/src/index.ts` lines 736–746 (`commitPlanChange` PATCH branch)
**Apply to:** New `updateConstraint` function
```typescript
const resp = await fetch(`${env.SUPABASE_URL}/rest/v1/<table>?id=eq.${id}`, {
  method: "PATCH",
  headers: {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
  },
  body: JSON.stringify(payload),
});
if (!resp.ok) throw new Error(`Update failed: ${resp.status} ${await resp.text()}`);
```

### Migration idempotency (`IF NOT EXISTS` + `DO $$ BEGIN ... EXCEPTION`)
**Source:** `migrations/2026-06-01-resilience-audit.sql` lines 40–46, 67
**Apply to:** `migrations/2026-06-07-workout-prescription-quality.sql`
All DDL must be wrapped in `IF NOT EXISTS` or `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;`. Seed inserts must use `WHERE NOT EXISTS`.

### Test source assertion style
**Source:** `tests/test_audit_resilience.py` lines 759–789 (`test_o1_schema_create_table_idempotent`, `test_o4_o6_migration_present`)
**Apply to:** `tests/test_active_constraints.py`
```python
def test_<thing>_present():
    src = (ROOT / "migrations" / "<file>.sql").read_text(encoding="utf-8")
    assert "<keyword>" in src
```

### Script section structure
**Source:** `scripts/verify_analytics.py` lines 26–221
**Apply to:** `scripts/verify_prescription_quality.py`
Each section: `def _verify_<topic>(sb) -> None:` with `try/except Exception as exc: print(f"ERRORE ...")` and `print()` separator at the end.

---

## No Analog Found

No files are without analogs. All 7 files have direct analogs in the codebase.

---

## Key Pitfalls to Propagate to Planner

1. **`valid_from` is DATE not TIMESTAMPTZ** — `new Date("2026-06-04")` parses as UTC midnight. `todayRomeISO()` also returns a date string. Treat both as UTC midnight for age_days calculation. See RESEARCH.md Pitfall 1.
2. **`commitMesocycle` silently ignores `progression_plan`** — the payload builder at index.ts lines 838–846 must be extended with the conditional `if (args.progression_plan !== undefined)` pattern. See RESEARCH.md Pitfall 2.
3. **`WHERE NOT EXISTS` for seed** — `ON CONFLICT DO NOTHING` requires a UNIQUE constraint. `active_constraints` has no natural unique key. Use `WHERE NOT EXISTS (SELECT 1 FROM active_constraints WHERE type=... AND discipline=... AND resolved_at IS NULL)`. See RESEARCH.md Pitfall 5.
4. **`update_constraint` must call `isUuid(args.id)`** — the helper already exists at index.ts line 490. Use it before the PATCH fetch call.
5. **`deriveProgressionStep` must return null gracefully** when `active_mesocycle` is null — no mesocycle committed yet is a valid state. See RESEARCH.md Pitfall 6.

---

## Metadata

**Analog search scope:** `skills/`, `workers/mcp-server/src/`, `migrations/`, `tests/`, `scripts/`
**Files read:** 12 (propose_session.md, generate_mesocycle.md, fitness_test.md, index.ts full, 2026-06-01-resilience-audit.sql, test_audit_resilience.py, verify_analytics.py partial)
**Pattern extraction date:** 2026-06-07
