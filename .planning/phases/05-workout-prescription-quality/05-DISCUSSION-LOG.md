# Phase 5: Workout Prescription Quality - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 05-workout-prescription-quality
**Areas discussed:** Percorso prescrizioni, FTP bici test, Struttura JSONB vs prose, Guardrail vincoli medici, Gap qualità élite

---

## Percorso prescrizioni

| Option | Description | Selected |
|--------|-------------|----------|
| Solo skill prompt upgrade | Migliora propose_session.md + generate_mesocycle.md — nessun nuovo codice Python | |
| Script Python auto-generator | Job domenicale che genera sessioni strutturate automaticamente | |
| Entrambi | Skill prompt + script auto | ✓ (poi rivisto) |

**User's choice:** Inizialmente "Entrambi", poi chiarito che il piano viene generato via Claude Opus dall'app Claude.ai — fase rivista a "Solo qualità MCP/skill"

**Notes:** "Di solito il piano lo genera Claude Opus via app, ho bisogno della qualità massima per il training." Script auto domenicale → Phase 7 (AUTO-02).

---

## FTP bici test

| Option | Description | Selected |
|--------|-------------|----------|
| Script Python auto-trigger | Ingest/job controlla FTP age, inserisce plan_modulations | |
| Solo via Claude.ai interattivo | Nessun auto-trigger, coach propone con fitness_test.md | |
| Out of scope per Phase 5 | Solo qualità sessioni esistenti | |

**User's choice:** "Mi piace un intreccio dell'1 e 2, ovviamente se i valori cambiano deve aggiornarsi il sistema"

**Follow-up:** "è il coach che deve essere in grado di decidere quando è necessario farlo" → decisione finale: skill + MCP tool con `valid_from`/`age_days`, nessun auto-trigger Python.

**Notes:** Il coach (Claude.ai Opus) decide il timing in base a TSB/CTL. `fitness_test_processor.py` già aggiorna zones automaticamente dopo il test Garmin (Phase 2).

---

## Struttura JSONB vs prose

| Option | Description | Selected |
|--------|-------------|----------|
| JSONB obbligatorio | Ogni commit_plan_change DEVE avere structured JSONB | ✓ |
| JSONB opzionale | Se Claude genera struttura — bene; se no, description basta | |
| JSONB + schema validation nel Worker | TypeScript valida warmup/main/cooldown prima di scrivere | |

**User's choice:** "JSONB obbligatorio per ogni sessione"

**Follow-up schema:** Steps flat list `[{name, duration_s, zone, target_value, reps?, notes?}]` — già compatibile con `_format_structured()` in briefing.py.

---

## Guardrail vincoli medici

| Option | Description | Selected |
|--------|-------------|----------|
| Skill prompt esplicito + summary nel MCP context | Vincoli in skill + get_weekly_context.active_constraints | |
| Solo nei skill prompt (già in CLAUDE.md) | Nessuna modifica | |
| Python validator pre-commit | Validator TypeScript nel Worker prima della scrittura su DB | |

**User's choice:** "Io li rispetto, ma bisogna anche inserire un modo per togliere l'alert quando non più necessario"

**Notes:** Scelta finale: nuova tabella `active_constraints` in DB + MCP tool `update_constraint(id, resolved_at)` via Claude.ai. `get_weekly_context` include `active_constraints`. Vincoli letti da DB (dinamici), non da CLAUDE.md (statico).

---

## Gap qualità élite

### Identificazione gap

Il coach AI ha identificato 3 gap vs. best practices coaching élite non coperti dalle aree precedenti:

1. **Gap 1**: `propose_session` non legge sessioni recenti simili — prescrive senza guardare come sono andate le ultime sessioni della stessa disciplina
2. **Gap 2**: Zone statiche senza aggiustamento contestuale (caldo, TSB, sonno)
3. **Gap 3**: Sessioni decontestualizzate dal mesociclo — nessun razionale che le collega al blocco corrente

**User's choice:** "Tutto, ovviamente si deve integrare con l'intero sistema"

### Dettagli Gap 1

| Option | Description | Selected |
|--------|-------------|----------|
| Ultime 3 sessioni stessa disciplina (14gg) | Finestra 14gg, limit 3 | ✓ |
| Ultime 5 sessioni stessa disciplina | Più contesto, più rumore | |
| Ultima settimana tutte discipline | Carico complessivo 7gg | |

### Dettagli Gap 2

| Option | Description | Selected |
|--------|-------------|----------|
| Caldo >25°C + TSB <-10 + sonno <65 (≥2) | Threshold chiari | ✓ |
| Qualsiasi combinazione avversa | Valutazione libera del coach AI | |
| Solo se HRV z < -1.0 | Solo segnale HRV | |

### Dettagli Gap 3

| Option | Description | Selected |
|--------|-------------|----------|
| Da DB via MCP get_weekly_context | Dinamico, sempre aggiornato | ✓ |
| Da CLAUDE.md §4 (Stato corrente) | Statico | |
| Entrambi | DB per numeri, CLAUDE.md per contesto stagionale | |

### Gap aggiuntivi (proposti dal coach AI, tutti accettati)

**Gap 4 — Drill tecnici specifici Nicolò**
- User: "Tutti" (accettato)
- Drill library in `propose_session.md` — nel prompt, non file separato

**Gap 5 — Race-pace back-calculation Lavarone**
- User: "Tutti" (accettato)
- Target via `race_prediction` + `get_race_context` — aggiornamento automatico con fitness

**Gap 6 — Progressione multi-sessione documentata**
- User: "Tutti" (accettato)
- Progressione in `mesocycles.progression_plan` JSONB; `get_weekly_context` espone `current_progression_step`

**User note:** "Tutti i sistemi ovviamente si devono mantenere aggiornati nel tempo, come tutti gli altri d'altronde" — principio trasversale che guida tutte le decisioni: dati sempre da DB via MCP, non hard-coded.

---

## Claude's Discretion

- Struttura interna dei drill per disciplina (ordine, volume drill vs. volume principale)
- Threshold esatto di riduzione pace per zona contestualizzata (range "5-8%" vs specifico per condizione)
- Schema DB `active_constraints` per campi aggiuntivi (es. `source`, `notes`)
- Formato esatto della sezione "Contesto mesociclo" nel template output
- Numero di strides/drill per sessione in base a durata totale

## Deferred Ideas

- Script auto domenicale piano settimanale → Phase 7 (AUTO-02)
- Adattamento fisiologico intelligente (cedimento muscolare vs cardiovascolare) → Phase 6
- Qualità analisi post-sessione → Phase 9
- Qualità brief mattutino → Phase 8
- Cross-training specifico MTB per Lavarone → valutare Phase 6/7
