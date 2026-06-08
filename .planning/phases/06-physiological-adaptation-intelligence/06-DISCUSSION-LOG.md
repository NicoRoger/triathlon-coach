# Phase 6: Physiological Adaptation Intelligence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 06-physiological-adaptation-intelligence
**Areas discussed:** Classificazione cedimento, Seeding belief endurance, Pipeline belief → prescrizione, Trigger aggiornamento beliefs, Storage classificazione fatica

---

## Meta: Le logiche attuali servono?

User raised: le infrastrutture esistono (belief_engine, pattern_extraction, post_session_analysis) ma sono probabilmente sottoutilizzate. Conclusione: l'architettura è corretta, mancano (1) il classification step esplicito e (2) una belief seedata con dati reali. Nessuna rearchitettura necessaria.

---

## Classificazione cedimento

| Option | Description | Selected |
|--------|-------------|----------|
| Python analytics deterministico | Nuova funzione in analytics, soglie hard-coded, testabile, zero LLM | ✓ |
| LLM nel skill prompt (Gemini) | Gemini inferisce il tipo, flessibile ma non testabile | |
| Ibrido: Python classifica, LLM arricchisce | Python flag + Gemini linguaggio naturale | |

**User's choice:** Python analytics deterministico

**Secondo step (come influenza la sessione successiva):**

| Option | Description | Selected |
|--------|-------------|----------|
| Via get_weekly_context | Campo last_fatigue_by_sport nel tool MCP | ✓ |
| Via flag in planned_sessions | briefing.py legge fatigue_type dalla sessione | |
| Solo in session_analyses | Lettura via get_activity_history + join | |

**Terzo step (soglie):**

| Option | Description | Selected |
|--------|-------------|----------|
| Soglie conservative CLAUDE.md-aware | HR drift + RPE + pace/power drop, fallback RPE-only | ✓ |
| Solo HR drift e decoupling | Più semplice, meno accurato | |
| Lascia decidere Claude | Soglie come implementation detail | |

---

## Seeding belief endurance

| Option | Description | Selected |
|--------|-------------|----------|
| Migration diretta come validated_belief | n=8, conf=0.75, fatto noto da CLAUDE.md | ✓ |
| Bootstrap da session_analyses | Retroattivo sulle analisi esistenti | |
| Seed come hypothesis | n=2, conf=0.60, cresce nel tempo | |

**User's choice:** Migration diretta (è un fatto noto, non un'ipotesi)

**Quali altri beliefs seedare:**

| Option | Description | Selected |
|--------|-------------|----------|
| Solo ADAPT-02 | Gli altri emergono dall'evidenza | ✓ |
| + Profilo fisiologico endurance puro | Da CLAUDE.md §2 | |
| + Vincolo spalla nuoto max Z1-Z2 | Già in active_constraints | |

**User's choice:** Solo ADAPT-02. Chiarimento richiesto su "seedati" → "inserire dati iniziali nel DB invece di aspettare che il sistema li crei dall'uso normale."

---

## Pipeline belief → prescrizione

| Option | Description | Selected |
|--------|-------------|----------|
| Estendi get_weekly_context | active_beliefs + last_fatigue_by_sport nel tool esistente | ✓ |
| Nuovo tool get_adaptation_context | Tool dedicato, un call aggiuntivo per prescrizione | |
| Il skill legge list_beliefs() direttamente | Nuovo tool nel Worker MCP | |

**User's choice:** Estendi get_weekly_context (coerente con pattern Phase 5 D-15)

**Come appare il tag belief:**

| Option | Description | Selected |
|--------|-------------|----------|
| Tag inline nella sessione | Inline nel main set o nel razionale, con motivazione specifica | ✓ |
| Sezione dedicata in fondo | Lista audit trail separata dalla prescrizione | |
| Solo se il belief influenza la scelta | Tag condizionale, riduce rumore | |

---

## Trigger aggiornamento beliefs

| Option | Description | Selected |
|--------|-------------|----------|
| Python job settimanale auto | Estensione pattern_extraction.py, deterministico | ✓ |
| Claude.ai interattivo via MCP | Manual trigger durante weekly review | |
| Trigger immediato post-sessione | post_session_analysis.py verifica n≥3 e aggiorna | |

**User's choice:** Python job settimanale (stesso pattern di pattern_extraction già in produzione)

**Come aggiusta la progressione:**

| Option | Description | Selected |
|--------|-------------|----------|
| Il belief aggiorna progression_plan in mesocycles | reinforce → incrementa step (D-27/D-28 Phase 5) | ✓ |
| Il belief è solo informativo | Progressione manuale | |
| Il belief sblocca sessioni avanzate pre-configurate | next_session_template per belief | |

---

## Storage classificazione fatica

| Option | Description | Selected |
|--------|-------------|----------|
| Nuova colonna in session_analyses | ALTER TABLE: fatigue_type + fatigue_confidence | ✓ |
| Campo nel JSONB analysis_data | No migration, non SQL-queryable facilmente | |
| Tabella dedicata fatigue_classifications | Over-engineering per questo use case | |

**User's choice:** Nuova colonna (SQL-queryable, migration coerente con pattern Phase 3)

---

## Claude's Discretion

- Soglia esatta per power drop su bici (5% vs 8%)
- Numero settimane storico nel job beliefs (default 14gg)
- Formato `evidence_note` per beliefs generati dal job
- Naming convention esatta per beliefs di risposta (`responds_well_` vs `adapts_to_`)

## Deferred Ideas

- Qualità LLM analisi post-sessione (profondità, citation tags strutturate) → Phase 9
- Brief mattutino con beliefs attivi → Phase 8
- Weekly review narrativa con beliefs → Phase 10
- Belief decay automatico su infortuni → Phase 7 o Phase 10
