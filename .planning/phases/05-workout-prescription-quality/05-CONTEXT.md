# Phase 5: Workout Prescription Quality - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Elevare la qualità delle prescrizioni di allenamento a livello coach professionista — sessioni strutturate con warmup/main set con intervalli specifici/cooldown, calibrate su fisiologia misurata (`physiology_zones`), contestualizzate al mesociclo corrente, con drill tecnici specifici per Nicolò, e adattate dinamicamente a condizioni ambientali e stato dell'atleta.

**In scope:**
- Skill prompt upgrade: `propose_session.md`, `generate_mesocycle.md`, `fitness_test.md`
- Struttura JSONB obbligatoria per ogni sessione via `commit_plan_change`
- FTP bici: `get_physiology_zones` include `valid_from` + età in giorni; `fitness_test.md` propone test se null o >6 settimane
- Nuova tabella `active_constraints` + MCP tool `update_constraint` per vincoli medici dinamici
- `get_weekly_context` esteso: `active_constraints` + mesocycle progression step
- Lettura ultime 3 sessioni stessa disciplina (14gg) + session_analyses prima di prescrivere
- Zone contestualizzate dinamicamente: adjusted se ≥2 fattori avversi (caldo/TSB/sonno)
- Drill tecnici specifici per Nicolò integrati nelle prescrizioni
- Race-pace Lavarone via `race_prediction` + `get_race_context`
- Progressione multi-sessione tracciata in `mesocycles` table

**Out of scope:**
- Script auto domenicale per piano settimanale → Phase 7 (AUTO-02)
- Adattamento fisiologico intelligente (cedimento muscolare vs cardiovascolare) → Phase 6
- Qualità analisi post-sessione → Phase 9
- Qualità brief mattutino → Phase 8
- MCP auth hardening → Phase 11

**Principio trasversale:** ogni dato letto dinamicamente dal DB via MCP — non hard-coded — così le prescrizioni restano corrette quando fitness, infortuni e fisiologia cambiano.

</domain>

<decisions>
## Implementation Decisions

### Percorso prescrizioni (primary path)
- **D-01:** Primary path = Claude Opus via Claude.ai MCP — l'atleta genera il piano interattivamente con il coach AI. Nessun script auto Python in Phase 5.
- **D-02:** `propose_session.md` e `generate_mesocycle.md` rendono `get_physiology_zones` come **step 1 obbligatorio** (non opzionale). Se il tool call non viene fatto, il skill non può proseguire con la prescrizione.
- **D-03:** Template sessione include warmup/main set con intervalli espliciti/cooldown come **sezioni obbligatorie** — mai prescrivere "60min Z2" come unica riga.
- **D-04:** Script auto domenicale per piano settimanale → Phase 7 (AUTO-02), come da roadmap.

### FTP bici test
- **D-05:** `get_physiology_zones` MCP tool espone `valid_from` + `age_days` per ogni disciplina nel payload di risposta.
- **D-06:** `fitness_test.md` skill aggiornato: il coach controlla FTP age dal `get_physiology_zones` response. Se FTP null o `age_days > 42` (6 settimane): propone test con data ottimale (post 1-2gg Z2/recovery, non in settimana di carico massimo).
- **D-07:** Nessun auto-trigger Python — è il coach (Claude.ai Opus) a decidere il timing in base a TSB/CTL. Il sistema fornisce i dati; il coach prende la decisione.

### Struttura JSONB sessioni
- **D-08:** Ogni sessione via `commit_plan_change` **DEVE** includere il campo `structured` JSONB popolato.
- **D-09:** Formato canonical: **flat steps list** `[{name, duration_s, zone, target_value, reps?, notes?}]` — già compatibile con `_format_structured()` in `briefing.py`.
- **D-10:** Nomi step obbligatori: almeno un "warmup", uno o più "main_set" (con dettaglio intervalli), un "cooldown". Il campo `target_value` deve contenere il valore numerico preciso da `physiology_zones` (es. watt, s/km, s/100m).
- **D-11:** Enforcement via skill prompt — nessuna validazione TypeScript nel Worker MCP (JSONB accetta qualsiasi formato; la qualità dipende dall'instruction al coach AI).

### Vincoli medici dinamici
- **D-12:** Nuova tabella `active_constraints` con schema: `(id UUID, type TEXT, discipline TEXT, description TEXT, severity TEXT, created_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ nullable)`.
- **D-13:** Dati iniziali da inserire: (a) spalla dx — type='injury', discipline='swim', description='borsite + tendinopatia CLB: max Z1-Z2, no Z4+'; (b) fascite sx — type='injury', discipline='run', description='+10%/settimana max, cap 14-15km/settimana'.
- **D-14:** Nuovo MCP tool `update_constraint(id, resolved_at)` via Claude.ai — il coach marca il vincolo come risolto dopo valutazione clinica.
- **D-15:** `get_weekly_context` restituisce `active_constraints` come array strutturato (solo righe con `resolved_at IS NULL`).
- **D-16:** Skill prompts leggono vincoli da `get_weekly_context.active_constraints` — **non da CLAUDE.md statico**. Questo garantisce che quando un vincolo viene risolto, sparisce automaticamente dalle prescrizioni.

### Gap 1 — Sessioni recenti disciplina-specifiche
- **D-17:** `propose_session` include come step obbligatorio: chiamata `get_activity_history` per la disciplina della sessione odierna, filtrata sugli ultimi 14gg, limit 3. Legge anche le `session_analyses` corrispondenti per RPE e pattern fatica.
- **D-18:** Se dalle ultime 3 sessioni emerge RPE medio ≥ 8.0 o pattern "fatica neuromuscolare" (HR drift > 15bpm nelle ultime 20min di intensità): abbassa il volume del main set di 1 step (es. 5×6min → 4×6min) e aggiunge nota esplicita.

### Gap 2 — Zone contestualizzate
- **D-19:** Il target di zona viene espresso come **perceived effort** (non pace/watt assoluti) se ≥2 delle seguenti condizioni sono presenti al momento della prescrizione: temperatura prevista >25°C (da `daily_metrics.weather` o forecast), TSB <-10, sleep score <65.
- **D-20:** Nota esplicita nella prescrizione: "Condizioni avverse: corri a sensazione Z4 — oggi [condizione]. Pace di riferimento: ~4:30-4:35/km invece di 4:23/km."

### Gap 3 — Razionale mesociclo
- **D-21:** Ogni prescrizione include una sezione **"Contesto mesociclo"** con: settimana corrente (1/2/3/scarico), TSS settimanale accumulato vs target, sessioni di qualità già fatte questa settimana, ruolo della sessione odierna nel piano. Dati da `get_weekly_context`.
- **D-22:** Il razionale deve essere esplicito: "Settimana 2/3 del blocco build. TSS accumulato: 280/400. Già 1 sessione qualità (soglia corsa martedì). Oggi Z2 bici OBBLIGATORIO per preparare l'interval run di venerdì." Non descrizione generica.

### Gap 4 — Drill tecnici specifici Nicolò
- **D-23:** `propose_session.md` include una sezione dedicata "Drill tecnici Nicolò" per disciplina:
  - **Nuoto**: pull drill con pull buoy (shoulder-safe), DPS count, kick lavoro con pinne per shoulder relief, fingertip drag per fase catch
  - **Bici**: big gear intervals (50-55rpm) per muscular endurance, cadenza drill (100rpm+ 3×30sec), climbing position
  - **Corsa**: strides (8×80m) per neuromuscolare e meccanica post-fascite, marcia di attivazione tibiali, cadenza drill
- **D-24:** I drill tecnici sono parte **integrante** della sessione (nel main set o nel warmup), non aggiunta opzionale. Ogni sessione include almeno 1-2 drill rilevanti per la disciplina.

### Gap 5 — Race-pace Lavarone
- **D-25:** Sessioni race-pace bici e corsa calibrate su target Lavarone da `race_prediction` (CTL/FTP/threshold → stima performance su percorso cross) + `get_race_context` (dati specifici Lavarone: distanza, dislivello, tipo fondo).
- **D-26:** I target si aggiornano automaticamente con la fitness corrente — non hardcodati. Il skill legge `race_prediction` output prima di prescrivere race-pace sessions.

### Gap 6 — Progressione multi-sessione
- **D-27:** Progressione qualità tracciata in `mesocycles` table come campo `progression_plan` JSONB: `{"run_threshold": {"week1": "4x6min", "week2": "5x6min", "week3": "6x6min"}, ...}`.
- **D-28:** `get_weekly_context` espone `current_progression_step` per ogni tipo di sessione di qualità. Il skill legge il passo corrente e propone il successivo solo se RPE medio ultime 3 sessioni ≤ 7.5; altrimenti consolida.

### Claude's Discretion
- Struttura interna dei drill per disciplina nel prompt (ordine, volume drill vs. volume principale)
- Threshold esatto di riduzione pace per zona contestualizzata (range "5-8%" o specifico per condizione)
- Schema DB `active_constraints` per campi aggiuntivi (es. `source`, `notes`)
- Formato esatto della sezione "Contesto mesociclo" nel template output
- Numero di strides/drill per sessione in base a durata totale

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Profilo atleta e metodologia
- `CLAUDE.md` §2 (profilo atleta) — CSS/soglia corsa/FTP correnti, vincoli medici attivi (spalla dx, fascite sx), struttura settimanale fissa
- `CLAUDE.md` §3 (metodologia) — block periodization polarizzata 80/20, struttura mesociclo 3+1
- `CLAUDE.md` §5.1-5.3 (regole deterministiche) — soglie HRV, fitness test scheduling ogni 4-6 settimane
- `docs/elite_training_reference.md` — 114 sessioni periodo élite 2021-2022 (target a lungo termine, non punto di partenza)
- `docs/coaching_observations.md` — pattern longitudinali estratti automaticamente

### Requirements e roadmap
- `.planning/REQUIREMENTS.md` §Qualità Prescrizioni Sessioni (WORKOUT-01..05) — acceptance criteria definitivi
- `.planning/ROADMAP.md` §Phase 5 — goal, 5 success criteria, requirements mappati
- `.planning/phases/04-live-behavior-verification/04-CONTEXT.md` — D-02 (confine Phase 4/5), D-12 (FTP scheduling deferito a Phase 5)

### Codice da modificare (skill prompts)
- `skills/propose_session.md` — **LEGGERE PRIMA**: step correnti, template output, zone reference; aggiungere D-02, D-03, D-17-D-24
- `skills/generate_mesocycle.md` — step correnti, citation obbligatoria, output template; aggiungere D-02, D-03, D-27
- `skills/fitness_test.md` — aggiungere D-06 (check FTP age da `get_physiology_zones`)

### Codice da modificare (MCP Worker)
- `workers/mcp-server/src/index.ts` — tool definitions; aggiungere `update_constraint`, estendere `get_physiology_zones` con `valid_from`/`age_days`, estendere `get_weekly_context` con `active_constraints` + `current_progression_step`

### Schema DB e migration
- `sql/schema.sql` — schema `physiology_zones`, `mesocycles`, `planned_sessions.structured`; reference per nuova tabella `active_constraints`
- `migrations/` — pattern migration esistenti per nuova tabella `active_constraints`

### Codice di supporto (lettura, no modifica)
- `coach/planning/briefing.py` `_format_structured()` — renderizza `planned_sessions.structured` già; nessuna modifica necessaria
- `coach/planning/briefing.py` `_format_session_zones()` — già legge `physiology_zones` per discipline; reference per aggiungere `valid_from`
- `coach/coaching/fitness_test_processor.py` — aggiorna `physiology_zones` dopo test; già funzionante da Phase 2
- `coach/utils/llm_client.py` — routing Gemini/Anthropic; `propose_session` e `generate_mesocycle` sono chiamate via Claude.ai (non Python), ma il processor usa questo client

### MCP tools disponibili (da invocare nei skill)
- `get_physiology_zones(discipline)` — da estendere con `valid_from` + `age_days`
- `get_weekly_context` — da estendere con `active_constraints` + `current_progression_step`
- `get_activity_history` — per D-17 (ultime 3 sessioni disciplina)
- `get_session_review_context` — per session_analyses recenti
- `get_race_context` — per D-25 (target Lavarone)
- `commit_plan_change` — write path sessioni con `structured` JSONB
- `commit_mesocycle` — write path mesociclo con `progression_plan`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coach/planning/briefing.py` `_format_structured()` — già renderizza flat steps list `[{name, label, reps, duration_s, zone}]`; nessuna modifica per Phase 5
- `coach/planning/briefing.py` `_fetch_current_zones()` — pattern per leggere physiology_zones da DB; riferimento per estensione MCP tool
- `coach/planning/briefing.py` `_format_session_zones()` — chiama `derive_zones_for_discipline()` per formattare zone; già funzionante per bici/corsa/nuoto
- `coach/coaching/fitness_test_processor.py` `derive_zones_for_discipline()` — calcola Z1-Z5 da FTP/CSS/threshold; usato nella prescrizione numerica
- `scripts/verify_analytics.py`, `scripts/verify_physiology.py` — pattern script read-only con load_dotenv/logging/sections/main() per eventuali script di verifica Phase 5

### Established Patterns
- `planned_sessions.structured` JSONB già accetta qualsiasi formato; `_format_structured()` gestisce dict con chiave `steps`/`intervals`/`workout` e list
- MCP Worker TypeScript: pattern tool definition in `workers/mcp-server/src/index.ts` — aggiunte `update_constraint` e estensioni seguono lo stesso pattern
- Skill prompts in `skills/*.md` sono markdown puri caricati come system prompt — modifica è solo testo
- `get_weekly_context` MCP tool già esiste e restituisce mesocycle_info — estendere non rompere

### Integration Points
- `commit_plan_change` → `planned_sessions.structured`: il Worker MCP scrive JSONB direttamente — nessun cambiamento allo schema, solo enforcement nel prompt
- `get_weekly_context` → `active_constraints`: il Worker legge da nuova tabella `active_constraints` dove `resolved_at IS NULL`
- `get_physiology_zones` → `valid_from` + `age_days`: aggiunta campo calcolato `age_days = NOW() - valid_from` nel response
- `mesocycles` table → `progression_plan`: nuovo campo JSONB da aggiungere con migration

</code_context>

<specifics>
## Specific Ideas

### Formato target zone contestualizzato (D-19/D-20)
Quando ≥2 fattori avversi attivi:
```
⚠️ Condizioni avverse: caldo 28°C + TSB -15
Target: perceived effort Z4 (non pace assoluta)
Riferimento pace: ~4:30-4:35/km (vs 4:23/km standard)
Motivo: in caldo significativo con TSB negativo, mantieni la sensazione di sforzo, non il numero.
```

### Formato sezione contesto mesociclo (D-21/D-22)
```
📊 Contesto mesociclo
Settimana 2/3 del blocco build
TSS accumulato: 280 / ~400 (target settimana)
Sessioni qualità questa settimana: 1 (soglia corsa martedì — ✓)
Ruolo di oggi: Z2 bici lungo — fondamentale per non overcaricare prima dell'interval run di venerdì
```

### Formato drill tecnici nel main set (D-23/D-24)
Esempio sessione nuoto:
```
Warm-up: 400m progressivo Z1→Z2 (no intensità spalla)
Drill block: 4×50m fingertip drag (focus fase catch, riposo 20sec)
Main set: 6×100m @ CSS-5 (pace Z2: <1:35/100m), rec 20sec
Kick set: 3×100m con pinne Z1 (relief spalla, lavoro gambe)
Cool-down: 200m Z1 libero
```

### Formato step JSONB per commit_plan_change
```json
{
  "structured": [
    {"name": "warmup", "duration_s": 900, "zone": "Z1-Z2", "notes": "progressivo, nessuna intensità spalla"},
    {"name": "drill", "reps": 4, "duration_s": 50, "zone": "Z1", "target_value": "fingertip drag", "notes": "focus catch"},
    {"name": "main_set", "reps": 6, "duration_s": 100, "zone": "Z2", "target_value": 95, "notes": "CSS-5: 1:35/100m"},
    {"name": "cooldown", "duration_s": 600, "zone": "Z1", "notes": "libero"}
  ]
}
```

### Check FTP age in fitness_test.md (D-05/D-06)
```
Prima di procedere con la sessione:
1. Chiama get_physiology_zones('bike')
2. Verifica age_days nel response
3. Se age_days > 42 (6 settimane) o FTP null:
   "FTP non aggiornato da X giorni. Propongo un test FTP bici.
   Data ottimale: [calcola: 1-2gg dopo prossima sessione Z2, non in settimana di carico max]
   Struttura test: 20min warmup + 20min maximal effort / ramp 1min"
```

</specifics>

<deferred>
## Deferred Ideas

- **Script auto domenicale piano settimanale** → Phase 7 (AUTO-02): job GitHub Actions che genera sessioni settimanali automaticamente la domenica sera come draft in `plan_modulations`
- **Adattamento fisiologico intelligente** (cedimento muscolare vs cardiovascolare, beliefs integration) → Phase 6
- **Qualità analisi post-sessione** (citation tags, confronto vs piano, pattern adattamento) → Phase 9
- **Qualità brief mattutino** (dati numerici reali, discrepanza readiness, countdown gara) → Phase 8
- **Sessioni proattive da illness/injury flag** (protocollo rientro automatico) → Phase 7
- **Cross-training specifico MTB** (sessioni su mountain bike per simulare Lavarone) — da valutare in Phase 6/7 quando sistema più stabile

</deferred>

---

*Phase: 05-workout-prescription-quality*
*Context gathered: 2026-06-07*
