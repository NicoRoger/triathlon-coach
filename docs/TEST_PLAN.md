# Step 6.5 — Audit Resilienza Sistema Completo

## Contesto

Sto lavorando su `triathlon-coach`. Step 6 (coach reattivo continuo + budget cap) è stato implementato e committato. Adesso prima di procedere con altre feature, voglio fare un audit completo della resilienza del sistema. Sospetto che ci siano bug, edge case non gestiti, e comportamenti scorretti del bot Telegram.

**Repo**: https://github.com/NicoRoger/triathlon-coach
**Branch**: main
**Stato attuale**:
- 7 sessioni planned per settimana 7-13 maggio
- Bot Telegram con comandi vari (/log, /rpe, /status, /debrief, /budget, /help)
- 7 workflow GitHub Actions
- 7 tool MCP esposti
- 11+ skill files
- Tutta l'infrastruttura Step 6 (analisi sessione, modulazione, proactive questions, pattern extraction, race week mental coaching)
- Episodio noto: stamattina 8 maggio il debrief mattutino sembra essere fallito, possibilmente perché non c'è allenamento programmato. Da investigare.

## Cosa devi fare

Sei un test engineer ed un security auditor. Il tuo lavoro è:
1. Identificare TUTTE le vulnerabilità funzionali e di robustezza del sistema
2. Categorizzarle per gravità
3. Fixare quelle critiche
4. Documentare quelle non critiche come issue
5. Creare suite di test che coprono i casi trovati

**Filosofia**: meglio un test paranoico che un bug in produzione. Pensa come un utente che USA il sistema ogni giorno per 6 mesi: tutti gli scenari "strani ma plausibili" devono essere coperti.

## Task 1 — Audit comportamento bot Telegram

### 1.1 — Mappa esistente

Crea documento `docs/telegram_bot_audit_2026-05-09.md` che mappa:

- **Tutti i comandi attualmente accettati** dal bot (`workers/telegram-bot/src/index.ts`)
- Per ciascuno: parametri attesi, parser regex usato, side effects (DB write, MCP calls, ecc.)
- **Tutti i pattern di parsing automatico** del testo libero (es. "ho male alla spalla" → injury_flag)
- **Allow-list singolo utente**: rischio di leak se chat_id sbagliato

### 1.2 — Test casi reali

Per OGNI comando del bot, esegui questi test e documenta esito:

**Test funzionali base:**
- Comando con sintassi corretta → risposta corretta
- Comando con sintassi sbagliata → errore graceful (no crash, no message muto)
- Comando vuoto (es. `/log` senza argomenti)
- Comando con argomenti molto lunghi (1000+ caratteri)
- Comando con caratteri speciali (emoji, accenti, virgolette tipografiche)
- Comando in italiano vs inglese vs misto
- Comando con typo (es. `/lgo` invece di `/log`)

**Test edge case:**
- 2 messaggi inviati in 2 secondi (race condition)
- Stesso comando 5 volte di fila (idempotenza, dedup updates)
- Bot offline e poi online (quale messaggio elabora? il primo? l'ultimo? tutti?)
- Messaggio che NON è un comando ma testo libero senza /
- Reply a un messaggio del bot (gestito o ignorato?)
- Forward di un messaggio
- Messaggio audio/foto/file (deve essere ignorato senza crash)

**Test persistenza dati:**
- `/log RPE 7` → verifica che colonna `rpe` (numerica) si popoli, non solo `parsed_data` JSONB
- `/log mi fa male la spalla forte` → verifica `injury_flag=true`, `injury_details` popolato
- `/debrief` → verifica TUTTE le colonne native si popolino (parser fix Step 5.0)
- Pattern proattivo (risposta a domanda settimanale): viene loggato con purpose corretto?

**Test stato globale:**
- `/status` mostra TUTTI i componenti? Inclusi i nuovi (api_usage, pattern_extraction, proactive_check_in)?
- `/budget` funziona dopo prima chiamata API (test che hai fatto ieri)?

### 1.3 — Bug noti riportati dall'utente

Stamattina (8 maggio) il debrief mattutino è fallito. **Investiga la causa root**:
- Verifica log del workflow `morning-briefing.yml` su GitHub Actions
- Verifica codice di `coach/planning/briefing.py` su scenario "no planned session today"
- Causa probabile: la sezione `_build_session_section` o `_build_race_progress_section` ha qualche edge case quando `planned` è None
- Fix se confermato

### 1.4 — Output

Per ogni test crea entry in `docs/telegram_bot_audit_2026-05-09.md`:
Test [nome]
Setup: [contesto]
Input: [esatto comando inviato]
Atteso: [comportamento atteso]
Osservato: [comportamento reale]
Esito: ✅ ok / ⚠️ degraded / ❌ broken
Severità: P0/P1/P2/P3
Fix proposto: [se broken/degraded]

Severità:
- **P0**: dati persi, crash sistema, perdita budget API non controllata
- **P1**: comando importante non funziona, dati salvati in posto sbagliato
- **P2**: messaggio inelegante ma sistema gira
- **P3**: cosmetico

## Task 2 — Audit resilienza pipeline ingest

### 2.1 — Test scenari di failure Garmin

Simula questi scenari e verifica che il sistema reagisca correttamente:

**Auth failure:**
- Token Garmin scaduto → workflow ingest gestisce gracefully? Manda alert? Non corrompe DB?
- Re-auth necessario → istruzioni in RUNBOOK chiare?

**Rate limit:**
- Garmin restituisce 429 → retry con backoff? Quanti tentativi? Cosa succede dopo l'ultimo retry?
- Comportamento durante backfill esteso (>30 giorni in una run)

**Data corruption:**
- Attività con campi mancanti (es. distance_m=null, hr_zones_s vuoto)
- Attività duplicata (stesso external_id) → upsert idempotente o duplicato?
- Attività con timestamp futuro (caso anomalo)
- Attività "Manual" senza dispositivo (es. inserita a mano sul Garmin Connect)

**Network failure:**
- Timeout durante chiamata → retry?
- Connection terminated mid-stream (è successo durante backfill 11 aprile 2025)

### 2.2 — Test idempotenza

Esegui `python -m coach.ingest.garmin` 3 volte di fila a 1 minuto di distanza. Verifica:
- N° righe `activities` non aumenta dopo la prima
- N° righe `daily_wellness` non aumenta dopo la prima
- `health.last_success_at` viene aggiornato tre volte
- Nessuna duplicazione

### 2.3 — Test ordine workflow

L'`ingest.yml` ora include 3 step in sequenza:
1. Garmin sync
2. Compute daily metrics
3. Post-session analysis

Verifica:
- Se step 1 fallisce, step 2 e 3 partono comunque? Devono sapere che dati nuovi NON ci sono
- Se step 2 fallisce, step 3 ha dati incompleti
- Se step 3 fallisce (es. budget exhausted), step 1 e 2 sono comunque OK

### 2.4 — Output

Stessa struttura di Task 1.4. Documenta in `docs/ingest_resilience_audit_2026-05-09.md`.

## Task 3 — Audit resilienza coaching agent (Step 6 features)

### 3.1 — Test budget cap

**Scenario A — Hard cap raggiunto (Anthropic Console)**:
- Simula scenario in cui Anthropic restituisce 429 per "budget exceeded"
- Il sistema deve: NON andare in errore esplicito utente, fallback graceful, alert Telegram

**Scenario B — Soft cap raggiunto ($4.50)**:
- Simula `get_month_spend_usd() = $4.55`
- `LLMClient.call(prefer_model='sonnet', purpose='session_analysis')` → deve declassare a Haiku silenziosamente
- Verifica log

**Scenario C — Critical cap ($4.85)**:
- Simula `get_month_spend_usd() = $4.85`
- `purpose='session_analysis'` deve essere bloccato
- `purpose='emergency'` deve passare comunque

**Scenario D — Esaurimento durante sessione lunga**:
- Forza budget a $4.95 a metà weekly review
- Verifica che le chiamate successive falliscano graceful
- Alert utente con stato chiaro

### 3.2 — Test post-session analysis

**Scenario A — Sessione "normale"**: 
- Forza ingest di una sessione recente
- Verifica analisi generata, salvata su DB, mandata su Telegram
- Verifica log in api_usage

**Scenario B — Sessione senza pianificato corrispondente**:
- Allenamento "spontaneo" (es. partita a tennis che il sistema non sa cos'è)
- Comportamento atteso: analisi generica, NON deve fallire

**Scenario C — Sessione molto breve (< 5 min)**:
- Es. accidentalmente avviato e fermato il Garmin
- Comportamento atteso: skip analisi, log leggero, NO chiamata Claude

**Scenario D — Errore durante chiamata Claude**:
- Simula 503 da Anthropic
- Retry? Quanti? Dopo l'ultimo, cosa succede?

### 3.3 — Test modulazione mid-week

**Scenario A — Accept**:
- Forza scenario con HRV crash
- Verifica che la proposta arriva su Telegram con bottoni
- Click su "✅ Accetto"
- Verifica: `commit_plan_change` chiamato, gcal aggiornato, plan_modulations status='accepted'

**Scenario B — Reject**:
- Stesso ma click "❌ Rifiuto"
- Verifica: nessuna modifica, plan_modulations status='rejected'

**Scenario C — Discuto**:
- Click "💬 Discuto"
- Verifica messaggio "apri Claude Code"

**Scenario D — Doppio click**:
- Click "Accetto", poi di nuovo "Accetto"
- Verifica idempotenza, no doppia chiamata commit

**Scenario E — Click vecchio**:
- Modulation aperta 7 giorni fa, click sul bottone oggi
- Comportamento atteso: messaggio "questa proposta è scaduta"

### 3.4 — Test domande proactive

**Scenario A — Generazione**:
- Triggera manualmente il workflow `proactive_check_in.yml`
- Verifica che venga selezionata UNA domanda rilevante (non multiple)
- Verifica costo (~$0.001 con Haiku)

**Scenario B — Risposta utente**:
- Rispondi a una proactive question
- Verifica salvataggio in subjective_log con purpose='proactive_response'
- Verifica che la prossima analisi sessione la consideri

**Scenario C — Ignore**:
- Non rispondere alla proactive question per 3 giorni
- Comportamento atteso: il sistema non insiste, non blocca nulla

### 3.5 — Test pattern extraction

**Scenario A — Run normale**:
- Triggera manualmente il workflow `pattern-extraction.yml`
- Verifica che `docs/coaching_observations.md` venga aggiornato (con commit)
- Verifica che il commit author sia il bot, non utente
- Verifica costo

**Scenario B — Run senza dati**:
- Forza scenario con DB quasi vuoto
- Comportamento atteso: skip o produce output minimo, NO crash

**Scenario C — Pattern conflittuali**:
- Se l'estrazione produce un pattern in conflitto con uno esistente, cosa fa?
- Sovrascrive? Aggiunge entrambi? Concilia?

### 3.6 — Output

Documenta in `docs/coaching_resilience_audit_2026-05-09.md`.

## Task 4 — Audit security e privacy

### 4.1 — Test allow-list bot

- Manda messaggio al bot da un altro account Telegram → bot deve ignorare/rifiutare
- Verifica log: nessun side effect

### 4.2 — Test bearer MCP

- Chiama il MCP Worker senza Bearer → 401
- Chiama con Bearer sbagliato → 401
- Chiama con Bearer corretto ma manomessione del payload (es. SQL injection nei parametri tool) → input validation

### 4.3 — Test secret leak

- Verifica che NESSUN secret sia loggato nei log GitHub Actions (cerca pattern tipo `Bearer ghp_`, `sk-ant-`, ecc.)
- Verifica che `.env` sia in `.gitignore`
- Verifica che i log dei Workers Cloudflare non logghino secret

### 4.4 — Test SQL injection sui parametri MCP

I tool MCP accettano parametri stringa (es. `sport`, `description`). Verifica che:
- Input con `'; DROP TABLE activities;--` venga sanitizzato dal client supabase (dovrebbe già)
- Input con caratteri non-ASCII (emoji, accenti) sia gestito

### 4.5 — Output

Documenta in `docs/security_audit_2026-05-09.md`.

## Task 5 — Suite di smoke test estesa

Estendi `scripts/smoke_test.py` per includere TUTTI i check critici trovati durante l'audit. Output finale del comando deve essere:
=== SMOKE TEST SISTEMA ===
🔌 Connettività
✓ Supabase
✓ MCP Worker (con bearer)
✓ Telegram API
✓ Garmin Connect (login)
✓ Anthropic API
🗄️ Schema DB
✓ activities
✓ daily_wellness (con sleep_score, vo2max_run)
✓ daily_metrics (con garmin_acute_load)
✓ planned_sessions (con calendar_event_id)
✓ subjective_log
✓ api_usage
✓ session_analyses
✓ plan_modulations
✓ health
✓ physiology_zones
✓ races
✓ mesocycles
⏰ Freshness
✓ ingest < 6h
✓ briefing < 26h
✓ analytics < 6h
✓ dr_snapshot < 30h
💰 Budget
✓ Tabella api_usage accessibile
✓ Spesa mese < $5
✓ Pricing table aggiornato
🔧 Workflows
✓ ingest.yml
✓ morning-briefing.yml
✓ debrief-reminder.yml
✓ weekly-review.yml
✓ watchdog.yml
✓ dr-snapshot.yml
✓ keepalive.yml
✓ proactive-check-in.yml
✓ pattern-extraction.yml
🎯 Tools MCP
✓ get_recent_metrics
✓ get_planned_session
✓ get_activity_history
✓ query_subjective_log
✓ propose_plan_change
✓ commit_plan_change
✓ force_garmin_sync
📚 Skills
✓ 11+ skill files presenti
✅ TUTTI I CHECK VERDI

## Task 6 — Fix dei bug P0 e P1 trovati

Per ogni bug P0 o P1 trovato:
- Fai diagnosi root cause
- Implementa fix
- Aggiungi test che riproduca il bug
- Documenta nel commit

NON committare fix per P2/P3. Documentali come GitHub Issues invece.

## Task 7 — Documenta procedure di triage

Crea `docs/TROUBLESHOOTING.md` con procedure per:

1. **Bot Telegram non risponde**: come diagnosticare (log Cloudflare, getWebhookInfo, stato secret)
2. **Brief mattutino non arriva**: log workflow, edge case "no planned session", timezone bug
3. **Budget API esaurito**: verifica console Anthropic, pulizia plan_modulations vecchie, scope sessioni Coach
4. **Workflow GitHub Actions fallisce**: triage step-by-step (requirements.txt, secret, runner availability)
5. **Modulation in pending da > 24h**: come chiudere manualmente
6. **Sessione analyses vecchie da pulire**: query manuale di pulizia
7. **Pattern observations duplicati**: revisione manuale di docs/coaching_observations.md

Stile: ogni procedura inizia con sintomo osservato dall'utente, poi diagnosi, poi fix con comandi precisi.

## Task 8 — Session log e cleanup

1. Crea `docs/session_log_2026-05-09.md` con:
   - Lista bug trovati per gravità
   - Bug fixati in questa sessione
   - Bug aperti come issue
   - Test aggiunti
   - Documenti creati

2. Verifica `git status` finale: nessun file untracked dovuto a errori

3. Commit pushato:
```bash
git add -A
git commit -m "Step 6.5: resilience audit, P0/P1 fixes, troubleshooting playbook"
git push
```

## Vincoli e preferenze

- **Budget API per i test**: NON usare più di $0.50 totali per i test in questa sessione. Usa principalmente Haiku per simulazioni
- **Non rompere il prod**: i fix P0/P1 vanno applicati solo se ben testati. In caso di dubbio, documenta come issue e lascia all'utente decidere
- **Stile**: italiano "tu", asciutto, lista numerata per procedure
- **Working style utente**: zip deliverables completi, root cause analysis, rimozione legacy, max 3 tab UI

## Cosa fare se la sessione è troppo lunga

Priorità (dal più importante al meno):

1. Task 1 (audit bot) + Task 1.3 (fix debrief mattutino fallito stamattina)
2. Task 2 (audit ingest)
3. Task 3 (audit coaching)
4. Task 5 (smoke test esteso)
5. Task 7 (troubleshooting playbook)
6. Task 4 (security)
7. Task 6 (fix P0/P1)

Se non chiudi tutto, fai bene 1-3 e rimanda 4-7 a sessione successiva. Documenta cosa non hai fatto in `docs/session_log_2026-05-09.md`.

## Output atteso

A fine sessione, l'utente deve avere:

1. ✅ `docs/telegram_bot_audit_2026-05-09.md`
2. ✅ `docs/ingest_resilience_audit_2026-05-09.md`
3. ✅ `docs/coaching_resilience_audit_2026-05-09.md`
4. ✅ `docs/security_audit_2026-05-09.md`
5. ✅ `docs/TROUBLESHOOTING.md`
6. ✅ `docs/session_log_2026-05-09.md`
7. ✅ `scripts/smoke_test.py` esteso e funzionante (output con tutti ✓)
8. ✅ Bug stamattina (debrief fallito) FIXATO con root cause
9. ✅ Tutti i P0/P1 fixati o documentati come issue
10. ✅ Commit pushato con messaggio descrittivo
11. ✅ Sintesi a console: bug trovati, bug fixati, test aggiunti, prossimi passi

Ricorda: l'obiettivo è che l'utente possa dormire la notte sapendo che il sistema regge, non che abbia un report di bug. Quindi pesa qualità del fix > quantità di bug trovati.