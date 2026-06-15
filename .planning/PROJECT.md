# Triathlon AI Coach — Integrità di Sistema & Qualità Elite

## What This Is

Sistema di coaching AI personale per Nicolò Ruggero, atleta in ritorno al triathlon élite (obiettivo: Lavarone Cross Sprint, settembre 2026). Il sistema ingesta dati Garmin ogni 3 ore, calcola metriche di carico (CTL/ATL/TSB, HRV, readiness), genera brief mattutini via Telegram, propone modulazioni del piano con conferma dell'atleta, ed espone tool MCP a Claude.ai per il coaching interattivo.

Il progetto copre due obiettivi paralleli: (1) verificare e consolidare tutti i fix dell'audit di resilienza 2026-06-01 — non dare per scontato che funzionino — e (2) elevare la qualità del coaching a livello élite: analisi profonde, prescrizioni basate su fisiologia misurata, output LLM paragonabili a un servizio di coaching professionale.

## Core Value

Ogni mattina Nicolò riceve dati corretti, analisi attendibili e prescrizioni allineate all'allenamento élite — e può fidarsi ciecamente del sistema per prepararsi alla gara.

## Requirements

### Validated

- ✓ Ingest Garmin → Supabase ogni 3h (idempotente, upsert) — esistente
- ✓ Brief mattutino via Telegram con sessione del giorno dettagliata — esistente + feat
- ✓ Analisi post-sessione LLM (Gemini) salvata in `session_analyses` — fix BUG-001
- ✓ Modulazioni mid-week con confirm via Telegram inline buttons — fix BUG-002 + K1
- ✓ CTL/ATL/TSB via EWMA (PMC) — fix B1/B2/B3
- ✓ HRV z-score e flag fatigue/critical con soglie §5.1 — fix B1/B2
- ✓ Readiness composite score — fix B11
- ✓ Budget hard-cap €5/mese con auto-degradazione Sonnet→Haiku — fix I1/I2/I9
- ✓ DR snapshot/restore con guard tabelle vuote — fix L3
- ✓ Watchdog che rileva componenti assenti — fix L4
- ✓ Belief engine Bayesiano + Decision priority engine — Cognitive MVP Phase 4
- ✓ Proactive questions + reminders (3x/settimana) — fix F1/F2
- ✓ Dashboard React/Vite con GoalBoard, AnnualView, ReadinessCard — fix N1/N2/N3
- ✓ MCP server con tool get_weekly_context, commit_plan_change, ecc. — fix BUG-003/BUG-005

### Active

- [ ] **VERIFY-001** — Verificare che ogni fix dell'audit sia effettivamente live (code + deploy + migration + comportamento reale), non solo committato
- [ ] **VERIFY-002** — Verificare che i valori physiology_zones (FTP, CSS, soglia corsa) siano nel DB dopo i test fitness già eseguiti da Nicolò
- [ ] **DEPLOY-001** — Eseguire le migrazioni pending in Supabase SQL editor (lista in `OPEN_ISSUES.md`), verificarne l'esito
- [ ] **DEPLOY-002** — Deploy Telegram bot (`wrangler deploy`) con fix K2/K3/K4/K5 e validare end-to-end
- [ ] **DEPLOY-003** — Verificare che `apply_accepted_modulations` sia wired in `ingest.yml` e funzioni su modulazione reale
- [ ] **QUALITY-001** — Elevare qualità brief mattutino: precisione dati atleta, congruenza con metodologia élite (Seiler/Laursen block periodization)
- [ ] **QUALITY-002** — Elevare qualità analisi post-sessione: profondità pari a coach professionista, citation tags, relazione con obiettivi stagionali
- [ ] **QUALITY-003** — Elevare qualità prescrizioni sessioni: zone precise su fisiologia misurata (FTP/CSS/soglia), struttura sessione dettagliata, progressione coerente con mesociclo
- [ ] **QUALITY-004** — Weekly review e pattern extraction: output strutturato con insight azionabili, beliefs aggiornate, decision provenance
- [ ] **INTEGRITY-001** — Test suite verde su tutti i fix: verificare `pytest` passa localmente e che i test coprono i bug critici risolti
- [ ] **INTEGRITY-002** — MCP auth hardening (J1 + J2-J6): eseguire il piano in `docs/mcp_auth_hardening_plan.md`
- [ ] **INTEGRITY-003** — Verificare correttezza logica `fitness_test_processor.py` sui test già eseguiti (FTP bici, soglia corsa, CSS nuoto)

### Out of Scope

- Google Calendar integration reale — OAuth complexity, rinviato post-Lavarone; `calendar_event_id` resta colonna placeholder
- Multi-athlete support — sistema pensato per un solo atleta, aggiungere user_id richiederebbe rewrite schema
- App mobile nativa — Telegram bot è sufficiente come interfaccia mobile
- Consigli nutrizionali specifici — fuori dalla competenza del sistema (reindirizza a dietista sportivo)
- Strava sync attiva — disabilitata in `ingest.yml`, Garmin = single source of truth
- Phase 5 Cognitive expansion (coaching philosophy layer, multi-memory) — oltre l'orizzonte attuale

## Context

**Stato audit precedente (non assumere che funzioni):**
L'audit di resilienza 2026-06-01 ha identificato ~45 bug su 15 aree e committato i fix sul branch `audit-resilience-2026-06-01`, poi mergiato in main via PR #1. Tuttavia:
- Le migrazioni DB sono pending (elencate in `OPEN_ISSUES.md` e `docs/audit_resilience_2026-06-01.md §Da fare manualmente`)
- Il Telegram bot non è stato ridistribuito con i fix K2/K3/K4/K5
- Il comportamento live potrebbe divergere dal codice committato
- Nicolò ha eseguito i test fitness (FTP, CSS, soglia corsa) ma non sappiamo se `fitness_test_processor.py` li ha rilevati e processati correttamente
- Il bug E1 (FTP fallback su averageSpeed) e E2 (threshold fallback su averagePace) erano critici per la correttezza delle zone — verificare che i valori in DB siano plausibili

**Architettura esistente:**
- Python backend: analytics deterministico (`coach/analytics/`), coaching LLM (`coach/coaching/`), ingest Garmin (`coach/ingest/`)
- Cloudflare Workers: MCP server (`workers/mcp-server/`) + Telegram bot (`workers/telegram-bot/`)
- Supabase PostgreSQL: single source of truth
- GitHub Actions: scheduling (ingest 3h, brief 06:20 UTC, weekly review, ecc.)
- LLM routing: Gemini 2.5 Flash (free, high-volume) + Anthropic claude-sonnet-4-6/haiku (paid, critical decisions)

**Obiettivo gara**: Lavarone Cross Sprint, 2026-09-06, target top 15-20.

**Fitness tests eseguiti (giugno 2026)**: FTP bici, soglia corsa, CSS nuoto — dati su Garmin, processamento da verificare.

## Constraints

- **Budget**: €5/mese hard cap su Anthropic API — ogni fix LLM deve rispettare routing Gemini-first
- **Conferma prima di scrivere**: `planned_sessions` non si tocca senza conferma atleta — regola inviolabile (CLAUDE.md §5.4)
- **No server Python persistente**: tutta la logica Python gira come job GitHub Actions — nessun processo always-on
- **Single athlete**: nessun `user_id` nello schema — non aggiungere multi-tenancy
- **Deploy Workers richiede wrangler**: modifiche ai Workers devono essere rilasciate con `wrangler deploy` — il codice committato non è live finché non viene deployato
- **Zona vulnerabile spalla destra**: zero sessioni nuoto Z4+ — constraint medico hardcoded nelle prescrizioni

## Key Decisions

| Decisione | Razionale | Esito |
|-----------|-----------|-------|
| Trust but verify su tutti i fix precedenti | Il codice committato non garantisce comportamento live; migrazioni e deploy sono passi separati | — Pending |
| Verificare physiology_zones prima di usarle per prescrizioni | Bug E1/E2 potevano corrompere zone; dati invalidi in DB sono peggio di nessun dato | — Pending |
| MCP auth hardening bundlato in fase dedicata | Cambiare auth MCP rischia di rompere il connettore Claude.ai — richiede sessione dedicata con Nicolò al PC | — Pending |
| Qualità coaching = standard coach professionista | Non "chatbot che risponde" ma "coach che conosce l'atleta e usa i dati per decisioni precise" | — Pending |
| Gemini Flash per analisi ad alto volume, Anthropic per decisioni critiche | Riduce costo da €1.50/mese a €0.30/mese mantenendo qualità sulle decisioni che contano | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-05 after initialization*
