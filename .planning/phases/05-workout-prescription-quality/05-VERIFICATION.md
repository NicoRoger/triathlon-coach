---
phase: 05-workout-prescription-quality
verified: 2026-06-08T14:00:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Chiedi al coach in Claude.ai: 'Dettagliami la sessione di oggi'. Verifica struttura completa."
    expected: "Output contiene Warm-up (durata+zona), Main set (intervalli con target numerici es. '6x4min @ 105% FTP, rec 2min'), Cool-down — mai solo '60min Z2'"
    why_human: "WORKOUT-01 dipende dall'output LLM del coach AI — non verificabile con grep sul codice"
  - test: "Chiedi get_physiology_zones e confronta i valori watt/pace/s100m con i target nella prescrizione generata."
    expected: "I target numerici nella prescrizione corrispondono ai valori di physiology_zones (FTP corrente, soglia 263s/km, CSS 80s/100m) — zero hard-coded"
    why_human: "WORKOUT-02 richiede osservazione dell'output LLM e confronto con dati DB live"
  - test: "Genera prescrizione nuoto in Claude.ai e verifica che il coach citi active_constraints."
    expected: "La prescrizione nuoto rimane Z1-Z2 e il coach cita i vincoli da get_weekly_context.active_constraints, non da CLAUDE.md statico"
    why_human: "WORKOUT-03 comportamento prompt richiede verifica osservativa del flusso MCP tool-call"
  - test: "Genera prescrizione e verifica sezione 'Contesto mesociclo' con TSS accumulato vs target."
    expected: "Sezione Contesto mesociclo presente con TSS accumulato, target settimanale, ruolo della sessione nel mesociclo corrente"
    why_human: "WORKOUT-04 dipende da dati DB live e output LLM formattato — non verificabile staticamente"
  - test: "Genera piano settimanale con generate_mesocycle. Conta sessioni Z1-Z2 vs qualità."
    expected: ">= 80% sessioni Z1-Z2, blocchi qualità Z4-Z5 su giorni non consecutivi, Z3 minimizzato"
    why_human: "WORKOUT-05 distribuzione 80/20 è una proprietà del piano generato, non del codice sorgente"
---

# Phase 05: Workout Prescription Quality — Verification Report

**Phase Goal:** Elevare la qualità del coaching a livello élite — prescrizioni strutturate, calibrate sulla fisiologia misurata, vincoli medici dinamici da DB, output LLM paragonabile a un servizio professionale.
**Verified:** 2026-06-08T14:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | La tabella active_constraints esiste nella migration con 2 vincoli seed (spalla dx swim, fascite sx run) | VERIFIED | `migrations/2026-06-07-workout-prescription-quality.sql` contiene `CREATE TABLE IF NOT EXISTS active_constraints`, `WHERE NOT EXISTS` guards per i 2 seed, substring `borsite + tendinopatia CLB` e `fascite plantare sinistra` — confermato da grep e da 5 test source-assertion che passano verde |
| 2 | La colonna mesocycles.progression_plan JSONB esiste nella migration | VERIFIED | `ALTER TABLE mesocycles ADD COLUMN IF NOT EXISTS progression_plan JSONB` presente nel file migration |
| 3 | tests/test_active_constraints.py passa verde (source assertions) | VERIFIED | `pytest tests/test_active_constraints.py -v` → 5 passed, 1 skipped (live DB). I 5 test source-assertion passano senza SUPABASE_URL |
| 4 | La migration è idempotente | VERIFIED | `CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS` + `WHERE NOT EXISTS` per i seed — pattern idempotente verificato nel sorgente SQL |
| 5 | get_physiology_zones espone age_days per ogni disciplina | VERIFIED | `index.ts` riga 819: `zone.age_days = Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)))` — campo calcolato da `valid_from`, null-safe |
| 6 | get_weekly_context restituisce active_constraints e current_progression_step | VERIFIED | `index.ts`: Promise.all 12° elemento `active_constraints?resolved_at=is.null`, return object include `active_constraints: constraints || []` e `current_progression_step: deriveProgressionStep(...)` con `.catch(() => [])` fallback |
| 7 | Esiste il tool update_constraint con validazione UUID | VERIFIED | TOOLS array include entry `update_constraint` con `required: ["id"]`; `updateConstraint()` chiama `isUuid(args.id)` prima della PATCH fetch; switch case `case "update_constraint"` presente |
| 8 | I skill prompts contengono gate fisiologico obbligatorio, vincoli dinamici da DB, drill tecnici, template strutturato | VERIFIED | Source assertions su tutti e 3 i file: `propose_session.md` contiene GATE FISIOLOGICO, active_constraints, get_activity_history, Contesto mesociclo, Drill tecnici Nicolo, race_prediction, perceived effort, structured, `[source:`; `generate_mesocycle.md` contiene GATE FISIOLOGICO, active_constraints, current_progression_step, progression_plan, structured, `[source:`, record_prediction; `fitness_test.md` contiene Step 0 — Check FTP age, age_days, `get_physiology_zones('bike')` |

**Score:** 8/8 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/2026-06-07-workout-prescription-quality.sql` | active_constraints table + progression_plan column + 2 seed rows idempotenti | VERIFIED | File esiste, 57 righe, tutti i pattern chiave presenti |
| `tests/test_active_constraints.py` | 5+ test source assertions + 1 live test skip-safe | VERIFIED | 6 test (5 source + 1 live skip), collezionabili senza SUPABASE_URL |
| `scripts/verify_prescription_quality.py` | Phase gate bool + Riepilogo N/3 OK + checklist manuale | VERIFIED | Firme `-> bool` su tutte e 3 le funzioni verify, `main()` con aggregazione results, stampa `=== Riepilogo: {passed}/{len(results)} OK ===`, `_print_manual_checklist()` presente |
| `workers/mcp-server/src/index.ts` | age_days, active_constraints, current_progression_step, update_constraint, progression_plan persistito | VERIFIED | Tutti i 7 pattern chiave presenti e wired (vedi sopra) |
| `skills/propose_session.md` | GATE FISIOLOGICO + vincoli dinamici + drill + template strutturato | VERIFIED | Tutti e 12 i pattern dell'acceptance criteria presenti |
| `skills/generate_mesocycle.md` | GATE FISIOLOGICO + active_constraints + progression_plan + structured JSONB | VERIFIED | Tutti e 8 i pattern chiave presenti |
| `skills/fitness_test.md` | Step 0 check FTP age data-driven da age_days | VERIFIED | Step 0 — Check FTP age presente prima di Quando proporre, `zones[0].age_days` verificato |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_active_constraints.py` | `migrations/2026-06-07-workout-prescription-quality.sql` | `read_text()` source assertion su `active_constraints` | WIRED | Test legge il file migration e asserisce le substring |
| `workers/mcp-server/src/index.ts getWeeklyContext` | `active_constraints` table | `active_constraints?resolved_at=is.null&order=created_at.asc` con `.catch(() => [])` | WIRED | Query presente nel 12° elemento del Promise.all |
| `workers/mcp-server/src/index.ts updateConstraint` | `active_constraints` table | PATCH fetch con `isUuid` guard | WIRED | Guard UUID + PATCH a `active_constraints?id=eq.${args.id}` |
| `workers/mcp-server/src/index.ts getPhysiologyZones` | `valid_from` field | `age_days` computed field | WIRED | Calcolo `diffMs / (1000*60*60*24)` da `valid_from` |
| `skills/propose_session.md` | `get_weekly_context.active_constraints` | Step 2 lettura vincoli medici dinamici | WIRED | Testo esplicito: "QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md" |
| `skills/propose_session.md` | `get_physiology_zones` | Step 0 gate obbligatorio | WIRED | "NON procedere con la prescrizione finché non hai ricevuto il response di get_physiology_zones" |
| `skills/generate_mesocycle.md` | `current_progression_step` | Step 8 lettura passo progressione | WIRED | `current_progression_step` estratto da `get_weekly_context` con regola RPE <= 7.5 |
| `skills/fitness_test.md` | `get_physiology_zones age_days` | Step 0 check FTP age data-driven | WIRED | `zones[0].age_days` letto dal response per condizione `> 42` |
| `scripts/verify_prescription_quality.py main` | `_verify_active_constraints / _verify_physiology_zones_age / _verify_mesocycles_progression_plan` | `results = [...]` aggregazione bool | WIRED | `results = [_verify_active_constraints(sb), ...]` → `passed = sum(...)` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `index.ts getPhysiologyZones` | `zone.age_days` | `physiology_zones.valid_from` (DB) | Si — calcolato da campo DATE reale | FLOWING |
| `index.ts getWeeklyContext` | `active_constraints` | `active_constraints` table (DB), resolved_at IS NULL | Si — query live, fallback `[]` | FLOWING |
| `index.ts getWeeklyContext` | `current_progression_step` | `mesocycles.progression_plan` via `deriveProgressionStep` | Si — `null` quando nessun mesociclo ha progression_plan (comportamento corretto, non stub) | FLOWING |
| `index.ts updateConstraint` | PATCH result | `active_constraints` table (DB) | Si — PATCH con Prefer=return=representation | FLOWING |
| `scripts/verify_prescription_quality.py` | `active` vincoli | `active_constraints` table query live | Si — read-only query Supabase; operatore vede dati reali | FLOWING |

**Nota data-flow:** `current_progression_step` ritorna `null` nell'ambiente corrente perché nessun mesociclo ha ancora `progression_plan` impostato. Questo è il comportamento atteso (Pitfall 6 documentato nel RESEARCH.md) — il campo verrà popolato quando il coach AI userà `commit_mesocycle` con `progression_plan` per il prossimo mesociclo. Non è uno stub.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Migration SQL ha i pattern idempotenti | `python -c "src=open('migrations/...sql').read(); assert 'CREATE TABLE IF NOT EXISTS' in src"` | PASS | PASS |
| Script verify è importabile e sintaticamente valido | `python -c "import ast; ast.parse(open('scripts/verify_prescription_quality.py').read())"` | OK | PASS |
| pytest test_active_constraints (source assertions) | `pytest tests/test_active_constraints.py -v` | 5 passed, 1 skipped | PASS |
| Full test suite (non-live) | `pytest tests/ -q` | 199 passed, 1 skipped, 1 flaky pre-existing fail | PASS (see notes) |
| Source assertions propose_session | grep su 12 substring chiave | 0 mancanti | PASS |
| Source assertions generate_mesocycle | grep su 8 substring chiave | 0 mancanti | PASS |
| Source assertions fitness_test | grep su 5 substring chiave | 0 mancanti | PASS |
| index.ts chiave patterns | grep su 7 pattern (age_days, active_constraints, ecc.) | 0 mancanti | PASS |

**Note sul test failure pre-esistente:** `tests/test_live_behavior.py::test_verify04_session_analysis_routes_to_gemini` fallisce intermittentemente nella full suite a causa di contaminazione di `sys.modules` da `test_fitness_test.py` (stubs `coach.utils` come `types.ModuleType` non rimossi dopo i test). Il test passa in isolamento. Documentato in `deferred-items.md` come issue pre-esistente di Phase 4, non introdotto da Phase 5.

---

### Probe Execution

Step 7c: SKIPPED — nessun probe script (`scripts/*/tests/probe-*.sh`) dichiarato nei PLAN di Phase 5 e nessun file `probe-*.sh` trovato nel repository. Il phase gate si basa su `scripts/verify_prescription_quality.py` (run manuale, non probe automatico).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WORKOUT-01 | 05-03, 05-04 | Struttura completa warmup/main set/cooldown in ogni prescrizione | NEEDS HUMAN | Skill prompt impone template con Warm-up/Main set/Cool-down; verifica output LLM richiede Claude.ai live |
| WORKOUT-02 | 05-03, 05-04 | Zone da physiology_zones misurate, mai hard-coded | NEEDS HUMAN | Step 0 GATE FISIOLOGICO in propose_session.md; verifica numerica richiede confronto output LLM vs DB |
| WORKOUT-03 | 05-01, 05-02, 05-03, 05-04 | Vincoli medici attivi da DB (non CLAUDE.md statico) | PARTIALLY AUTOMATED | Automatico: active_constraints table esiste con 2 seed, MCP Worker espone il campo, skill prompts lo leggono. Comportamento prompt: needs human |
| WORKOUT-04 | 05-03, 05-04 | TSS coerente con mesociclo corrente | NEEDS HUMAN | Template output include "Contesto mesociclo" con TSS; verifica coerenza numerica richiede output LLM live |
| WORKOUT-05 | 05-03, 05-04 | Distribuzione 80/20 nel piano settimanale | NEEDS HUMAN | generate_mesocycle.md ha regola 80/20 codificata nel prompt; verifica distribuzione reale richiede piano generato |

**Nota requisiti:** REQUIREMENTS.md mappa WORKOUT-01..05 a Phase 5 con status "Pending" — status non è stato aggiornato a "Complete" in REQUIREMENTS.md nonostante la fase sia completata. Questo è un gap documentale, non un gap implementativo (il ROADMAP.md mostra Phase 5 come completata il 2026-06-08).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_live_behavior.py` | suite order | Test isolation failure (pre-esistente da Phase 4, documentato) | Warning | 1 flaky test nell'intera suite — non bloccante, non introdotto da Phase 5 |

Nessun TBD/FIXME/XXX non referenziato nei file modificati da Phase 5. Nessun return null/\[\]/\{\} che fluisce a output visibile. I `return ok` bool nelle funzioni `_verify_*` sono corretti (valore calcolato, non hardcoded).

---

### Human Verification Required

La SUMMARY.md di Plan 04 riporta un "approvato" dell'atleta per WORKOUT-01..05 in Claude.ai. Tuttavia, il verifier non ha accesso all'output LLM e non può retro-verificare quella sessione. Per principio, l'output LLM non è verificabile staticamente — la conferma di un checkpoint umano precedente è documentazione, non prova riproducibile.

**I seguenti check richiedono un umano con Claude.ai attivo e MCP connector collegato:**

### 1. WORKOUT-01: Struttura sessione completa

**Test:** Chiedi al coach in Claude.ai: "Dettagliami la sessione di oggi"
**Expected:** Output contiene Warm-up (durata + zona), Main set (es. "6×4min @ 105% FTP, rec 2min"), Cool-down come sezioni distinte — mai solo "60min Z2"
**Why human:** Output LLM dipende dal modello, dal contesto runtime MCP, dai dati DB live — non verificabile con grep sul codice sorgente

### 2. WORKOUT-02: Target numerici da physiology_zones

**Test:** Chiama `get_physiology_zones` dall'interfaccia MCP e confronta watt/pace/s100m con i target nella prescrizione generata
**Expected:** I target numerici corrispondono ai valori correnti di physiology_zones (FTP ≈ valore attuale, soglia 263s/km, CSS 80s/100m)
**Why human:** Richiede confronto live tra response MCP e output coach

### 3. WORKOUT-03: Vincoli da DB, non da CLAUDE.md

**Test:** Genera una prescrizione nuoto e verifica che il coach citi i vincoli letti da `get_weekly_context.active_constraints`
**Expected:** Prescrizione nuoto resta Z1-Z2; coach menziona "vincolo attivo: spalla dx" citando il DB come fonte, non CLAUDE.md
**Why human:** Comportamento del prompt dipende dall'esecuzione runtime del coach AI

### 4. WORKOUT-04: TSS e contesto mesociclo

**Test:** Verifica che la prescrizione includa sezione "Contesto mesociclo" con TSS accumulato e target settimanale
**Expected:** Sezione Contesto mesociclo presente con numeri coerenti col mesociclo corrente
**Why human:** Dipende da dati DB live (mesocycl attivo, TSS accumulati)

### 5. WORKOUT-05: Distribuzione 80/20

**Test:** Chiedi "pianifica la settimana" o usa generate_mesocycle. Conta sessioni Z1-Z2 vs qualità
**Expected:** >= 80% Z1-Z2, qualità (Z4-Z5) su giorni non consecutivi, Z3 minimizzato
**Why human:** Distribuzione è proprietà del piano generato — richiede conteggio manuale dell'output

---

### Gaps Summary

Nessun gap bloccante identificato. Tutti gli artefatti esistono, sono sostanziali e wired correttamente. Il dato `current_progression_step: null` è comportamento atteso (nessun mesociclo con progression_plan ancora, Pitfall 6 documentato).

Lo status `human_needed` riflette che WORKOUT-01/02/04/05 (e la dimensione comportamentale di WORKOUT-03) non sono verificabili staticamente — richiedono osservazione dell'output LLM in Claude.ai con MCP attivo. La SUMMARY di Plan 04 documenta un "approvato" dell'atleta, ma il verifier non può retro-verificare quell'osservazione in modo riproducibile.

---

### Pre-existing test failure (out of scope di Phase 5)

`tests/test_live_behavior.py::test_verify04_session_analysis_routes_to_gemini` — failure intermittente per contaminazione `sys.modules` da `test_fitness_test.py`. Pre-esistente da Phase 4, documentato in `deferred-items.md`. Il test passa in isolamento (`pytest tests/test_live_behavior.py::test_verify04_session_analysis_routes_to_gemini -v` → PASSED).

---

_Verified: 2026-06-08T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
