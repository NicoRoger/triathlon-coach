# Requirements: Triathlon AI Coach — Integrità & Qualità Elite

**Defined:** 2026-06-05
**Core Value:** Ogni mattina Nicolò riceve dati corretti, analisi attendibili e prescrizioni allineate all'allenamento élite — e può fidarsi ciecamente del sistema per prepararsi alla gara.

> **Principio trasversale**: non dare per scontato che i fix committati funzionino.
> Ogni requisito di verifica implica osservare il comportamento reale, non solo leggere il codice.

---

## v1 Requirements

### Verifica Fix Precedenti (VERIFY)

- [ ] **VERIFY-01**: L'intera test suite pytest passa verde localmente senza failures su logiche critiche (HRV, PMC, readiness, fitness test, modulation, budget, DR, watchdog)
- [ ] **VERIFY-02**: I valori di `physiology_zones` nel DB per FTP, CSS e soglia corsa corrispondono ai test fitness eseguiti da Nicolò a giugno 2026 — valori plausibili e non corrotti da bug E1/E2
- [ ] **VERIFY-03**: Il brief mattutino inviato via Telegram mostra la sessione del giorno con zone corrette basate su physiology_zones misurate (non stime)
- [ ] **VERIFY-04**: Le analisi post-sessione in `session_analyses` vengono generate dopo ogni sync Garmin e contengono testo non vuoto e `model_used = gemini-2.5-flash`
- [ ] **VERIFY-05**: Le modulazioni proposte via Telegram compaiono con inline buttons ✅/❌, e quelle accettate vengono applicate a `planned_sessions` nel ciclo ingest successivo
- [ ] **VERIFY-06**: Il budget tracker riflette la spesa reale Anthropic — non si supera €5/mese e il degrado Sonnet→Haiku scatta a €4.00 correttamente

### Deploy & Migrazioni (DEPLOY)

- [ ] **DEPLOY-01**: Tutte le migrazioni pending in `OPEN_ISSUES.md` sono state eseguite in Supabase e verificate (CHECK constraint, UNIQUE, FK ON DELETE, expires_at, kind values)
- [ ] **DEPLOY-02**: La migrazione `2026-06-01-resilience-audit.sql` è stata eseguita e il suo contenuto è live sul DB
- [ ] **DEPLOY-03**: Il Telegram bot è stato ridistribuito con `wrangler deploy` e i fix K2/K3/K4/K5 sono attivi (status routing, kind constraint, webhook guard, resp.ok check)
- [ ] **DEPLOY-04**: `apply_accepted_modulations` è chiamato da `ingest.yml` e nel primo run post-deploy una modulazione accepted transita ad applied

### Correttezza Logiche Analytics (ANALYTICS)

- [ ] **ANALYTICS-01**: La baseline HRV (28d) esclude correttamente oggi e usa la data come chiave (non il valore HRV) — verifica B1 live su dati reali
- [ ] **ANALYTICS-02**: Il flag `fatigue_warning` scatta dopo 2 giorni consecutivi con HRV z < -1.0 SD e il flag `fatigue_critical` dopo 1 giorno con z < -2.0 SD (§5.1 CLAUDE.md)
- [ ] **ANALYTICS-03**: Il PMC riporta `None` per giorni senza dati (non 0), e il readiness score non mostra TSB "ottimale" su cold-start
- [ ] **ANALYTICS-04**: Il readiness composite score è clamped 0-100 e il brief mostra il label corretto (non `(None)`)
- [ ] **ANALYTICS-05**: Il risk module calcola il volume bucketing su data Rome (non UTC) — nessun crash su `started_at` come datetime

### Correttezza Fitness Test & Zone (FITNESS)

- [ ] **FITNESS-01**: `fitness_test_processor.py` non usa fallback `averageSpeed`→watt né `averagePace` come threshold — fix E1/E2 verificati su dati reali
- [ ] **FITNESS-02**: FTP, CSS e soglia corsa in `physiology_zones` sono entro i bound fisiologici plausibili (FTP 80-450W, threshold 150-360 s/km, CSS 70-150 s/100m)
- [ ] **FITNESS-03**: Il CSS è calcolato correttamente con guard `t400 > t200 > 0` — nessun valore negativo o assurdo
- [ ] **FITNESS-04**: Il brief mostra le zone precise (Z1/Z2/Z3/Z4/Z5) basate su physiology_zones misurate per ogni disciplina

### Resilienza Pipeline (PIPELINE)

- [ ] **PIPELINE-01**: L'ingest Garmin propaga exit 1 su fallimento (no retry silenzioso) — fix L1 verificato nei GitHub Actions log
- [ ] **PIPELINE-02**: Il watchdog rileva componenti con riga health mancante (non solo righe stantie) — fix L4 verificato
- [ ] **PIPELINE-03**: Il DR snapshot aborta su tabelle critiche vuote invece di committare un backup corrotto — fix L3 verificato
- [ ] **PIPELINE-04**: Il brief mattutino arriva una sola volta ogni mattina (idempotency check) — no doppio invio

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
| FITNESS-02 | Phase 2 | Pending |
| FITNESS-03 | Phase 2 | Pending |
| VERIFY-02 | Phase 2 | Pending |
| DEPLOY-01 | Phase 3 | Pending |
| DEPLOY-02 | Phase 3 | Pending |
| DEPLOY-03 | Phase 3 | Pending |
| DEPLOY-04 | Phase 3 | Pending |
| PIPELINE-01 | Phase 3 | Pending |
| PIPELINE-02 | Phase 3 | Pending |
| PIPELINE-03 | Phase 3 | Pending |
| PIPELINE-04 | Phase 3 | Pending |
| VERIFY-03 | Phase 4 | Pending |
| VERIFY-04 | Phase 4 | Pending |
| VERIFY-05 | Phase 4 | Pending |
| VERIFY-06 | Phase 4 | Pending |
| FITNESS-04 | Phase 4 | Pending |
| QUALITY-BRIEF-01 | Phase 5 | Pending |
| QUALITY-BRIEF-02 | Phase 5 | Pending |
| QUALITY-BRIEF-03 | Phase 5 | Pending |
| QUALITY-BRIEF-04 | Phase 5 | Pending |
| QUALITY-ANALYSIS-01 | Phase 6 | Pending |
| QUALITY-ANALYSIS-02 | Phase 6 | Pending |
| QUALITY-ANALYSIS-03 | Phase 6 | Pending |
| QUALITY-ANALYSIS-04 | Phase 6 | Pending |
| QUALITY-WEEKLY-01 | Phase 7 | Pending |
| QUALITY-WEEKLY-02 | Phase 7 | Pending |
| QUALITY-WEEKLY-03 | Phase 7 | Pending |
| MCP-01 | Phase 8 | Pending |
| MCP-02 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-05 after initial definition*
