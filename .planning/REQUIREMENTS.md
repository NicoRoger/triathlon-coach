# Requirements: Triathlon AI Coach — Integrità & Qualità Elite

**Defined:** 2026-06-05
**Core Value:** Ogni mattina Nicolò riceve dati corretti, analisi attendibili e prescrizioni allineate all'allenamento élite — e può fidarsi ciecamente del sistema per prepararsi alla gara.

> **Principio trasversale**: non dare per scontato che i fix committati funzionino.
> Ogni requisito di verifica implica osservare il comportamento reale, non solo leggere il codice.

---

## v1 Requirements

### Verifica Fix Precedenti (VERIFY)

- [ ] **VERIFY-01**: L'intera test suite pytest passa verde localmente senza failures su logiche critiche (HRV, PMC, readiness, fitness test, modulation, budget, DR, watchdog)
- [x] **VERIFY-02**: I valori di `physiology_zones` nel DB per FTP, CSS e soglia corsa corrispondono ai test fitness eseguiti da Nicolò a giugno 2026 — valori plausibili e non corrotti da bug E1/E2
- [x] **VERIFY-03**: Il brief mattutino inviato via Telegram mostra la sessione del giorno con zone corrette basate su physiology_zones misurate (non stime)
- [x] **VERIFY-04**: Le analisi post-sessione in `session_analyses` vengono generate dopo ogni sync Garmin e contengono testo non vuoto e `model_used = gemini-2.5-flash`
- [x] **VERIFY-05**: Le modulazioni proposte via Telegram compaiono con inline buttons ✅/❌, e quelle accettate vengono applicate a `planned_sessions` nel ciclo ingest successivo
- [x] **VERIFY-06**: Il budget tracker riflette la spesa reale Anthropic — non si supera €5/mese e il degrado Sonnet→Haiku scatta a €4.00 correttamente

### Deploy & Migrazioni (DEPLOY)

- [x] **DEPLOY-01**: Tutte le migrazioni pending in `OPEN_ISSUES.md` sono state eseguite in Supabase e verificate (CHECK constraint, UNIQUE, FK ON DELETE, expires_at, kind values)
- [x] **DEPLOY-02**: La migrazione `2026-06-01-resilience-audit.sql` è stata eseguita e il suo contenuto è live sul DB
- [x] **DEPLOY-03**: Il Telegram bot è stato ridistribuito con `wrangler deploy` e i fix K2/K3/K4/K5 sono attivi (status routing, kind constraint, webhook guard, resp.ok check)
- [ ] **DEPLOY-04**: `apply_accepted_modulations` è chiamato da `ingest.yml` e nel primo run post-deploy una modulazione accepted transita ad applied

### Correttezza Logiche Analytics (ANALYTICS)

- [ ] **ANALYTICS-01**: La baseline HRV (28d) esclude correttamente oggi e usa la data come chiave (non il valore HRV) — verifica B1 live su dati reali
- [ ] **ANALYTICS-02**: Il flag `fatigue_warning` scatta dopo 2 giorni consecutivi con HRV z < -1.0 SD e il flag `fatigue_critical` dopo 1 giorno con z < -2.0 SD (§5.1 CLAUDE.md)
- [ ] **ANALYTICS-03**: Il PMC riporta `None` per giorni senza dati (non 0), e il readiness score non mostra TSB "ottimale" su cold-start
- [ ] **ANALYTICS-04**: Il readiness composite score è clamped 0-100 e il brief mostra il label corretto (non `(None)`)
- [ ] **ANALYTICS-05**: Il risk module calcola il volume bucketing su data Rome (non UTC) — nessun crash su `started_at` come datetime

### Correttezza Fitness Test & Zone (FITNESS)

- [ ] **FITNESS-01**: `fitness_test_processor.py` non usa fallback `averageSpeed`→watt né `averagePace` come threshold — fix E1/E2 verificati su dati reali
- [x] **FITNESS-02**: FTP, CSS e soglia corsa in `physiology_zones` sono entro i bound fisiologici plausibili (FTP 80-450W, threshold 150-360 s/km, CSS 70-150 s/100m)
- [x] **FITNESS-03**: Il CSS è calcolato correttamente con guard `t400 > t200 > 0` — nessun valore negativo o assurdo
- [x] **FITNESS-04**: Il brief mostra le zone precise (Z1/Z2/Z3/Z4/Z5) basate su physiology_zones misurate per ogni disciplina

### Resilienza Pipeline (PIPELINE)

- [ ] **PIPELINE-01**: L'ingest Garmin propaga exit 1 su fallimento (no retry silenzioso) — fix L1 verificato nei GitHub Actions log
- [ ] **PIPELINE-02**: Il watchdog rileva componenti con riga health mancante (non solo righe stantie) — fix L4 verificato
- [ ] **PIPELINE-03**: Il DR snapshot aborta su tabelle critiche vuote invece di committare un backup corrotto — fix L3 verificato
- [ ] **PIPELINE-04**: Il brief mattutino arriva una sola volta ogni mattina (idempotency check) — no doppio invio

### Qualità Prescrizioni Sessioni (WORKOUT)

> **Priorità massima** — le sessioni proposte devono essere allenamenti strutturati, sensati, professionali e calibrati su Nicolò.

- [x] **WORKOUT-01**: Ogni sessione proposta include struttura completa: riscaldamento (durata + intensità), set principale (intervalli specifici con target watt/pace/HR per zona), defatigamento — mai solo "60 min Z2"
- [x] **WORKOUT-02**: Le zone prescritte usano sempre i valori misurati di `physiology_zones` (FTP bici, soglia corsa, CSS nuoto) — mai stime hard-coded o valori di default
- [x] **WORKOUT-03**: Ogni sessione rispetta i vincoli medici attivi: nuoto max Z1-Z2 (spalla destra), corsa +10% volume/settimana max con cap 14-15km, nessun Z4+ con spalla
- [x] **WORKOUT-04**: Il TSS atteso per ogni sessione è coerente con il target settimanale del mesociclo e la progressione CTL pianificata — non proposto in modo arbitrario
- [x] **WORKOUT-05**: La distribuzione delle sessioni settimanali rispetta l'80/20 del block periodization (Seiler/Laursen) — Z3 "grigio" minimizzato, qualità solo in blocchi dedicati

### Intelligenza Adattamento Fisiologico (ADAPT)

- [ ] **ADAPT-01**: Il sistema distingue il cedimento muscolare da quello cardiovascolare dai dati Garmin (HR drift, decoupling aerobico, RPE vs pace) — distinzione usata nelle prescrizioni e nell'analisi post-sessione
- [ ] **ADAPT-02**: I beliefs sull'adattamento di Nicolò (atleta endurance puro, primo cedimento muscolare non cardiovascolare) sono integrati esplicitamente in ogni proposta di sessione e modulazione
- [ ] **ADAPT-03**: Dopo pattern ripetuti (≥3 sessioni della stessa tipologia), il sistema aggiorna la stima di risposta fisiologica e aggiusta progressione e volume nelle sessioni future

### Resilienza Situazionale & Automazione (RESILIENCE)

- [ ] **RESILIENCE-01**: Una richiesta di spostare una sessione (via Telegram o MCP) produce una settimana ribilanciata — il carico viene ridistribuito coerentemente, non solo la sessione spostata nel calendario
- [ ] **RESILIENCE-02**: Una sessione saltata viene gestita automaticamente: se TSB > -10, la settimana viene ricalibrata; se TSB < -20, viene proposta una settimana alleggerita — proposta entro il ciclo ingest successivo senza che l'atleta debba chiederla
- [ ] **RESILIENCE-03**: Le trasferte in Croazia NON riducono il carico — il sistema adatta solo gli orari delle sessioni (Nicolò recupera meglio in trasferta: §2 CLAUDE.md)
- [ ] **RESILIENCE-04**: In caso di malattia (symptom flag o T° elevata), il sistema propone automaticamente il protocollo: stop intensità finché baseline non recupera 48h+, con re-entry plan graduale
- [ ] **AUTO-01**: La modulazione di una sessione saltata o spostata è proposta automaticamente entro il ciclo ingest successivo (via `plan_modulations` + Telegram button), senza richiedere input esplicito dell'atleta
- [ ] **AUTO-02**: Il piano settimanale viene proposto automaticamente ogni domenica sera come draft ready-to-confirm — Nicolò conferma o aggiusta, il sistema non aspetta la weekly review manuale per generare le sessioni

### Qualità Coaching — Brief & Sessioni (QUALITY-BRIEF)

- [ ] **QUALITY-BRIEF-01**: Il brief mattutino mostra TSB/HRV z-score/readiness con valori numerici reali — non placeholder o None
- [ ] **QUALITY-BRIEF-02**: La sessione del giorno nel brief include: disciplina, durata, zone target con ritmi/watt/HR precisi, struttura (riscaldamento/lavoro/defatigamento), TSS atteso
- [ ] **QUALITY-BRIEF-03**: Il brief segnala discrepanza >15 punti tra readiness Garmin e readiness interno (§12 CLAUDE.md)
- [ ] **QUALITY-BRIEF-04**: Il brief include il countdown alla gara (giorni a Lavarone) e il contesto di fase (base/build/specifico)

### Qualità Coaching — Analisi Post-Sessione (QUALITY-ANALYSIS)

- [ ] **QUALITY-ANALYSIS-01**: L'analisi post-sessione confronta performance vs piano (pace/watt vs target zone, HR drift, RPE vs atteso)
- [ ] **QUALITY-ANALYSIS-02**: L'analisi include citation tags `[source: ...]` per ogni decisione strutturale e `[athlete-belief: ...]` quando applica beliefs
- [ ] **QUALITY-ANALYSIS-03**: L'analisi identifica pattern di adattamento (positivo/negativo) e li mappa ai beliefs correnti dell'atleta
- [ ] **QUALITY-ANALYSIS-04**: L'analisi post-sessione per il nuoto segnala sempre lo stato della spalla destra e rispetta il vincolo Z4+

### Qualità Coaching — Weekly Review & Beliefs (QUALITY-WEEKLY)

- [ ] **QUALITY-WEEKLY-01**: La weekly review produce un output strutturato con: sommario carico (CTL/ATL/TSB trend), sessioni chiave analizzate, beliefs aggiornati, piano settimana successiva
- [ ] **QUALITY-WEEKLY-02**: Pattern extraction genera output con formato `[Osservazione] (n=X, conf=Y) → Prescrizione: ... Expected outcome: ...`
- [ ] **QUALITY-WEEKLY-03**: Il piano della settimana successiva viene committato su `planned_sessions` dopo conferma — verifica che non venga saltato (BUG-008)

### MCP Auth Hardening (MCP)

- [ ] **MCP-01**: Il piano in `docs/mcp_auth_hardening_plan.md` è eseguito: header mancante non trattato come autenticato, `/oauth/token` non ritorna service token senza verifica
- [ ] **MCP-02**: Gli item J2-J6 (req.json guardato, getRaceContext usa tabella `races`, check existingResp.ok, forceGarminSync senza busy-wait, zone consistency) sono risolti e deployati

---

## v2 Requirements

### Dashboard Enhancement

- **DASH-01**: ComplianceBar fa match sport-specifico tra attività e sessioni pianificate (fix N6)
- **DASH-02**: ReadinessCard mostra "NaN giorni" come fallback leggibile se race_date è malformato (fix N5)
- **DASH-03**: Token null inviato come `Bearer null` nell'api.ts (fix N4)

### Strava Integration

- **STRAVA-01**: Ingest Strava riattivato in `ingest.yml` con paginazione e gestione 429
- **STRAVA-02**: Cross-validation Garmin/Strava per attività duplicate

### Google Calendar

- **GCAL-01**: Sync `planned_sessions` ↔ Google Calendar via OAuth (creazione/aggiornamento/cancellazione eventi)
- **GCAL-02**: `calendar_event_id` collegato a eventi reali

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-athlete support | Schema senza user_id; aggiungere multi-tenancy richiederebbe rewrite completo |
| App mobile nativa | Telegram bot è l'interfaccia mobile sufficiente |
| Google Calendar (v1) | OAuth complexity; rinviato post-Lavarone |
| Consigli nutrizionali specifici | Fuori dalla competenza del sistema; reindirizza a dietista sportivo |
| Strava sync attiva (v1) | Disabilitata in ingest.yml; Garmin = single source of truth |
| Phase 5 Cognitive expansion | Oltre l'orizzonte attuale (coaching philosophy layer, multi-memory) |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VERIFY-01 | Phase 1 | Pending |
| ANALYTICS-01 | Phase 1 | Pending |
| ANALYTICS-02 | Phase 1 | Pending |
| ANALYTICS-03 | Phase 1 | Pending |
| ANALYTICS-04 | Phase 1 | Pending |
| ANALYTICS-05 | Phase 1 | Pending |
| FITNESS-01 | Phase 2 | Pending |
| FITNESS-02 | Phase 2 | Complete |
| FITNESS-03 | Phase 2 | Complete |
| VERIFY-02 | Phase 2 | Complete |
| DEPLOY-01 | Phase 3 | Complete |
| DEPLOY-02 | Phase 3 | Complete |
| DEPLOY-03 | Phase 3 | Complete |
| DEPLOY-04 | Phase 3 | Pending |
| PIPELINE-01 | Phase 3 | Pending |
| PIPELINE-02 | Phase 3 | Pending |
| PIPELINE-03 | Phase 3 | Pending |
| PIPELINE-04 | Phase 3 | Pending |
| VERIFY-03 | Phase 4 | Complete |
| VERIFY-04 | Phase 4 | Complete |
| VERIFY-05 | Phase 4 | Complete |
| VERIFY-06 | Phase 4 | Complete |
| FITNESS-04 | Phase 4 | Complete |
| WORKOUT-01 | Phase 5 | Complete |
| WORKOUT-02 | Phase 5 | Complete |
| WORKOUT-03 | Phase 5 | Complete |
| WORKOUT-04 | Phase 5 | Complete |
| WORKOUT-05 | Phase 5 | Complete |
| ADAPT-01 | Phase 6 | Pending |
| ADAPT-02 | Phase 6 | Pending |
| ADAPT-03 | Phase 6 | Pending |
| RESILIENCE-01 | Phase 7 | Pending |
| RESILIENCE-02 | Phase 7 | Pending |
| RESILIENCE-03 | Phase 7 | Pending |
| RESILIENCE-04 | Phase 7 | Pending |
| AUTO-01 | Phase 7 | Pending |
| AUTO-02 | Phase 7 | Pending |
| QUALITY-BRIEF-01 | Phase 8 | Pending |
| QUALITY-BRIEF-02 | Phase 8 | Pending |
| QUALITY-BRIEF-03 | Phase 8 | Pending |
| QUALITY-BRIEF-04 | Phase 8 | Pending |
| QUALITY-ANALYSIS-01 | Phase 9 | Pending |
| QUALITY-ANALYSIS-02 | Phase 9 | Pending |
| QUALITY-ANALYSIS-03 | Phase 9 | Pending |
| QUALITY-ANALYSIS-04 | Phase 9 | Pending |
| QUALITY-WEEKLY-01 | Phase 10 | Pending |
| QUALITY-WEEKLY-02 | Phase 10 | Pending |
| QUALITY-WEEKLY-03 | Phase 10 | Pending |
| MCP-01 | Phase 11 | Pending |
| MCP-02 | Phase 11 | Pending |

**Coverage:**

- v1 requirements: 50 total
- Mapped to phases: 50
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-05 after initial definition*
