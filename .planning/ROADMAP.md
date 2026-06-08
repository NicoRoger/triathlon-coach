# Roadmap: Triathlon AI Coach — Integrità & Qualità Elite

**Core Value:** Ogni mattina Nicolò riceve dati corretti, analisi attendibili e prescrizioni allineate all'allenamento élite — e può fidarsi ciecamente del sistema per prepararsi alla gara.

**Granularity:** fine
**Mode:** mvp
**Requirements:** 50 v1 mapped across 11 phases

---

## Phases

- [x] **Phase 1: Test Suite & Analytics Correctness** — La suite pytest è verde e le logiche analytics (HRV, PMC, readiness, risk) si comportano correttamente su dati reali (completed 2026-06-05)
- [x] **Phase 2: Fitness Test Correctness** — I valori physiology_zones (FTP, CSS, soglia corsa) nel DB sono corretti, plausibili e non corrotti dai bug E1/E2 (completed 2026-06-05)
- [x] **Phase 3: Deploy & Pipeline Resilience** — Migrazioni eseguite, Telegram bot ridistribuito, pipeline ingest resiliente con exit codes e DR corretti (completed 2026-06-07)
- [x] **Phase 4: Live Behavior Verification** — Il sistema si comporta come atteso end-to-end su dati reali: brief, analisi, modulazioni, budget
 (completed 2026-06-07)

- [x] **Phase 5: Workout Prescription Quality** — Le sessioni proposte sono strutturate, professionali, calibrate su fisiologia misurata e vincoli medici di Nicolò (completed 2026-06-08)
- [ ] **Phase 6: Physiological Adaptation Intelligence** — Il sistema distingue cedimento muscolare da cardiovascolare e integra i beliefs di adattamento nelle prescrizioni
- [ ] **Phase 7: Situational Resilience & Automation** — Gestione automatica di spostamenti, sessioni saltate, trasferte Croazia e malattia — senza aumentare i costi LLM
- [ ] **Phase 8: Brief Quality** — Il brief mattutino ha qualità da coaching pro: dati numerici reali, sessione strutturata, discrepanza readiness, countdown gara
- [ ] **Phase 9: Post-Session Analysis Quality** — Le analisi post-sessione sono a livello coach professionista: confronto vs piano, citation tags, pattern adattamento, vincolo spalla
- [ ] **Phase 10: Weekly Review & Beliefs Quality** — La weekly review produce insight azionabili, beliefs aggiornati e piano settimana committato correttamente
- [x] **Phase 11: MCP Auth Hardening** — Il server MCP è protetto da autenticazione corretta e i bug funzionali J2-J6 sono risolti e deployati (completed 2026-06-08)

---

## Phase Details

### Phase 1: Test Suite & Analytics Correctness

**Goal**: La test suite pytest è verde e ogni logica analytics critica (HRV baseline, PMC, readiness, risk) produce output corretti su dati reali
**Mode:** mvp
**Depends on**: Nothing (foundation)
**Requirements**: VERIFY-01, ANALYTICS-01, ANALYTICS-02, ANALYTICS-03, ANALYTICS-04, ANALYTICS-05
**Success Criteria** (what must be TRUE):

  1. `pytest` eseguito localmente termina con 0 failures su tutte le logiche critiche (HRV, PMC, readiness, fitness test, modulation, budget, DR, watchdog)
  2. La baseline HRV 28d usa la data come chiave e non include il giorno corrente — verificato su dati reali dal DB
  3. Il flag `fatigue_warning` scatta esattamente dopo 2 giorni consecutivi con HRV z < -1.0 SD, e `fatigue_critical` dopo 1 giorno con z < -2.0 SD
  4. Il PMC riporta `None` (non 0) per giorni senza dati, e il readiness score mostra label leggibili (non `None`)
  5. Il risk module non crasha su `started_at` come datetime e usa la timezone Rome per il bucketing dei volumi

**Plans**: 2 plans
Plans:

- [x] 01-01-PLAN.md — Test ANALYTICS-04 (readiness_label/score) + gate suite pytest verde
- [x] 01-02-PLAN.md — Script verify_analytics.py: verifica live HRV/PMC/readiness/risk su dati reali

### Phase 2: Fitness Test Correctness

**Goal**: I valori FTP, CSS e soglia corsa nel DB derivano dai test fitness eseguiti da Nicolò a giugno 2026, sono entro bounds fisiologici plausibili, e non sono stati corrotti dai bug E1/E2
**Mode:** mvp
**Depends on**: Phase 1 (analytics layer verified)
**Requirements**: FITNESS-01, FITNESS-02, FITNESS-03, VERIFY-02
**Success Criteria** (what must be TRUE):

  1. `fitness_test_processor.py` non usa `averageSpeed` come proxy per watt né `averagePace` come threshold — fix E1/E2 confermati su codice e dati reali
  2. FTP in DB è tra 80 e 450W, threshold corsa è tra 150 e 360 s/km, CSS è tra 70 e 150 s/100m — valori coerenti con i test di giugno 2026 di Nicolò
  3. Il CSS è calcolato con guard `t400 > t200 > 0` — nessun valore negativo o assurdo in DB
  4. La query `physiology_zones` per FTP, CSS e soglia corsa ritorna righe non null con timestamp aggiornato post-test

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Script verify_physiology.py: mostra zones DB vs CLAUDE.md con bounds check
- [x] 02-02-PLAN.md — Script cleanup_physiology_zones.py: dry-run + --confirm DELETE righe fuori bounds

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Trigger processore giugno 2026 + checkpoint verifica finale physiology_zones

### Phase 3: Deploy & Pipeline Resilience

**Goal**: Tutte le migrazioni pending sono live su Supabase, il Telegram bot è ridistribuito con i fix K2-K5, e la pipeline ingest è resiliente con exit codes corretti, DR funzionante e idempotency sul brief
**Mode:** mvp
**Depends on**: Phase 2 (correct physiology_zones before deploy)
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, PIPELINE-01, PIPELINE-02, PIPELINE-03, PIPELINE-04
**Success Criteria** (what must be TRUE):

  1. Tutte le migrazioni in `OPEN_ISSUES.md` e `2026-06-01-resilience-audit.sql` sono eseguite in Supabase e lo schema live corrisponde (CHECK constraints, UNIQUE, FK ON DELETE, expires_at, kind values)
  2. `wrangler deploy` eseguito sul Telegram bot — i fix K2/K3/K4/K5 (status routing, kind constraint, webhook guard, resp.ok check) sono attivi nel worker live
  3. `apply_accepted_modulations` è referenziato in `ingest.yml` e nel log del primo run post-deploy compare la transizione `accepted → applied` per una modulazione reale
  4. L'ingest Garmin propaga exit 1 su fallimento nei GitHub Actions log — nessun retry silenzioso
  5. Il DR snapshot aborta su tabelle critiche vuote e il watchdog rileva componenti con health row mancante
  6. Il brief mattutino non viene inviato due volte nello stesso giorno — idempotency verificata nei log Telegram

**Plans**: TBD

### Phase 4: Live Behavior Verification

**Goal**: Il sistema end-to-end si comporta correttamente su dati reali: brief con zone precise, analisi post-sessione generate con Gemini, modulazioni con inline buttons funzionanti, budget tracker accurato
**Mode:** mvp
**Depends on**: Phase 3 (migrations live, bot deployed)
**Requirements**: VERIFY-03, VERIFY-04, VERIFY-05, VERIFY-06, FITNESS-04
**Success Criteria** (what must be TRUE):

  1. Il brief mattutino ricevuto da Nicolò su Telegram mostra zone numeriche precise (watt/pace/HR) basate su `physiology_zones` misurate, non stime o placeholder
  2. Dopo un sync Garmin, una riga in `session_analyses` viene generata con testo non vuoto e `model_used = 'gemini-2.5-flash'`
  3. Una modulazione proposta compare su Telegram con inline buttons ✅/❌, e dopo il tap ✅ il ciclo ingest successivo aggiorna `planned_sessions`
  4. Il budget tracker in DB mostra la spesa Anthropic reale — la soglia di degrado a €4.00 (Sonnet→Haiku) è configurata e verificata nei log
  5. Il brief mostra le zone Z1-Z5 per ogni disciplina derivate da physiology_zones misurate (non hard-coded)

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Brief zone misurate (VERIFY-03 + FITNESS-04): physiology_zones → Z1-Z5 inline nel brief
- [x] 04-02-PLAN.md — Pipeline session_analyses + modulazione end-to-end (VERIFY-04 + VERIFY-05 + DEPLOY-04): routing Gemini, accepted→applied
- [x] 04-03-PLAN.md — Budget tracker (VERIFY-06): soglia degrado Sonnet→Haiku allineata a €4.00

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-04-PLAN.md — Script verify_live_behavior.py read-only + checkpoint finale 4/4 OK

### Phase 5: Workout Prescription Quality

**Goal**: Le sessioni proposte dal sistema sono strutturate, professionali, calibrate su fisiologia misurata e rispettano vincoli medici e metodologia élite — paragonabili a quelle di un coach professionista
**Mode:** mvp
**Depends on**: Phase 4 (live system verified, physiology_zones in DB)
**Requirements**: WORKOUT-01, WORKOUT-02, WORKOUT-03, WORKOUT-04, WORKOUT-05
**Success Criteria** (what must be TRUE):

  1. Ogni sessione proposta include struttura completa: riscaldamento con durata e intensità, set principale con intervalli specifici (es. "6×4min a 105% FTP, rec 2min"), defatigamento — mai una prescrizione generica
  2. Le zone usano valori numerici precisi da `physiology_zones` (watt per bici, pace s/km per corsa, s/100m per nuoto) — zero stime hard-coded
  3. Nessuna sessione nuoto supera Z2 (vincolo spalla destra); le sessioni corsa rispettano il cap di volume e la progressione +10%/settimana
  4. Il TSS atteso di ogni sessione è documentato ed è coerente con il budget settimanale del mesociclo corrente
  5. Il mix settimanale rispetta l'80/20: almeno 80% delle sessioni è Z1-Z2, i blocchi di qualità (Z4-Z5) sono programmati su giorni non consecutivi

**Plans**: 4 plans

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Migration active_constraints + progression_plan + test WORKOUT-03 + scaffold verify script

**Wave 2** *(blocked on Wave 1)*

- [x] 05-02-PLAN.md — MCP Worker: age_days, active_constraints, current_progression_step, update_constraint, progression_plan + deploy

**Wave 3** *(blocked on Wave 2)*

- [x] 05-03-PLAN.md — Skill prompts: propose_session/generate_mesocycle/fitness_test (gate fisiologico, vincoli dinamici, drill, contesto mesociclo, race-pace)

**Wave 4** *(blocked on Wave 3)*

- [x] 05-04-PLAN.md — Phase gate: apply migration + verify script completo + suite pytest + checkpoint output LLM (WORKOUT-01..05)

### Phase 6: Physiological Adaptation Intelligence

**Goal**: Il sistema capisce come il corpo di Nicolò risponde agli stimoli allenanti — distingue cedimento muscolare da cardiovascolare, integra i beliefs di adattamento nelle prescrizioni e aggiusta la progressione sui pattern osservati
**Mode:** mvp
**Depends on**: Phase 5 (workout quality baseline in place)
**Requirements**: ADAPT-01, ADAPT-02, ADAPT-03
**Success Criteria** (what must be TRUE):

  1. Le analisi post-sessione identificano esplicitamente il tipo di cedimento (muscolare vs cardiovascolare) usando HR drift, decoupling aerobico e RPE — e la classificazione viene usata nella sessione successiva della stessa disciplina
  2. Il belief "atleta endurance puro, primo cedimento muscolare" è attivo in `beliefs` con confidence ≥ 0.7 e viene citato nelle prescrizioni con `[athlete-belief: ...]`
  3. Dopo 3+ sessioni della stessa tipologia, il sistema aggiorna il belief di risposta fisiologica (es. "risponde bene agli interval run 4min") e aggiusta la progressione nel mesociclo

**Plans**: 4 plans

Plans:
**Wave 1**

- [x] 06-01-PLAN.md — Fondazione: migration (colonne session_analyses + seed belief endurance_failure_type) + test scaffold Wave 0

**Wave 2** *(blocked on Wave 1)*

- [ ] 06-02-PLAN.md — ADAPT-01: classify_fatigue_type() in readiness.py + hook in post_session_analysis (fatigue_type/confidence/sport in session_analyses)

**Wave 3** *(blocked on Wave 2)*

- [ ] 06-03-PLAN.md — ADAPT-02: get_weekly_context espone active_beliefs + last_fatigue_by_sport + propose_session.md cita [athlete-belief] (deploy)

**Wave 4** *(blocked on Wave 3)*

- [ ] 06-04-PLAN.md — ADAPT-03: job belief update in pattern_extraction.py + update progression_plan + phase gate

### Phase 7: Situational Resilience & Automation

**Goal**: Il sistema gestisce automaticamente situazioni reali — spostamenti sessioni, sessioni saltate, trasferte Croazia, malattia — proponendo ricalibrazione senza che Nicolò debba chiederla, usando solo modelli gratuiti (Gemini)
**Mode:** mvp
**Depends on**: Phase 4 (live system verified), Phase 5 (workout quality for rescheduled sessions)
**Requirements**: RESILIENCE-01, RESILIENCE-02, RESILIENCE-03, RESILIENCE-04, AUTO-01, AUTO-02
**Success Criteria** (what must be TRUE):

  1. Quando Nicolò sposta una sessione (via Telegram o MCP), il sistema risponde con la settimana ribilanciata — carico redistribuito, non solo la sessione spostata nel calendario
  2. Una sessione saltata genera automaticamente una proposta di `plan_modulation` entro il ciclo ingest successivo: ricalibrazione se TSB > -10, alleggerimento settimana se TSB < -20
  3. Le sessioni nelle settimane di trasferta Croazia non vengono ridotte — il sistema adatta solo gli orari, con log esplicito "trasferta = recovery bonus atteso"
  4. Su `illness_flag` attivo, il sistema genera automaticamente un protocollo di rientro: intensità sospesa finché baseline non recupera 48h+, sessioni sostitutive leggere proposte
  5. Ogni domenica sera viene generata automaticamente una proposta di piano settimanale (`plan_modulations` tipo `weekly_plan`) ready-to-confirm su Telegram — senza richiedere weekly review manuale
  6. Tutte le azioni automatiche (rescheduling, illness, missed session) usano solo Gemini Flash (costo €0) — zero chiamate Anthropic aggiuntive

**Plans**: TBD

### Phase 8: Brief Quality

**Goal**: Il brief mattutino ha qualità da coaching professionale — dati numerici reali, sessione strutturata con riscaldamento/lavoro/defatigamento, discrepanza readiness segnalata, countdown gara
**Mode:** mvp
**Depends on**: Phase 5 (workout quality — session detail in brief comes from prescriptions)
**Requirements**: QUALITY-BRIEF-01, QUALITY-BRIEF-02, QUALITY-BRIEF-03, QUALITY-BRIEF-04
**Success Criteria** (what must be TRUE):

  1. Il brief mostra TSB, HRV z-score e readiness score con valori numerici reali — nessun placeholder, nessun None
  2. La sessione del giorno nel brief include disciplina, durata, zone target con ritmi/watt/HR precisi, struttura in fasi (riscaldamento/lavoro/defatigamento) e TSS atteso
  3. Quando il readiness Garmin e quello interno differiscono di oltre 15 punti, il brief include un segnale esplicito di discrepanza
  4. Il brief contiene il countdown in giorni a Lavarone (2026-09-06) e il label della fase corrente (base/build/specifico/peak/taper)

**Plans**: TBD

### Phase 9: Post-Session Analysis Quality

**Goal**: Le analisi post-sessione hanno profondità da coach professionista — confronto vs piano, citation tags su ogni decisione, pattern di adattamento mappati sui beliefs, vincolo spalla esplicitato per il nuoto
**Mode:** mvp
**Depends on**: Phase 6 (adaptation intelligence active), Phase 8 (brief quality baseline)
**Requirements**: QUALITY-ANALYSIS-01, QUALITY-ANALYSIS-02, QUALITY-ANALYSIS-03, QUALITY-ANALYSIS-04
**Success Criteria** (what must be TRUE):

  1. Ogni analisi post-sessione confronta la performance reale vs il piano (pace/watt vs zona target, HR drift, RPE vs atteso)
  2. Ogni decisione strutturale nell'analisi porta un tag `[source: ...]` e ogni applicazione di belief porta `[athlete-belief: ...]`
  3. L'analisi identifica il pattern di adattamento (positivo/negativo) e lo mappa esplicitamente a uno o più beliefs dell'atleta
  4. Le analisi post-nuoto contengono sempre un paragrafo sullo stato della spalla destra e confermano che la sessione è rimasta entro Z1-Z2

**Plans**: TBD

### Phase 10: Weekly Review & Beliefs Quality

**Goal**: La weekly review produce un report strutturato con CTL/ATL/TSB trend, beliefs aggiornati con formato standard, e piano settimana successiva committato su `planned_sessions` dopo conferma
**Mode:** mvp
**Depends on**: Phase 9 (analysis quality baseline established)
**Requirements**: QUALITY-WEEKLY-01, QUALITY-WEEKLY-02, QUALITY-WEEKLY-03
**Success Criteria** (what must be TRUE):

  1. L'output della weekly review contiene: sommario carico con CTL/ATL/TSB trend, almeno 2 sessioni chiave analizzate, beliefs aggiornati, e piano strutturato per la settimana successiva
  2. I pattern estratti dalla pattern extraction hanno il formato `[Osservazione] (n=X, conf=Y) → Prescrizione: ... Expected outcome: ...`
  3. Dopo conferma esplicita, il piano della settimana successiva viene scritto su `planned_sessions` — il campo `created_at` delle sessioni è post-review e la weekly non salta il commit (BUG-008 risolto)

**Plans**: TBD

### Phase 11: MCP Auth Hardening

**Goal**: Il server MCP rifiuta richieste senza header di autenticazione valido, non espone il service token senza verifica, e i bug funzionali J2-J6 sono risolti e deployati
**Mode:** mvp
**Depends on**: Phase 3 (deploy infrastructure in place)
**Requirements**: MCP-01, MCP-02
**Success Criteria** (what must be TRUE):

  1. Una richiesta al MCP server senza header di autenticazione riceve 401 — non viene trattata come autenticata
  2. L'endpoint `/oauth/token` non ritorna un service token senza verifica delle credenziali
  3. I fix J2-J6 sono deployati: `req.json` è guardato, `getRaceContext` usa la tabella `races`, `existingResp.ok` è verificato, `forceGarminSync` non fa busy-wait, le zone sono consistenti tra tool e DB

**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Suite & Analytics Correctness | 2/2 | Complete   | 2026-06-05 |
| 2. Fitness Test Correctness | 3/3 | Complete   | 2026-06-05 |
| 3. Deploy & Pipeline Resilience | 4/4 | Complete   | 2026-06-07 |
| 4. Live Behavior Verification | 4/4 | Complete    | 2026-06-07 |
| 5. Workout Prescription Quality | 4/4 | Complete    | 2026-06-08 |
| 6. Physiological Adaptation Intelligence | 1/4 | In Progress|  |
| 7. Situational Resilience & Automation | 0/0 | Not started | - |
| 8. Brief Quality | 0/0 | Not started | - |
| 9. Post-Session Analysis Quality | 0/0 | Not started | - |
| 10. Weekly Review & Beliefs Quality | 0/0 | Not started | - |
| 11. MCP Auth Hardening | 2/2 | Complete    | 2026-06-08 |

---

## Coverage

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
| DEPLOY-01 | Phase 3 | Complete |
| DEPLOY-02 | Phase 3 | Complete |
| DEPLOY-03 | Phase 3 | Complete |
| DEPLOY-04 | Phase 3 | Complete |
| PIPELINE-01 | Phase 3 | Complete |
| PIPELINE-02 | Phase 3 | Complete |
| PIPELINE-03 | Phase 3 | Complete |
| PIPELINE-04 | Phase 3 | Complete |
| VERIFY-03 | Phase 4 | Pending |
| VERIFY-04 | Phase 4 | Pending |
| VERIFY-05 | Phase 4 | Pending |
| VERIFY-06 | Phase 4 | Pending |
| FITNESS-04 | Phase 4 | Pending |
| WORKOUT-01 | Phase 5 | Pending |
| WORKOUT-02 | Phase 5 | Pending |
| WORKOUT-03 | Phase 5 | Pending |
| WORKOUT-04 | Phase 5 | Pending |
| WORKOUT-05 | Phase 5 | Pending |
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

**Total v1 requirements:** 50
**Mapped:** 50/50 ✓
**Unmapped:** 0

---

*Roadmap created: 2026-06-05*
*Milestone: Integrità & Qualità Elite*
