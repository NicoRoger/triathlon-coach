# Phase 5: Workout Prescription Quality — Research

**Researched:** 2026-06-07
**Domain:** LLM skill prompt engineering + TypeScript MCP Worker extension + PostgreSQL migration (Supabase)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Percorso prescrizioni (primary path)**
- D-01: Primary path = Claude Opus via Claude.ai MCP. Nessun script auto Python in Phase 5.
- D-02: `propose_session.md` e `generate_mesocycle.md` rendono `get_physiology_zones` come **step 1 obbligatorio**.
- D-03: Template sessione include warmup/main set con intervalli espliciti/cooldown come **sezioni obbligatorie**.
- D-04: Script auto domenicale → Phase 7 (AUTO-02).

**FTP bici test**
- D-05: `get_physiology_zones` espone `valid_from` + `age_days` per ogni disciplina.
- D-06: `fitness_test.md` aggiornato: controlla FTP age; se null o `age_days > 42` propone test.
- D-07: Nessun auto-trigger Python — il coach (Claude.ai Opus) decide il timing.

**Struttura JSONB sessioni**
- D-08: Ogni sessione via `commit_plan_change` DEVE includere `structured` JSONB.
- D-09: Formato canonical: flat steps list `[{name, duration_s, zone, target_value, reps?, notes?}]`.
- D-10: Nomi step obbligatori: almeno un "warmup", "main_set" (con intervalli), un "cooldown".
- D-11: Enforcement via skill prompt — nessuna validazione TypeScript nel Worker MCP.

**Vincoli medici dinamici**
- D-12: Nuova tabella `active_constraints` con schema: `(id UUID, type TEXT, discipline TEXT, description TEXT, severity TEXT, created_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ nullable)`.
- D-13: Dati iniziali: spalla dx (swim, injury, Z1-Z2 max) + fascite sx (run, injury, +10%/settimana, cap 14-15km).
- D-14: Nuovo MCP tool `update_constraint(id, resolved_at)`.
- D-15: `get_weekly_context` restituisce `active_constraints` (solo `resolved_at IS NULL`).
- D-16: Skill prompts leggono vincoli da `get_weekly_context.active_constraints`, non da CLAUDE.md statico.

**Gap 1 — Sessioni recenti disciplina-specifiche**
- D-17: `propose_session` chiama `get_activity_history` (disciplina, 14gg, limit 3).
- D-18: RPE medio ≥ 8.0 o pattern fatica neuromuscolare → volume main set ridotto di 1 step.

**Gap 2 — Zone contestualizzate**
- D-19: Perceived effort (non numeri assoluti) se ≥2 fattori avversi: T°>25°C, TSB<-10, sleep<65.
- D-20: Nota esplicita nella prescrizione con riferimento alla condizione avversa.

**Gap 3 — Razionale mesociclo**
- D-21: Ogni prescrizione include sezione "Contesto mesociclo" con dati da `get_weekly_context`.
- D-22: Razionale esplicito (non generico): settimana N/3, TSS accumulato/target, ruolo della sessione.

**Gap 4 — Drill tecnici specifici**
- D-23: Drill tecnici specifici per disciplina integrati nella prescrizione.
- D-24: Drill obbligatori nel main set o warmup (non opzionali).

**Gap 5 — Race-pace Lavarone**
- D-25: Race-pace calibrato su `race_prediction` + `get_race_context`.
- D-26: Target aggiornati automaticamente con la fitness corrente.

**Gap 6 — Progressione multi-sessione**
- D-27: Progressione qualità in `mesocycles.progression_plan` JSONB.
- D-28: `get_weekly_context` espone `current_progression_step` per tipo sessione di qualità.

### Claude's Discretion
- Struttura interna dei drill per disciplina nel prompt (ordine, volume drill vs. volume principale)
- Threshold esatto di riduzione pace per zona contestualizzata (range "5-8%" o specifico per condizione)
- Schema DB `active_constraints` per campi aggiuntivi (es. `source`, `notes`)
- Formato esatto della sezione "Contesto mesociclo" nel template output
- Numero di strides/drill per sessione in base a durata totale

### Deferred Ideas (OUT OF SCOPE)
- Script auto domenicale piano settimanale → Phase 7 (AUTO-02)
- Adattamento fisiologico intelligente → Phase 6
- Qualità analisi post-sessione → Phase 9
- Qualità brief mattutino → Phase 8
- MCP auth hardening → Phase 11
- Sessioni proattive da illness/injury flag → Phase 7
- Cross-training specifico MTB → Phase 6/7
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WORKOUT-01 | Ogni sessione proposta include struttura completa: warmup (durata + intensità), main set (intervalli specifici con target watt/pace/HR), cooldown — mai solo "60 min Z2" | Sezione "Gaps in propose_session.md" + template D-03 |
| WORKOUT-02 | Zone prescritte usano valori misurati da `physiology_zones` (FTP bici, soglia corsa, CSS nuoto) — mai stime hard-coded | Sezione "Current state of get_physiology_zones" + D-02 |
| WORKOUT-03 | Ogni sessione rispetta vincoli medici attivi: nuoto max Z1-Z2, corsa +10%/settimana max, nessun Z4+ con spalla | Sezione "active_constraints migration" + D-12/D-15/D-16 |
| WORKOUT-04 | TSS atteso documentato e coerente con target settimanale del mesociclo | D-21/D-22 + mesocycles.progression_plan migration |
| WORKOUT-05 | Distribuzione settimanale rispetta 80/20 (Seiler/Laursen): Z3 minimizzato, qualità su giorni non consecutivi | D-28 + current_progression_step in get_weekly_context |
</phase_requirements>

---

## Summary

Phase 5 è interamente una fase di **skill prompt upgrade + MCP Worker extension + DB migration**. Non tocca la pipeline Python di ingest, analytics, né il briefing.py — questi sono confermati funzionanti da Phase 4.

Le tre categorie di lavoro sono:

1. **Skill prompt rewrite** (`skills/propose_session.md`, `skills/generate_mesocycle.md`, `skills/fitness_test.md`): aggiunta di step obbligatori, template strutturati, logica di contestualizzazione.

2. **MCP Worker extension** (`workers/mcp-server/src/index.ts`): aggiunta `update_constraint` tool, estensione `get_physiology_zones` con `valid_from`/`age_days`, estensione `get_weekly_context` con `active_constraints` e `current_progression_step`.

3. **DB migration** (`migrations/`): nuova tabella `active_constraints`, seed dati iniziali, aggiunta colonna `progression_plan` JSONB a `mesocycles`.

**Primary recommendation:** Scrivere i 3 skill prompts e le 2 estensioni MCP prima del deploy Worker. La migration SQL può essere eseguita in Supabase indipendentemente.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Prescrizioni sessioni strutturate | LLM (Claude.ai Opus via skill prompts) | MCP Worker (dati) | Il coach AI genera la prescrizione; il Worker la persiste via commit_plan_change |
| Vincoli medici dinamici | DB (active_constraints) + MCP (get_weekly_context) | Skill prompt (lettura) | La fonte di verità è il DB, non CLAUDE.md statico |
| Zone fisiologiche | DB (physiology_zones) + MCP (get_physiology_zones) | briefing.py (read-only, già funzionante) | Calcolo zone deterministico già in fitness_test_processor.py |
| Progressione multi-sessione | DB (mesocycles.progression_plan) + MCP (get_weekly_context) | Skill prompt (lettura) | Il passo corrente viene letto dal DB, non hardcodato nel prompt |
| Enforcement vincoli JSONB | Skill prompt (instruction) | — | D-11: nessuna validazione TypeScript nel Worker |
| FTP age check | MCP (get_physiology_zones con age_days) | fitness_test.md (trigger) | Il Worker calcola l'età; il skill decide se proporre il test |

---

## Current State Analysis (Source Code Audit)

### `skills/propose_session.md` — Stato Attuale vs Required

**Presente:**
- Step 1: leggi `get_planned_session(today)` via MCP
- Step 2: leggi `get_recent_metrics(days=7)`
- Step 3: leggi `physiology_zones` correnti per disciplina (generico)
- Step 4: leggi `docs/coaching_observations.md` e `docs/athlete_beliefs.md`
- Step 5: adatta per readiness (3 livelli: ≥75, 50-74, <50)
- Step 5 (race week): controlla `activities.weather`
- Step 6: output strutturato con warmup/main set/cool-down/note

**Mancante rispetto alle decisioni:**
- D-02: `get_physiology_zones` non è dichiarato come **step 1 obbligatorio** con gate
- D-03: Il template mostra warmup/main set/cooldown, ma non dichiara obbligatorietà assoluta
- D-05: Non legge `valid_from`/`age_days` dal response di `get_physiology_zones`
- D-06: Non controlla se FTP è null o > 42 giorni
- D-15/D-16: Non chiama `get_weekly_context` per leggere `active_constraints` (legge CLAUDE.md statico)
- D-17: Non chiama `get_activity_history` per ultime 3 sessioni stessa disciplina (14gg)
- D-18: Nessuna logica di riduzione volume su RPE medio ≥ 8.0
- D-19/D-20: Nessuna contestualizzazione zone per fattori avversi
- D-21/D-22: Nessuna sezione "Contesto mesociclo" nel template
- D-23/D-24: Sezione drill tecnici assente
- D-25/D-26: Nessuna chiamata a `race_prediction`/`get_race_context` per race-pace
- D-28: Non legge `current_progression_step` da `get_weekly_context`

**Impatto:** Il skill produce prescrizioni che potrebbero essere incomplete (es. "60 min Z2") senza warmup/cooldown dettagliato, senza vincoli medici dinamici, senza contestualizzazione.

---

### `skills/generate_mesocycle.md` — Stato Attuale vs Required

**Presente:**
- Step 1-8: procedura già solida con lettura CLAUDE.md, docs, metriche recenti, physiology_zones, multi-race awareness
- Step 8: chiama `get_weekly_context` per `upcoming_races` (ma non per `active_constraints`)
- Calcolo CTL target settimanale
- Distribuzione 80/20
- Commit flow: `commit_mesocycle` + `commit_plan_change` per ogni sessione
- Citation obbligatoria (già implementata con source tags)
- Output prediction (già previsto)

**Mancante:**
- D-02: `get_physiology_zones` come step 1 esplicito con gate (già nella procedura ma non enforcato come step 0 obbligatorio prima di tutto il resto)
- D-03: Template mostra sessioni sintetiche ("Z2 corsa 60min"), non format con warmup/main/cooldown
- D-15/D-16: `get_weekly_context` viene usato solo per `upcoming_races`, non per `active_constraints`
- D-27: `commit_mesocycle` non include `progression_plan` JSONB nel payload

---

### `skills/fitness_test.md` — Stato Attuale vs Required

**Presente:**
- Logica "quando proporre" con riferimento alle 6 settimane (testo, non tool call)
- Protocollo di proposta con `commit_plan_change`
- Ciclo test consigliato (FTP → soglia → CSS → LTHR)
- Aggiornamento automatico CLAUDE.md

**Mancante:**
- D-05/D-06: Non chiama `get_physiology_zones('bike')` per leggere `age_days` — la condizione "6 settimane" è scritta nel testo ma non basata su dati DB. Il skill deve diventare data-driven.

---

### `workers/mcp-server/src/index.ts` — Stato Attuale vs Required

**`get_physiology_zones` — Stato Attuale:**
```typescript
// Restituisce: {generated_at, zones: [{discipline, ftp_w, threshold_pace_s_per_km, 
//              css_pace_s_per_100m, lthr, hr_max, valid_from, valid_to, ...}], note?}
```
- La query SQL include già `valid_from` nella select implicita (nessun `select=` esplicito, ritorna tutte le colonne)
- **Il campo `valid_from` è già disponibile nel response** perché `sb()` ritorna l'intera riga
- **Manca:** calcolo `age_days = NOW() - valid_from` da aggiungere come campo calcolato nel response object

**`get_weekly_context` — Stato Attuale:**
- Restituisce: health, daily_metrics, daily_wellness, completed_activities, subjective_log, planned_past, planned_upcoming, session_analyses, open_modulations, active_mesocycle, upcoming_races
- **Manca `active_constraints`:** nuova query `active_constraints?resolved_at=is.null` da aggiungere alla `Promise.all()`
- **Manca `current_progression_step`:** da derivare da `mesocycles.progression_plan` JSONB e settimana corrente del mesociclo attivo

**Tools esistenti — già compatibili:**
- `get_activity_history(sport, days)`: già esiste, già filtra per sport e days — D-17 può usarlo direttamente
- `get_session_review_context`: già esiste, include `session_analyses` — per D-17 il skill chiama `get_activity_history` + legge RPE dalle attività
- `commit_plan_change`: già accetta `structured` come campo opzionale — serve solo l'enforcement nel prompt (D-08/D-09/D-10/D-11)
- `commit_mesocycle`: già esiste ma **non accetta `progression_plan`** nel payload — da aggiungere

**Tool mancante:**
- `update_constraint(id, resolved_at)`: nuovo tool da aggiungere per D-14

---

### `sql/schema.sql` — Stato Attuale vs Required

**Tabella `mesocycles` — Stato Attuale:**
```sql
CREATE TABLE mesocycles (
    id UUID PRIMARY KEY,
    name TEXT, phase TEXT, start_date DATE, end_date DATE,
    target_race_id UUID,
    weekly_pattern JSONB,   -- già presente
    notes TEXT,
    created_at, updated_at
)
```
- **Manca `progression_plan JSONB`**: da aggiungere con migration

**Tabella `physiology_zones` — Stato Attuale:**
```sql
-- valid_from DATE NOT NULL già presente
-- Unique constraint: (discipline, valid_from, method) già aggiunto in resilience-audit.sql
```
- Nessuna modifica necessaria

**Tabella `planned_sessions` — Stato Attuale:**
```sql
-- structured JSONB già presente
-- Unique constraint: (planned_date, sport, session_type) già aggiunto in resilience-audit.sql
```
- Nessuna modifica necessaria

**Tabella mancante:**
```sql
CREATE TABLE active_constraints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type TEXT NOT NULL CHECK (type IN ('injury', 'medical', 'tactical')),
    discipline TEXT NOT NULL CHECK (discipline IN ('swim', 'bike', 'run', 'all')),
    description TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('high', 'medium', 'low')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ   -- NULL = attivo
);
```

---

### `coach/planning/briefing.py` — Stato Attuale (READ-ONLY per Phase 5)

**`_format_structured(structured)`** — già gestisce:
- `structured` come `dict` con chiave `steps`, `intervals`, o `workout`
- `structured` come lista diretta
- Step come `dict` con campi: `name`/`label`, `reps`, `duration_s`/`duration`, `zone`/`target`/`intensity`
- **Il formato canonical D-09 (`[{name, duration_s, zone, target_value, reps?, notes?}]`) è già compatibile** — nessuna modifica necessaria

**`_format_session_zones(sport, zones_by_discipline)`** — già:
- Legge `valid_from` dalla query (campo incluso in `_fetch_current_zones`)
- **`valid_from` è già nel response di `_fetch_current_zones`** — ma non viene esposto nell'output del brief come "data test" o "age_days"

**`_build_warnings_section(metrics)`** — problema rilevante:
- Legge vincoli medici da `os.environ.get("SHOULDER_ACTIVE", "true")` e `os.environ.get("PLANTAR_ACTIVE", "true")`
- **Questo è il pattern "statico" che D-16 vuole eliminare dalle skill prompts** (non dal briefing.py che resta immutato)
- **Phase 5 non modifica briefing.py** — il dynamic constraint reading è solo nei skill prompts MCP

---

## Migration Pattern (da resilience-audit.sql)

Il pattern stabilito per le migration in questo progetto:

```sql
-- Idempotente con DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- Usa ADD COLUMN IF NOT EXISTS per colonne
-- Usa CREATE TABLE IF NOT EXISTS per tabelle
-- Seed con INSERT ... ON CONFLICT DO NOTHING
```

**Migration da creare per Phase 5:** `migrations/2026-06-07-workout-prescription-quality.sql`

Contenuto atteso:
1. `CREATE TABLE IF NOT EXISTS active_constraints (...)` con RLS enable
2. `ALTER TABLE mesocycles ADD COLUMN IF NOT EXISTS progression_plan JSONB`
3. `INSERT INTO active_constraints ...` per spalla dx e fascite sx (seed dati D-13)

---

## Standard Stack

### Core (tutti già in uso nel progetto — nessuna nuova dipendenza)

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| TypeScript (Cloudflare Workers) | 5.4 (pinned) | MCP Worker extension | Già usato per tutto il Worker |
| Supabase REST API | via `sb()` helper | Query `active_constraints`, `mesocycles.progression_plan` | Già il pattern di tutte le query nel Worker |
| Markdown skill prompts | plain text | Coaching instructions per Claude.ai Opus | Pattern consolidato in `skills/*.md` |
| PostgreSQL (Supabase) | managed | Nuova tabella `active_constraints`, colonna `progression_plan` | Già il DB del progetto |

### Supporting (nessuna nuova libreria)

- `uuid-ossp` extension: già abilitata — UUID per `active_constraints.id`
- `trigger_set_updated_at`: già esiste — **non applicabile a `active_constraints`** (nessuna colonna `updated_at` in questo schema)

### Package Legitimacy Audit

> Phase 5 non installa nuovi pacchetti npm o Python. Tutte le modifiche sono su file esistenti (TypeScript, Markdown, SQL). Questa sezione è N/A.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (nessuno) | — | N/A — nessuna nuova dipendenza |

---

## Architecture Patterns

### System Architecture Diagram

```
Claude.ai Opus (skill prompts)
    |
    | 1. get_physiology_zones(discipline) — STEP OBBLIGATORIO
    | 2. get_weekly_context() — active_constraints + current_progression_step
    | 3. get_activity_history(sport, 14d, limit 3) — RPE disciplina
    |
    v
MCP Worker (Cloudflare Worker)
    |── getPhysiologyZones: zones + valid_from + age_days [EXTENDED]
    |── getWeeklyContext: + active_constraints + current_progression_step [EXTENDED]
    |── updateConstraint(id, resolved_at) [NEW]
    |── commitPlanChange(structured=[flat steps]) [UNCHANGED]
    |── commitMesocycle(progression_plan={...}) [EXTENDED]
    |
    v
Supabase PostgreSQL
    |── physiology_zones (valid_from già presente)
    |── active_constraints [NEW TABLE]
    |── mesocycles.progression_plan [NEW COLUMN]
    |── planned_sessions.structured (già accetta JSONB)
```

### Recommended Project Structure (invariata)

```
skills/
├── propose_session.md     # REWRITE — aggiungere D-02,D-06,D-15..D-28
├── generate_mesocycle.md  # UPDATE — aggiungere D-02,D-03,D-15,D-27
└── fitness_test.md        # UPDATE — aggiungere D-05,D-06

workers/mcp-server/src/
└── index.ts               # UPDATE — +update_constraint, extend get_physiology_zones/get_weekly_context/commit_mesocycle

migrations/
└── 2026-06-07-workout-prescription-quality.sql  # NEW
```

### Pattern 1: `get_physiology_zones` con `age_days`

**What:** Aggiungere campo calcolato `age_days` a ogni zona nel response, basato su `valid_from`.

```typescript
// Source: codebase audit — workers/mcp-server/src/index.ts getPhysiologyZones()
// CURRENT: restituisce rows così come vengono da Supabase
// EXTENDED: aggiunge age_days calcolato

const today = new Date(todayRomeISO());
for (const zone of current) {
  if (zone.valid_from) {
    const validFrom = new Date(zone.valid_from);
    const diffMs = today.getTime() - validFrom.getTime();
    zone.age_days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  } else {
    zone.age_days = null;
  }
}
```

### Pattern 2: `get_weekly_context` con `active_constraints`

**What:** Aggiungere query a `active_constraints` nella Promise.all() esistente.

```typescript
// Source: codebase audit — getWeeklyContext() in index.ts
// Aggiungere alla Promise.all():
sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`),

// E al return object:
active_constraints: constraints || [],
```

### Pattern 3: `current_progression_step` da `mesocycles.progression_plan`

**What:** Derivare il passo corrente leggendo la settimana del mesociclo attivo.

```typescript
// Source: codebase audit — active_mesocycle è già letto in getWeeklyContext
// Logica: calcola settimana corrente nel mesociclo, legge progression_plan[type][weekN]
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

### Pattern 4: `update_constraint` tool

**What:** Nuovo tool per risolvere un vincolo medico.

```typescript
// Source: codebase audit — pattern commitPlanChange in index.ts
const tool = {
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
};

async function updateConstraint(args: any, env: Env): Promise<any> {
  const resolvedAt = args.resolved_at || new Date().toISOString();
  const resp = await fetch(
    `${env.SUPABASE_URL}/rest/v1/active_constraints?id=eq.${args.id}`,
    {
      method: "PATCH",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
      },
      body: JSON.stringify({ resolved_at: resolvedAt }),
    }
  );
  if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
  return { status: "resolved", id: args.id, resolved_at: resolvedAt };
}
```

### Pattern 5: Migration SQL — `active_constraints`

```sql
-- Source: codebase audit — pattern da 2026-06-01-resilience-audit.sql
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

-- Seed dati D-13
INSERT INTO active_constraints (type, discipline, description, severity) VALUES
  ('injury', 'swim', 'borsite + tendinopatia CLB spalla destra: max Z1-Z2, zero Z4+, distanza 72h tra sessioni nuoto', 'high'),
  ('injury', 'run', 'fascite plantare sinistra: max +10% volume/settimana, cap 14-15km/settimana attuale, asintomatica da 14gg', 'medium')
ON CONFLICT DO NOTHING;
```

### Pattern 6: Formato canonical `structured` JSONB

```json
{
  "structured": [
    {"name": "warmup",    "duration_s": 900,  "zone": "Z1-Z2", "notes": "progressivo"},
    {"name": "drill",     "reps": 4, "duration_s": 50, "zone": "Z1", "target_value": "fingertip drag"},
    {"name": "main_set",  "reps": 6, "duration_s": 360, "zone": "Z4", "target_value": 210, "notes": "@ 105% FTP"},
    {"name": "cooldown",  "duration_s": 600,  "zone": "Z1"}
  ]
}
```

Il campo `target_value` deve essere il valore numerico preciso da `physiology_zones`:
- Bici: watt (es. 210W per FTP 200W × 105%)
- Corsa: s/km (es. 263 per soglia 4:23/km)
- Nuoto: s/100m (es. 85 per CSS-5 se CSS=80)

`_format_structured()` in `briefing.py` già gestisce questo formato senza modifiche.

### Anti-Patterns to Avoid

- **Hard-coded physiological values**: mai scrivere "4:23/km" o "200W" nel skill prompt — sempre da `get_physiology_zones`
- **Vincoli da CLAUDE.md statico**: D-16 proibisce esplicitamente questa pratica — usare `get_weekly_context.active_constraints`
- **Skill prompt senza gate su physiology_zones**: se il tool call non viene fatto, il skill non ha i dati per prescrivere
- **`structured` come dict annidato**: `briefing.py` cerca `.get("steps")`, `.get("intervals")`, `.get("workout")` — ma il formato canonical D-09 è lista diretta, compatibile perché `isinstance(structured, list)` è gestito

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Calcolo zone fisiologiche | Formule nel prompt | `get_physiology_zones` → response già contiene `ftp_w`, `threshold_pace_s_per_km`, `css_pace_s_per_100m` | `derive_zones_for_discipline()` già usato in `briefing.py`; zone già calcolate nel DB via notes JSONB |
| Rendering `structured` nel brief | Modifiche a `briefing.py` | Nessuna modifica — `_format_structured()` già compatibile | Il flat steps list è già gestito |
| Calcolo settimana nel mesociclo | Script Python separato | Logica TypeScript in `getWeeklyContext` | Già si calcola `active_mesocycle` con query Supabase |
| Pattern coaching per drill | Training knowledge nel prompt | `docs/elite_training_reference.md` + `docs/coaching_observations.md` | Dati reali Nicolò (114 sessioni élite) già disponibili |
| RLS policy per `active_constraints` | Nuova policy per utente | Pattern esistente: nessuna policy = solo `service_role` accede | Single-user system — stesso pattern di tutte le altre tabelle |

---

## Common Pitfalls

### Pitfall 1: `valid_from` è DATE, non TIMESTAMPTZ — calcolo age_days

**What goes wrong:** `age_days = Math.floor((Date.now() - new Date(valid_from).getTime()) / 86400000)` può dare risultati errati se `valid_from` è una stringa `DATE` (es. `"2026-06-04"`) senza timezone.
**Why it happens:** `new Date("2026-06-04")` viene interpretata come UTC mezzanotte, mentre oggi-Rome potrebbe essere un giorno diverso.
**How to avoid:** Usare `todayRomeISO()` (già disponibile nel Worker) come baseline e fare differenza di stringhe o parsare entrambe come Rome date.
**Warning signs:** `age_days` risulta 1 giorno più alto del previsto per test eseguiti dopo mezzanotte UTC ma prima di mezzanotte Rome.

### Pitfall 2: `commitMesocycle` ignora `progression_plan` senza errore

**What goes wrong:** Il codice `commitMesocycle` costruisce il payload senza includere `progression_plan` anche se passato negli args — perché la lista `if (args.X !== undefined) payload.X = args.X` non lo include ancora.
**Why it happens:** Codebase audit conferma: `commitMesocycle` accetta solo `name, phase, start_date, end_date, target_race_id, weekly_pattern, notes` — `progression_plan` verrà silenziosamente ignorato.
**How to avoid:** Aggiungere `if (args.progression_plan !== undefined) payload.progression_plan = args.progression_plan;` nel payload builder di `commitMesocycle`. E aggiornare il `inputSchema` del TOOLS array.
**Warning signs:** `commit_mesocycle` ritorna `{status: "created"}` ma il campo `progression_plan` è null nel DB.

### Pitfall 3: `get_weekly_context` `Promise.all()` — nuova query aumenta latenza

**What goes wrong:** Aggiungere una query a `active_constraints` nella `Promise.all()` può aumentare la latenza se la tabella è nuova e non ha index.
**Why it happens:** Supabase ha startup cost per nuove tabelle senza dati/index.
**How to avoid:** La tabella avrà sempre ≤10 righe (vincoli medici, non dati di training). Nessun index necessario. La query `?resolved_at=is.null` è rapida su tabella piccola.
**Warning signs:** Non applicabile per questa dimensione di dati.

### Pitfall 4: Skill prompt `propose_session` — ordine step obbligatorio

**What goes wrong:** Se il prompt elenca `get_physiology_zones` come step 3 (dopo `get_planned_session` e `get_recent_metrics`), il coach potrebbe iniziare a rispondere prima di avere i dati fisiologici.
**Why it happens:** LLM tende a iniziare con i tool call che sembrano "setup" e può procedere in modo interleaved.
**How to avoid:** D-02 specifica `get_physiology_zones` come **step 1 obbligatorio con gate** — il testo del prompt deve dichiarare esplicitamente: "NON procedere con la prescrizione finché non hai ricevuto il response di `get_physiology_zones`. Se la disciplina non ha zone registrate, proponi un test fitness invece."
**Warning signs:** Prescrizione che usa watt/pace generici o stimati, non i valori numerici specifici del response.

### Pitfall 5: `active_constraints` seed — idempotenza

**What goes wrong:** `INSERT INTO active_constraints ... ON CONFLICT DO NOTHING` fallisce se non c'è un UNIQUE constraint sulla tabella.
**Why it happens:** La tabella non ha un natural key ovvio (description può cambiare).
**How to avoid:** Due opzioni: (a) aggiungere UNIQUE (discipline, type) se ogni disciplina ha al più un vincolo per tipo, oppure (b) usare `INSERT ... WHERE NOT EXISTS (...)`. Opzione (b) è più robusta.
**Warning signs:** Migration eseguita due volte inserisce due righe duplicate per spalla/fascite.

### Pitfall 6: `current_progression_step` — mesociclo non ancora committato

**What goes wrong:** Se nessun mesociclo è attivo in DB (start_date ≤ today ≤ end_date), `active_mesocycle` è null e `current_progression_step` non può essere calcolato.
**Why it happens:** Phase 5 presuppone che esista un mesociclo in DB, ma Nicolò potrebbe non averne committato uno ancora.
**How to avoid:** `deriveProgressionStep` deve gestire gracefully il caso null: ritorna `null` invece di crashare. Il skill deve avere un fallback: "Se `current_progression_step` è null, proponi il primo passo della progressione standard."
**Warning signs:** Tool call `get_weekly_context` ritorna `current_progression_step: null` anche se c'è un mesociclo in DB.

### Pitfall 7: Formato `structured` — `target_value` per nuoto

**What goes wrong:** Per il nuoto, `target_value` in secondi per 100m è un numero alto (es. 85) che potrebbe essere confuso con watt o s/km.
**Why it happens:** Unità diverse per disciplina senza tag esplicito di unità nel JSONB.
**How to avoid:** Il skill prompt deve specificare la nota `"notes": "CSS-5: 1:35/100m"` per rendere il valore umano-leggibile. Il campo `target_value` rimane numerico per future elaborazioni programmatiche.
**Warning signs:** Brief che mostra "target_value: 85" senza contesto di unità.

---

## Code Examples

### propose_session.md — Struttura step obbligatoria (D-02, D-03)

```markdown
## Procedura obbligatoria (NON saltare nessuno step)

### Step 0 — GATE FISIOLOGICO (obbligatorio, nessuna prescrizione senza questo)
Chiama `get_physiology_zones(discipline)` dove discipline è il sport della sessione.
- Se il response ha `zones: []` o `note: "Nessuna zona..."`: NON prescrivere. Proponi test fitness.
- Se `age_days > 42`: segnala che le zone potrebbero essere obsolete e suggerisci test.
- Estrai i valori precisi: `ftp_w`, `threshold_pace_s_per_km`, o `css_pace_s_per_100m`.
- Tutti i target numerici nella prescrizione DEVONO venire da questi valori.

### Step 1 — Sessione pianificata
Chiama `get_planned_session(today)`.

### Step 2 — Contesto settimanale + vincoli medici
Chiama `get_weekly_context()`. Estrai:
- `active_constraints`: vincoli medici attivi (resolved_at IS NULL). 
  Questi SOSTITUISCONO i vincoli hardcoded in CLAUDE.md — la fonte di verità è il DB.
- `active_mesocycle` + `current_progression_step`: passo corrente nella progressione.
- `daily_metrics`: TSB, HRV z-score, readiness.

### Step 3 — Storico disciplina (ultime 3 sessioni, 14gg)
Chiama `get_activity_history(sport=<disciplina>, days=14)`.
- Leggi RPE delle ultime 3 sessioni.
- Se RPE medio ≥ 8.0: riduci volume main set di 1 step (es. 5×6min → 4×6min).
  Aggiungi nota: "Volume ridotto: RPE medio ultimi 14gg = X.X/10."
```

### propose_session.md — Template output obbligatorio (D-03, D-09, D-10)

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

Commit struttura JSONB con `commit_plan_change` includendo:
- `target_tss`: [valore calcolato]
- `structured`: [lista flat steps — vedi formato D-09]
```

### fitness_test.md — FTP age check (D-05, D-06)

```markdown
## Step 0 — Check FTP age (SEMPRE per sessioni bici)

1. Chiama `get_physiology_zones('bike')`
2. Leggi `zones[0].age_days` nel response
3. Se `age_days > 42` (6 settimane) o zones è vuoto:
   "FTP non aggiornato da [age_days] giorni (>6 settimane). Propongo un test FTP bici.
   Data ottimale: [calcola: post 1-2gg Z2/recovery, non in settimana di carico max, non entro 10gg da gara A]
   TSB target al test: >0 per almeno 2 giorni."
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Vincoli medici in CLAUDE.md statico | `active_constraints` table + MCP read | Phase 5 | Vincoli si aggiornano quando la clinica cambia, senza modificare file |
| Zone fisiologiche hardcoded nel prompt | Sempre da `get_physiology_zones` con gate | Phase 5 | Prescrizioni automaticamente corrette quando FTP/CSS/threshold cambiano |
| Prescrizioni sintetiche ("60min Z2") | Template strutturato W/M/C obbligatorio | Phase 5 | Briefing automatico già formatta i step con `_format_structured()` |
| Progressione per settimana nella testa del coach | `mesocycles.progression_plan` JSONB in DB | Phase 5 | Coach AI legge sempre il passo corretto senza "ricordare" |

**Deprecated/outdated:**
- Lettura vincoli medici da CLAUDE.md nella logica skill: deprecato da D-16. `briefing.py` continua a leggere le env var (non modificato) ma i skill prompts usano il DB.
- Prescrizioni senza `structured` JSONB: deprecate da D-08 — ogni `commit_plan_change` deve includere il campo.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Supabase (PostgreSQL) | Migration `active_constraints`, query MCP | Confirmed (Phase 4 live) | Managed | — |
| Wrangler CLI | Deploy MCP Worker aggiornato | Confirmed (Phase 3 deploy) | 3.50 | — |
| Claude.ai Opus (MCP connector) | Esecuzione skill prompts | Confirmed (Phase 4 active) | Claude Pro subscription | — |

**Missing dependencies with no fallback:** nessuna.

---

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — sezione obbligatoria.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4 |
| Config file | `pytest.ini` (`testpaths = tests`) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WORKOUT-01 | Sessione con warmup/main/cooldown obbligatori | manual | Verifica manuale: proponi sessione in Claude.ai e controlla output | N/A — skill prompt |
| WORKOUT-02 | Zone da physiology_zones — nessun hard-code | manual | Verifica manuale: cambia FTP in DB e controlla se la prescrizione cambia | N/A — skill prompt |
| WORKOUT-03 | Vincoli medici da active_constraints (non CLAUDE.md) | integration | Script verify: query `active_constraints` returns 2 rows, `get_weekly_context` response include il campo | ❌ Wave 0 — `tests/test_active_constraints.py` |
| WORKOUT-04 | TSS documentato e coerente con mesociclo | manual | Verifica manuale: TSS proposto vs `mesocycles.progression_plan` | N/A — skill prompt |
| WORKOUT-05 | 80/20 distribuzione — Z3 minimizzato | manual | Verifica manuale: review piano settimanale | N/A — skill prompt |

**Note:** WORKOUT-01, 02, 04, 05 sono verificabili solo manualmente (dipendono dall'output LLM). WORKOUT-03 ha una componente verificabile con script: controllare che la migration abbia creato `active_constraints` con i 2 seed e che `get_weekly_context` la restituisca.

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (verifica regressioni suite esistente)
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Script di verifica `scripts/verify_prescription_quality.py` (da creare in Wave 0 con acceptance test WORKOUT-03 + check manuale degli altri 4 SC)

### Wave 0 Gaps

- [ ] `tests/test_active_constraints.py` — copre WORKOUT-03: verifica che la tabella esista in DB con le 2 righe seed, e che il response di `get_weekly_context` includa `active_constraints` come array
- [ ] `migrations/2026-06-07-workout-prescription-quality.sql` — la migration deve esistere prima di ogni altro task
- [ ] `scripts/verify_prescription_quality.py` — script read-only per phase gate: verifica WORKOUT-03 in modo automatico + checklist manuale per WORKOUT-01/02/04/05

---

## Security Domain

> `security_enforcement: true` in `.planning/config.json`, `security_asvs_level: 1`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | MCP auth non modificato in Phase 5 (Phase 11) |
| V3 Session Management | no | Stateless Worker |
| V4 Access Control | yes | `active_constraints` accessibile solo via service_role (RLS pattern esistente) |
| V5 Input Validation | yes | `update_constraint(id)` deve validare che `id` sia UUID valido prima della query |
| V6 Cryptography | no | Nessuna crittografia richiesta |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| UUID injection in `update_constraint(id)` | Tampering | Validare con `isUuid(id)` già disponibile nel Worker — usare la funzione esistente |
| SQL injection via `resolved_at` | Tampering | Supabase REST API con parametri URL-encoded — non raw SQL |
| Risoluzione vincolo medico non autorizzata | Elevation of Privilege | Tool `update_constraint` è dietro la stessa auth del Worker — unico atleta single-user |

---

## Open Questions

1. **Seed idempotenza per `active_constraints`**
   - What we know: ON CONFLICT DO NOTHING richiede un UNIQUE constraint
   - What's unclear: Usare UNIQUE (discipline, type) o WHERE NOT EXISTS pattern
   - Recommendation: UNIQUE (discipline, type) se si assume un solo vincolo per disciplina per tipo — altrimenti WHERE NOT EXISTS. Il planner dovrebbe scegliere WHERE NOT EXISTS per flessibilità futura (Nicolò potrebbe avere due vincoli swim simultanei).

2. **`current_progression_step` quando mesocycle null**
   - What we know: Se nessun mesociclo è attivo, `active_mesocycle` è null
   - What's unclear: Cosa deve fare il skill quando non c'è progressione in DB
   - Recommendation: Il skill deve avere fallback esplicito nel prompt: "Se `current_progression_step` è null o non disponibile, usa progressione conservativa (volume minore della media)."

3. **Deploy Worker — wrangler deploy necessario**
   - What we know: CLAUDE.md e ROADMAP confermano che ogni modifica al Worker richiede `wrangler deploy`
   - What's unclear: Il planner deve includere un task esplicito di deploy post-modifica
   - Recommendation: Includere task `wrangler deploy` come ultimo task di ogni wave che modifica `index.ts`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `physiology_zones` query già include tutte le colonne (no `select=` esplicito) → `valid_from` è nel response senza modifiche alla query SQL | Code Examples — Pattern 1 | Bassa: codice audit confermato, la query `sb(env, q)` non ha `select=` statement esplicito |
| A2 | `active_mesocycle` in `get_weekly_context` è già letto — `current_progression_step` può essere calcolato client-side nel Worker | Architecture Patterns | Media: se `mesocycles.progression_plan` non esiste come campo nella riga, il Worker ritorna null. Migration deve aggiungere la colonna prima. |
| A3 | Il brief mattutino (`briefing.py`) non richiede modifiche per Phase 5 — `_format_structured()` già compatibile con il formato canonical D-09 | Briefing.py section | Bassa: codebase audit confermato — flat list con `name, duration_s, zone` è già gestito |

**Tutti gli altri claim sono verificati da codebase audit (codice letto direttamente) o da decisioni utente in CONTEXT.md.**

---

## Sources

### Primary (HIGH confidence — codebase audit)
- `skills/propose_session.md` — letto direttamente, gap documentati
- `skills/generate_mesocycle.md` — letto direttamente, gap documentati
- `skills/fitness_test.md` — letto direttamente, gap documentati
- `workers/mcp-server/src/index.ts` — letto direttamente, ogni tool documentato
- `coach/planning/briefing.py` — letto direttamente, `_format_structured()` e `_format_session_zones()` analizzati
- `coach/coaching/fitness_test_processor.py` — letto direttamente, `derive_zones_for_discipline()` e zone calculators analizzati
- `sql/schema.sql` — letto direttamente, schema `mesocycles`, `physiology_zones`, `planned_sessions` verificati
- `migrations/2026-06-01-resilience-audit.sql` — letto direttamente, migration pattern documentato
- `.planning/phases/05-workout-prescription-quality/05-CONTEXT.md` — decisioni D-01..D-28 lette direttamente
- `.planning/config.json` — `nyquist_validation: true`, `security_enforcement: true` confermati

### Secondary (MEDIUM confidence)
- CLAUDE.md §2/§3/§5 — profilo atleta, metodologia, soglie HRV — letti nel system context
- `.planning/REQUIREMENTS.md` — acceptance criteria WORKOUT-01..05 — letti direttamente

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — nessuna nuova dipendenza, tutto già nel progetto
- Skill prompt gaps: HIGH — codebase audit diretto su tutti e 3 i file skill
- MCP Worker extension: HIGH — codebase audit diretto su `index.ts`, ogni funzione analizzata
- DB migration pattern: HIGH — pattern da migration esistente letto direttamente
- Pitfalls: HIGH — derivati da analisi diretta del codice (age_days, progression_plan silently ignored, seed idempotenza)
- Validation/test coverage: MEDIUM — WORKOUT-01/02/04/05 sono intrinsecamente manuali (output LLM)

**Research date:** 2026-06-07
**Valid until:** 2026-09-01 (skill prompts e Worker sono stabili; rischio principale è cambio fisiologia Nicolò che aggiorna `physiology_zones`)
