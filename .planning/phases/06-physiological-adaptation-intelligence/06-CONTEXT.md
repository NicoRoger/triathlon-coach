# Phase 6: Physiological Adaptation Intelligence - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Il sistema capisce come il corpo di Nicolò risponde agli stimoli allenanti — distingue cedimento muscolare da cardiovascolare, inserisce nel DB i beliefs fisiologici di Nicolò (a partire da quello noto: endurance puro, cedimento muscolare prima), e usa questi beliefs nelle prescrizioni di allenamento e nell'aggiustamento automatico della progressione.

**In scope:**
- Classificazione determinististica muscolare vs cardiovascolare in Python analytics (`coach/analytics/`)
- Storage classificazione in `session_analyses` (nuove colonne `fatigue_type`, `fatigue_confidence`)
- Seeding del belief "endurance_failure_type: muscolar-first" via migration/script (n=8, conf=0.75, validated_belief)
- Esposizione beliefs e fatigue_by_sport in `get_weekly_context` MCP tool
- Tag `[athlete-belief: ...]` inline nelle prescrizioni skill (`propose_session.md`)
- Job settimanale deterministico per aggiornamento beliefs (estensione di `pattern_extraction.py`)
- Aggiornamento `mesocycles.progression_plan` triggerato dai beliefs (reinforce → incrementa step)

**Out of scope:**
- Seeding di beliefs diversi da quello ADAPT-02 — gli altri emergono dall'evidenza reale
- Qualità analisi post-sessione (linguaggio, profondità) → Phase 9
- Brief mattutino → Phase 8
- Weekly review → Phase 10
- Predizione race performance → esistente in `coach/coaching/test_prediction.py`

</domain>

<decisions>
## Implementation Decisions

### Classificazione cedimento (ADAPT-01)

- **D-01:** La logica di classificazione muscolare vs cardiovascolare vive in **Python analytics deterministico** (`coach/analytics/` — nuovo modulo o estensione di `readiness.py`). Zero LLM, testabile in pytest, richiamata da `post_session_analysis.py` prima del call Gemini.
- **D-02:** Output della funzione: `{'failure_type': 'muscular'|'cardiovascular'|'mixed'|None, 'confidence': float}`. `None` quando dati insufficienti (es. splits mancanti, sessione < 30min).
- **D-03:** Soglie CLAUDE.md-aware:
  - **Cardiovascular signal**: HR drift >10bpm nel secondo 50% della sessione (confronto HR_avg primo 50% vs secondo 50%)
  - **Muscular signal**: HR stabile + RPE ≥8 + pace/power drop > 5% (decoupling inverso: corpo non risponde all'intensità richiesta ma il cuore tiene)
  - **Disciplina-specifica**: corsa usa pace degradation per km (da `splits`); bici usa power vs HR curve; nuoto usa pace vs HR negli ultimi 2 × 100m
  - **Fallback**: se `splits` mancanti → usa solo RPE con `confidence = 0.4` (flag: "dati insufficienti")
  - **Context**: Nicolò è endurance puro — il cedimento muscolare è il pattern atteso, non l'eccezione
- **D-04:** La classificazione viene salvata in `session_analyses` con due nuove colonne: `fatigue_type TEXT CHECK (IN ('muscular', 'cardiovascular', 'mixed', 'insufficient_data'))` e `fatigue_confidence FLOAT`. Migration necessaria.
- **D-05:** `get_weekly_context` MCP tool espone `last_fatigue_by_sport`: `{"run": {"type": "muscular", "confidence": 0.8, "date": "2026-06-07"}, "swim": null, "bike": null}`. Legge la riga più recente per disciplina in `session_analyses` con `fatigue_type IS NOT NULL`.

### Seeding belief "endurance puro" (ADAPT-02)

- **D-06:** Il belief principale viene inserito via **migration o script** direttamente in `beliefs` table con: `key='endurance_failure_type'`, `value='muscular-first'`, `n=8`, `confidence=0.75`, `status='validated_belief'`, `evidence_note='Basato su CLAUDE.md §2: profilo atleta, confermato da anni di dati pre-pausa élite 2021-2022'`.
- **D-07:** Solo questo belief viene seedato. Gli altri (risposta a interval run, soglia muscolare specifica per sessione, ecc.) emergono dall'evidenza reale accumulata nel tempo.
- **D-08:** Il motore belief (`belief_engine.py`) continua ad aggiornare il belief seedato con `reinforce_belief` / `contradict_belief` come ogni altro belief — non è immutabile.

### Pipeline belief → prescrizione (ADAPT-01 + ADAPT-02)

- **D-09:** `get_weekly_context` viene esteso con due nuovi campi:
  1. `active_beliefs`: lista di beliefs con `confidence >= 0.55` (weak_belief o superiore), formato `[{"key": "...", "value": "...", "status": "...", "confidence": 0.75}]`
  2. `last_fatigue_by_sport`: vedi D-05
- **D-10:** Il skill `propose_session.md` legge `get_weekly_context.active_beliefs` come step di lettura obbligatorio (come legge già `active_constraints`). Applica i beliefs pertinenti alla disciplina e cita con tag `[athlete-belief: key]` inline nel main set o nel razionale.
- **D-11:** Tag format: `[athlete-belief: endurance-puro, cedimento-muscolare-first] — [motivazione specifica applicata alla sessione]`. Il tag appare **inline** nel testo della prescrizione, nella sezione dove il belief ha influenzato la scelta (non in una sezione separata).

### Job aggiornamento beliefs (ADAPT-03)

- **D-12:** Estensione di `pattern_extraction.py` (già in produzione, gira settimanalmente): legge `session_analyses` ultimi 14gg, raggruppa per `session_type` (da `planned_sessions.session_type` via JOIN), se n≥3 sessioni stessa tipologia calcola pattern di risposta.
- **D-13:** Il job è **deterministico** (zero LLM): `avg_rpe`, `avg_hr_drift`, tendenza `fatigue_type` → chiama `reinforce_belief()` se pattern positivo (RPE ≤ 7.5, no degradazione) o `contradict_belief()` se negativo.
- **D-14:** I nuovi beliefs creati dal job seguono la naming convention `responds_well_{session_type}` o `struggles_with_{session_type}` (es. `responds_well_interval_run_4min`). Key format: `snake_case_with_session_type`.
- **D-15:** Quando un belief `responds_well_*` raggiunge `validated_belief` (n≥8, conf>0.7), il job aggiorna `mesocycles.progression_plan` incrementando il passo per quella tipologia: es. `{"run_threshold": {"week1": "4x6min", "week2": "5x6min"}}` → step avanza. Coerente con D-27/D-28 di Phase 5.

### Claude's Discretion

- Soglia esatta per "pace degradation" su bici (5% o 8% power drop)
- Quante settimane di storico usare nel job beliefs (14gg è il default — può scendere a 10 se pochi dati)
- Formato esatto `evidence_note` per beliefs generati dal job (breve vs verboso)
- Naming convention esatta per beliefs di risposta (prefisso `responds_well_` vs `adapts_to_`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Profilo atleta e metodologia
- `CLAUDE.md` §2 (profilo atleta) — tipo atleta "endurance puro, primo cedimento muscolare"; CSS/soglia corsa/FTP correnti; vincoli medici attivi; struttura settimanale fissa
- `CLAUDE.md` §3 (metodologia) — block periodization polarizzata 80/20; struttura mesociclo 3+1; Z3 minimizzato
- `CLAUDE.md` §5.1-5.3 (regole deterministiche) — soglie HRV, flag fatigue_warning/critical; fitness test scheduling

### Requirements Phase 6
- `.planning/ROADMAP.md` §Phase 6 — goal, 3 success criteria, requirements ADAPT-01/02/03
- `.planning/REQUIREMENTS.md` §ADAPT-01, ADAPT-02, ADAPT-03 — acceptance criteria definitivi

### Codice da modificare
- `coach/analytics/readiness.py` — aggiungere funzione `classify_fatigue_type(activity, splits, debrief)` → dict con failure_type + confidence (D-01/D-02/D-03)
- `coach/coaching/post_session_analysis.py` — chiamare `classify_fatigue_type()` prima del call Gemini, scrivere risultato in `session_analyses` (D-04)
- `coach/coaching/pattern_extraction.py` — estendere con belief update job (D-12/D-13/D-14/D-15)
- `workers/mcp-server/src/index.ts` — estendere `get_weekly_context` con `active_beliefs` + `last_fatigue_by_sport` (D-09)
- `skills/propose_session.md` — aggiungere step lettura `active_beliefs` da `get_weekly_context` e citation tag inline (D-10/D-11)

### Schema DB e migration
- `sql/schema.sql` — `session_analyses` schema corrente (reference per ALTER TABLE), `beliefs` schema (reference per seed), `mesocycles` + `progression_plan` (reference per update)
- `migrations/` — pattern migration esistenti per ALTER TABLE e INSERT seed

### Codice di supporto (lettura, no modifica)
- `coach/analytics/belief_engine.py` — API: `create_belief`, `reinforce_belief`, `contradict_belief`, `list_beliefs`. Lifecycle thresholds: `VALIDATED_MIN_N=8`, `VALIDATED_MIN_CONFIDENCE=0.7`. **Leggere prima di implementare il job belief update.**
- `coach/analytics/belief_guardrails.py` — guardrail su contraddizioni forti; verificare compatibilità con il nuovo job
- `coach/coaching/post_session_analysis.py` — flusso esistente: `_get_planned_session`, `_get_historical`, analisi Gemini; aggiungere classificazione prima del call LLM
- `coach/analytics/pmc.py` — calcolo TSS/CTL/ATL; reference per accesso dati `activities`
- `.planning/phases/05-workout-prescription-quality/05-CONTEXT.md` — D-15 (active_constraints via get_weekly_context), D-17/D-18 (sessioni recenti disciplina), D-27/D-28 (progression_plan in mesocycles). **Non duplicare — estendere.**

### MCP tools (da estendere)
- `get_weekly_context` — da estendere con `active_beliefs` + `last_fatigue_by_sport` (D-09); NON modificare campi esistenti
- `get_activity_history` — per lettura storico sessioni nel job belief update

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coach/analytics/belief_engine.py` `reinforce_belief(key, outcome_id)` / `contradict_belief(key, outcome_id, reason)` — API già pronta per il job settimanale (D-13)
- `coach/analytics/belief_engine.py` `list_beliefs(min_status='weak_belief')` — per popolare `active_beliefs` in `get_weekly_context`
- `coach/analytics/readiness.py` — pattern per funzioni analytics deterministiche con dataclass output; reference per `classify_fatigue_type()`
- `coach/planning/briefing.py` `_format_session_zones()` — già legge `physiology_zones` per disciplina; reference per accesso splits
- `coach/coaching/pattern_extraction.py` — già gira settimanalmente, legge `session_analyses`, usa Gemini; la parte deterministica (grouping, averaging) va separata dal call LLM
- `coach/coaching/post_session_analysis.py` `_get_historical()` — già legge `splits` da activities; il campo è disponibile per la classificazione fatica

### Established Patterns
- Analytics deterministico in `coach/analytics/` → zero LLM, output dataclass o dict tipizzato, testabile in pytest
- MCP Worker TypeScript: estensioni `get_weekly_context` seguono il pattern esistente — aggiungere campi al JSON response, non nuovi tool calls
- Belief lifecycle in `belief_engine.py`: non cancellare mai, solo contradict + decay; la confidence scende ma il belief resta

### Integration Points
- `post_session_analysis.py` → `classify_fatigue_type()` → scrive `session_analyses.fatigue_type` + `fatigue_confidence`
- `pattern_extraction.py` (job settimanale) → `reinforce_belief` / `contradict_belief` → `mesocycles.progression_plan`
- `get_weekly_context` Worker → `beliefs` table + `session_analyses.fatigue_type` → `propose_session.md` skill

</code_context>

<specifics>
## Specific Ideas

### Formato tag belief nelle prescrizioni (D-11)
Esempio inline nel main set:
```
Main set: 5×6min @ 105% FTP (Z4), rec 2min attivo Z1
[athlete-belief: endurance-failure-muscular-first] — capped a 5 reps (soglia muscolare Nicolò su interval run 6min: n>5 → degradazione qualità >60% sessioni)
```

### Formato `last_fatigue_by_sport` in get_weekly_context (D-05/D-09)
```json
{
  "last_fatigue_by_sport": {
    "run": {"type": "muscular", "confidence": 0.82, "date": "2026-06-06"},
    "swim": null,
    "bike": {"type": "mixed", "confidence": 0.55, "date": "2026-06-04"}
  }
}
```

### Seed SQL per belief ADAPT-02 (D-06)
```sql
INSERT INTO beliefs (key, value, confidence, n, status, evidence_note, created_at, updated_at)
VALUES (
  'endurance_failure_type',
  'muscular-first',
  0.75,
  8,
  'validated_belief',
  'Basato su CLAUDE.md §2: profilo atleta, confermato da storico élite 2021-2022 (114 sessioni)',
  NOW(),
  NOW()
) ON CONFLICT (key) DO NOTHING;
```

### Esempio naming belief generato dal job (D-14)
- `responds_well_interval_run_4min` — risponde bene agli interval run da 4min (RPE medio 6.8, no degradazione su 4 sessioni)
- `struggles_with_long_z2_bike` — bici Z2 lungo >2h porta affaticamento muscolare gambe (RPE medio 8.1 sulla seconda ora)

</specifics>

<deferred>
## Deferred Ideas

- **Qualità LLM analisi post-sessione** (profondità, confronto vs piano, citation tags strutturate) → Phase 9 come da roadmap
- **Brief mattutino con beliefs** (mostrare beliefs attivi nel brief) → Phase 8
- **Weekly review narrativa con beliefs** → Phase 10
- **Belief decay automatico su infortuni** (es. belief invalidato se fascite peggiora) → Phase 7 o Phase 10

</deferred>

---

*Phase: 06-physiological-adaptation-intelligence*
*Context gathered: 2026-06-08*
