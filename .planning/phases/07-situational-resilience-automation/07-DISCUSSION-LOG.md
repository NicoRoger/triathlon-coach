# Phase 7: Situational Resilience & Automation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 07-situational-resilience-automation
**Areas discussed:** Missed session detection, Travel/Croazia detection, Weekly plan draft (AUTO-02), Illness re-entry protocol, Other (gaps + LLM routing)

---

## Missed Session Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Ingest-time comparison | Nuovo step in ingest.yml: confronto planned_sessions[ieri] vs activities. Deterministico, zero LLM. | ✓ |
| RPE=0 via Telegram | Nicolò logga esplicitamente RPE=0 per segnalare sessione saltata. | |
| Combination auto + override | Ingest rileva "probabilmente saltata", Telegram permette conferma. | |

**User's choice:** Ingest-time comparison (Recommended)
**Notes:** Approccio deterministico preferito. TSB-gated response esattamente come RESILIENCE-02: TSB > -10 ricalibra, TSB < -20 alleggerisci. Logica in adaptive_planner.py.

---

## Travel / Croazia Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Telegram /travel command | Nicolò manda /travel data → scrive subjective_log. | ✓ |
| GitHub Actions env var TRAVEL_ACTIVE | Aggiorna secret manualmente prima della trasferta. | |
| Notes field in planned_sessions | Rileva "croazia" nelle note delle sessioni. | |

**User's choice:** Telegram /travel command
**Notes:** La trasferta viene pianificata in azienda 1 settimana prima. Il sistema deve tenerne conto durante la programmazione domenicale. In Croazia si può correre → swim sempre sostituita con run (nessun parametro pool). Carico invariato, solo orari/sport adattati.

---

## Weekly Plan Draft (AUTO-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Extend adaptive_planner + Gemini | Legge progression_plan, Gemini genera dettagli sessioni, scrive plan_modulations tipo 'weekly_plan'. | |
| New weekly_planner.py | Modulo dedicato + Gemini. | |
| Rule-based only | Template matching, zero LLM. | |

**User's choice:** Nessuna delle opzioni originali — chiarimento fondamentale durante discussione.
**Notes:** Nicolò apre Claude.ai ogni domenica per il piano → auto-generazione piano è ridondante. AUTO-02 ridefinito come "Telegram nudge se planned_sessions vuota domenica sera". weekly-review.yml già copre il weekly summary — non duplicare. Nudge minimale: "Nessun piano per la settimana, apri Claude.ai".

---

## Illness Re-entry Protocol

| Option | Description | Selected |
|--------|-------------|----------|
| Replace intense sessions + 48h tracking | Proposta sostituzione Z2/riposo + tracking recovery + re-entry graduale. | ✓ |
| Full stop + manual re-entry | Stop tutto, Nicolò manda /ok per rientrare. | |
| Only Telegram alert | Solo avviso, nessuna modifica proposta. | |

**Illness-specific path:** Extend modulation.py (illness già in critical_flags).

**Recovery threshold discussion:** Prima proposta era 2 cicli ingest (6h) — troppo corto vs CLAUDE.md §5.2 "48h+". Deciso: 24h senza illness_flag AND HRV z > -1.0 SD.

**User's choice:** Replace intense sessions + 48h tracking, in modulation.py, con recovery threshold 24h + HRV z > -1.0.

---

## Other — Gaps e LLM Routing

### 5 Gap identificati durante discussione
1. **Missed session detection** (RESILIENCE-02/AUTO-01) — gap principale, nessun check intraday
2. **Illness protocol** (RESILIENCE-04) — illness_flag esiste ma non fa nulla di automatico
3. **Travel command** (RESILIENCE-03) — nessun /travel nel bot
4. **Reschedule rebalancing** (RESILIENCE-01) — commit_plan_change non verifica back-to-back
5. **Empty plan nudge** (AUTO-02 ridefinito) — weekly-review.yml non controlla se piano è vuoto

Tutti e 5 in scope Phase 7, priorità nell'ordine elencato.

### Reschedule

| Option | Description | Selected |
|--------|-------------|----------|
| Solo via Claude.ai MCP | commit_plan_change triggera Python-side rebalancing check. | ✓ |
| Telegram /move | Aggiunge comando bot per spostare sessioni senza Claude.ai. | |
| Entrambi | MCP + Telegram. | |

**User's choice:** Solo via Claude.ai (MCP commit_plan_change).

### LLM Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Gemini-only per tutta Phase 7 | Tutti i purpose resilience_* → Gemini Flash. Cost €0. | |
| Illness su Anthropic | Re-entry plan su Haiku per safety. | |
| Gemini + fallback Haiku se saturo | Gemini primary, Haiku fallback se non disponibile. | ✓ |

**User's choice:** Gemini Flash primary, Anthropic Haiku fallback se Gemini non disponibile (pattern già in HybridClient).

---

## Claude's Discretion

- Testo esatto delle Telegram notification per ogni scenario
- Gestione TSB tra -10 e -20 per missed session (soft note o silenzio)
- Soglia "ricalibrazione materiale" (es. se manca 1 solo giorno a domenica, saltare la proposta)
- Formato proposta rebalancing settimana (lista sessioni vs summary)

## Deferred Ideas

- Weekly summary domenicale pre-pianificazione (numeri chiave prima di aprire Claude.ai) → Phase 8/weekly-review estensione
- Telegram `/move` command — Nicolò preferisce MCP, deferred indefinitamente
- Auto-generazione piano settimanale con Gemini (AUTO-02 originale) — Nicolò apre sempre Claude.ai domenica, non necessario
