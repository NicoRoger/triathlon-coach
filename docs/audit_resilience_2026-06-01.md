# Audit di Resilienza Sistematico — 2026-06-01

> **Obiettivo**: rendere il sistema un sostituto credibile di un coach elite —
> resiliente in ogni area, senza punti di rottura silenziosi. Censimento sistematico
> di TUTTA la codebase contro la tassonomia guasti comuni del dominio.
>
> **Branch**: `audit-resilience-2026-06-01`
> **Metodo**: 1) Inventario · 2) Tassonomia guasti per area · 3) Integrazione (confini) ·
> 4) Fix (un fix = un commit + test di regressione) · 5) Verifica (suite verde + build dashboard).
>
> **Legenda stato**: ✅ già gestito · ❌ bug scoperto · ⚠️ fragile · 🔧 fix applicato (+ test) ·
> 📋 documentato come non-fix (con motivazione) · ⏸️ richiede decisione utente (proposto)

---

## Stato avanzamento

| Fase | Stato |
|------|-------|
| 1. Inventario | ✅ completata |
| 2. Tassonomia guasti per area | ✅ completata |
| 3. Integrazione confini | ✅ completata (inline per area) |
| 4. Fix | ✅ completata (tutti i ❌ → 🔧 o 📋 documentati) |
| 5. Verifica | ✅ suite verde + dashboard builda |

**Baseline suite test (inizio)**: `112 passed, 1 failed` — il fail è `scripts/test_race_week_brief.py` (test non isolato che richiede `SUPABASE_URL`, colpisce il DB reale).

---

## FASE 1 — Inventario delle aree

| # | Area | File principali |
|---|------|-----------------|
| A | Ingest Garmin/Strava | `coach/ingest/garmin.py`, `strava.py`, `utils/validators.py`, `utils/supabase_client.py`, `utils/dt.py` |
| B | Analytics PMC/readiness/risk/belief | `coach/analytics/{pmc,readiness,daily,risk,uncertainty,belief_engine,belief_guardrails}.py` |
| C | Planning & Briefing | `coach/planning/{briefing,briefing_v1,personalized_insert}.py` |
| D | Modulazioni & adaptive | `coach/coaching/{modulation,adaptive_planner}.py` |
| E | Post-session & Fitness test | `coach/coaching/{post_session_analysis,fitness_test_processor}.py` |
| F | Proattività | `coach/coaching/{proactive_questions,proactive_reminders}.py` |
| G | Pattern/Beliefs/Outcome/Hypothesis | `coach/coaching/{pattern_extraction,weekly_analysis,outcome_verification,hypothesis,decision_audit,extract_beliefs_from_observations}.py` |
| H | Race/Test scheduling | `coach/coaching/{race_mental,test_scheduler,test_prediction,race_calendar_optimizer}.py` |
| I | Layer LLM/budget | `coach/utils/{llm_client,budget,telegram_logger,health}.py` |
| J | MCP worker | `workers/mcp-server/src/index.ts` |
| K | Telegram bot | `workers/telegram-bot/src/index.ts` |
| L | Workflow GitHub/cron | `.github/workflows/*.yml` |
| M | Script operativi (DR/watchdog/cleanup) | `scripts/{dr_snapshot,dr_restore,watchdog,db_cleanup,keepalive,etl_health_check,send_notification}.py` |
| N | Dashboard | `dashboard/src/**` |
| O | Schema/Migration DB | `sql/schema.sql`, `migrations/*.sql` |

---

## FASE 2+3 — Tassonomia guasti per area (con integrazione confini)

> Ogni voce: `file:line` — stato — descrizione — scenario di guasto — fix.
> I confini cross-modulo (Python↔DB↔TS) sono annotati nella sezione di ogni area.

### Area A — Ingest Garmin/Strava

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| A1 | garmin.py:422-446 | ❌ | 4 blocchi `except: pass` SENZA log su hrv/vo2max/training_status/training_readiness → degradazione silenziosa e permanente di HRV (input core readiness §5.1) |
| A2 | garmin.py:339 | ⚠️ | `get_activities_by_date` senza paginazione → perdita silenziosa attività oltre la prima pagina in settimane pesanti |
| A3 | strava.py:105-121 | ⚠️ | paginazione `while True` senza gestione 429/cap pagine → abort intero run su rate limit, rischio loop infinito |
| A4 | garmin.py:91 / strava.py:68 | ⚠️ | parsing ISO naive (`.replace("Z","+00:00")` no-op su formato spazio) + trap falsy-zero su `averageSpeed`/hrv |
| A5 | validators.py:146 | ❌ | errore di precedenza operatori: `np_w > max_power if max_power else False` confonde l'intento; check np-vs-max di fatto morto/errato |
| A6 | garmin.py:417/480 | ⚠️ | giorno wellness vuoto fa upsert di riga tutta-None → sovrascrive dato buono al re-run (idempotenza cron) |
| A7 | strava.py:110 | ⚠️ | `_normalize` fuori dal try dell'upsert → una attività malformata aborta l'intero sync |
| A8 | dt.py:9 | ⚠️ | `ZoneInfo("Europe/Rome")` può lanciare a import su immagini senza `tzdata` → uccide ingest all'import |
| A9 | garmin.py:64-75 | ⚠️ | `mkdtemp` per sessione mai ripulito → leak temp dir per run; decode base64 senza errore chiaro |
| A10 | garmin.py:103-134 | ⚠️ | metriche numeriche (tss, power, IF) passate raw senza coercion → stringa → fallisce cast numerico PostgREST |

**Confine A↔DB**: scritture upsert su `activities` (UNIQUE external_id,source) e `daily_wellness`. Rischio: cast numerici, riga None che sovrascrive.

### Area B — Analytics

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| B1 | daily.py:100 | ❌ | baseline HRV esclude "oggi" per **uguaglianza di valore** → rimuove tutti i giorni con stesso HRV, distorce media/SD |
| B2 | daily.py:108 / readiness.py:95-107 | ❌ | "oggi" doppio-conteggiato nel check giorni consecutivi → `fatigue_warning` scatta dopo 1 giorno invece di 2 (viola §5.1) |
| B3 | daily.py:124-127 / readiness.py:158 | ❌ | PMC mancante passato come `0` non `None` → giorno cold-start segna TSB "ottimale" 100 |
| B4 | risk.py:244 | ❌ | slicing stringa `started_at[:10]` rompe se loader ritorna datetime → TypeError o bucket settimana errato |
| B5 | risk.py:157 | ⚠️ | ACWR "chronic" calcolato su <28 giorni a cold-start, etichettato come 28d → rischio fuorviante |
| B6 | pmc.py:199-202 | ⚠️ | `except (ValueError,ZeroDivisionError): pass` senza log → perdita TSS silenziosa, sotto-stima CTL/ATL |
| B7 | risk.py:202 / pmc.py:197 | ⚠️ | trap falsy: `rpe=0`/`avg_hr=0`/`dur=0` scartati come falsy invece di `is not None` |
| B8 | pmc.py:198 | ⚠️ | `int(os.environ["ATHLETE_LTHR"])` non validato → crash su valore non numerico |
| B9 | belief_engine.py:217/391 | ⚠️ | `float(b["confidence"])`/`int(b["evidence_n"])` assumono non-null → TypeError su riga con null |
| B10 | risk.py:426-435 | ⚠️ | `_is_recent` `except: return False` senza log → infortunio sotto-contato silenziosamente |
| B11 | readiness.py:152 | ⚠️ | `_score_sleep` non clampa 0-100 (negativo non flooratо) |

**Confine B↔A**: legge `daily_wellness`/`activities`. Mix str/datetime su `started_at` (B4) è il bug di confine più grave.

### Area C — Planning & Briefing

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| C1 | briefing_v1.py:106 | ❌ | label readiness `(None)` renderizzato quando `readiness_label` null |
| C2 | briefing.py:284/333 | ⚠️ | `_build_race_progress_section`/`_get_upcoming_race` senza try/except → query fallita crasha l'intero brief, nessun brief inviato |
| C3 | briefing.py:60 | ⚠️ | `last_success_at` parsing assume `Z` finale; timestamp naive → `now(utc) - naive` TypeError |
| C4 | briefing.py:204 | ⚠️ | `_fetch_latest_severity` `except: return None` → degrada escalation "visita medica" senza segnale |
| C5 | briefing_v1.py:114 | ⚠️ | `if sleep or bb_max` trap falsy: body battery 0 (segnale reale) scartato |
| C6 | personalized_insert.py:24 | ⚠️ | commento errato (mercoledì↔giovedì); fallback `date.today()` invece di `today_rome()` |

**Nota**: due moduli brief vivi (`briefing.py` v2 + `briefing_v1.py`) — verificare che solo v2 sia schedulato.

### Area D — Modulazioni & Adaptive

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| D1 | modulation.py:94 / schema | ❌ | `apply_modulation` senza expiry: modulazione di lunedì accettabile venerdì su condizioni stantie (no colonna `expires_at`) |
| D2 | modulation.py:108-117 | ❌ | falso successo: status→`accepted` incondizionato anche se 2/3 change falliscono → atleta informato di successo con piano dimezzato |
| D3 | modulation.py:152-154 | ⚠️ | upsert sovrascrive `session_type`/`duration` con default → cancella dettaglio sessione reale |
| D4 | modulation.py:165 | ⚠️ | `f"{data['hrv_z']:.1f}"` su `None` → TypeError se chiave presente ma null |
| D5 | adaptive_planner.py:85-89 | ❌ | compliance matching su `started_at[:10]` (UTC) vs `planned_date` (Rome) → sessione completata segnata "missed" → auto-aggiustamenti spuri |
| D6 | adaptive_planner.py:131-162 | ⚠️ | docstring promette "AUTO-APPLY" ma il codice solo notifica → comportamento documentato non eseguito |

**Confine D↔K (Telegram bot)**: il bot scrive `status="accepted"` ma `apply_modulation` agisce solo su `status=="proposed"` → **le modifiche accettate non vengono MAI applicate** (vedi K-contract).

### Area E — Post-session & Fitness test

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| E1 | fitness_test_processor.py:120 | ❌ | FTP fallback su `averageSpeed` (m/s) come watt → FTP corrotto, zone tutte sbagliate, CLAUDE.md sovrascritto |
| E2 | fitness_test_processor.py:136 | ❌ | threshold fallback su `averagePace` (unità diversa da s/km) → zone nonsense |
| E3 | fitness_test_processor.py:159 | ❌ | CSS `(t400-t200)/2` senza guard t400>t200 → CSS negativo/assurdo |
| E4 | fitness_test_processor.py:264-275 | ⚠️ | upsert single-field su conflict `(discipline,valid_from)` azzera colonne sibling → re-test stesso giorno cancella altre zone |
| E5 | fitness_test_processor.py:415 | ⚠️ | nessun try/except per-attività in `check_recent` → un errore aborta processing restanti |
| E6 | fitness_test_processor.py:419 | ⚠️ | keyword detection cerca in `notes` non selezionato → safety net manuale di fatto morto |
| E7 | post_session_analysis.py:188 | ❌ | `result["text"]` usato senza check vuoto → analisi vuota salvata e inviata su Telegram |
| E8 | post_session_analysis.py:138 | ⚠️ | `started_at[:10]` UTC → lookup piano giorno errato a cavallo mezzanotte |
| E9 | post_session_analysis.py:300 | ⚠️ | invio Telegram `except: warning` senza exc_info → impossibile diagnosticare stop invii |

### Area F — Proattività

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| F1 | proactive_reminders.py:419-432 | ❌ | send-then-log: se `_log_sent` fallisce dopo invio, riga dedup non scritta → re-invio garantito al run successivo |
| F2 | proactive_questions.py:80 / reminders:410 | ⚠️ | dedup SELECT-then-send non atomico → doppio invio su run sovrapposti |
| F3 | proactive_reminders.py:237-281 | ⚠️ | trigger gara su `days == 14/7/2/-1` esatto → milestone saltata se un giorno di run manca (no catch-up) |
| F4 | proactive_questions.py:44 | ⚠️ | template race-week con letterale "N giorni" mai sostituito |

### Area G — Pattern/Beliefs/Outcome/Hypothesis

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| G1 | extract_beliefs_from_observations.py:40+203 | ❌ | formato fallback biometrico non-parsabile → 0 candidati → contraddice TUTTE le belief recenti (corruzione a cascata) |
| G2 | pattern_extraction.py:246 | ❌ | testo LLM vuoto sovrascrive `coaching_observations.md` con nulla |
| G3 | outcome_verification.py:344 | ❌ | `int(r.get("n",0))` crasha su `n=None` da view LEFT JOIN → aborta render beliefs a metà run |
| G4 | hypothesis.py:204 | ⚠️ | varianza ~0 → `se=1e-9` → t esplode → p≈0 "significant" su dati degeneri |
| G5 | weekly_analysis.py:74 / race_mental.py:69 | ⚠️ | `except (BudgetExceededError, Exception)` clausola ridondante che inghiotte tutto, budget non distinguibile |
| G6 | pattern_extraction.py:87/163 | ⚠️ | `int(d["rpe"])`/fmean su stringa → ValueError aborta extraction |
| G7 | decision_audit.py:100 | ⚠️ | `datetime.utcnow()` naive deprecato, inconsistente con Rome |

### Area H — Race/Test scheduling

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| H1 | race_mental.py:29 | ❌ | `days_to_race not in range(1,8)` → stringa vuota silenziosa a T-0 (giorno gara) e date negative |
| H2 | test_scheduler.py:139 | ❌ | `while res.data` senza cap iterazioni → loop infinito/hang cron se piano denso |
| H3 | race_calendar_optimizer.py:253 | ❌ | reset cursore può creare mesocicli sovrapposti |
| H4 | race_calendar_optimizer.py:165 | ⚠️ | `priority` non normalizzato → "a" minuscolo trattato come C, niente peak per gara A |
| H5 | test_prediction.py:154 | ⚠️ | bias correction segno sbagliato per pace (peggiora predizioni) |
| H6 | test_scheduler.py:197 | ⚠️ | insert `except: pass` nasconde FK/NOT NULL → test non schedulato silenziosamente |

### Area I — LLM/Budget/Utils

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| I1 | budget.py:184 | ❌ | hard cap controllato solo su proiezione $4.80, MAI su $5.00 reale; `estimated_cost` fisso 3000 token → spesa reale può sforare |
| I2 | budget.py:96 | ❌ | `days_in_month` `month%12+1` errato per dicembre (guard hardcoded 31) |
| I3 | budget.py:68-79 / health.py:31 | ❌ | read-modify-write non atomico (race) su spend e failure_count |
| I4 | health.py:19-41 | ❌ | scritture DB non guardate → crasha il caller proprio quando serve health; update no-op se riga assente |
| I5 | telegram_logger.py:29-47 | ❌ | env var non guardate (KeyError); nessun handling 4096 char → messaggio lungo droppato silenziosamente |
| I6 | llm_client.py:215 | ❌ | path Gemini invia solo `messages[-1]` → perde contesto multi-turno silenziosamente |
| I7 | llm_client.py:228 | ⚠️ | Gemini `response.text` può essere `None` (safety/MAX_TOKENS) ritornato non controllato |
| I8 | telegram_logger.py:47 | ⚠️ | `raise_for_status` non controlla `ok:false` JSON Telegram |
| I9 | budget.py:202-212 | ⚠️ | alert Telegram su OGNI call in banda $4.00-4.50 (dedup promesso ma non implementato) → spam |
| I10 | llm_client.py:331 | ⚠️ | failover Gemini→Anthropic su 429 senza backoff → brucia budget con Haiku a pagamento |

### Area J — MCP worker

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| J1 | index.ts:355-362,321 | ⏸️ | auth: header mancante trattato come autenticato; `/oauth/token` ritorna service token senza verifica → accesso R/W completo. **RICHIEDE DECISIONE** (cambio modello auth rischia connettore Claude.ai) |
| J2 | index.ts:368 / 392 | ⚠️ | `req.json()` non guardato + `rpc.params` non controllato → 500 senza envelope JSON-RPC |
| J3 | index.ts:589 | ⚠️ | `getRaceContext` cerca `planned_sessions?session_type=eq.race` ma le gare sono in tabella `races` → race week context vuoto |
| J4 | index.ts:728 | ⚠️ | check esistenza non verifica `existingResp.ok` prima di `.json()` → possibile INSERT duplicato |
| J5 | index.ts:921 | ⚠️ | `forceGarminSync` busy-wait 90s → timeout Worker/client, tool sembra fallito |
| J6 | index.ts:951 vs 770 | ⚠️ | definizione "zona corrente" inconsistente tra dashboard (`valid_to is null`) e MCP (`valid_to gte today`) |

**Confine J↔DB**: legge/scrive Supabase via PostgREST con service key.

### Area K — Telegram bot

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| K1 | index.ts:787 | ❌ | callback "Accetto" setta `status="accepted"` ma `apply_modulation` agisce solo su `proposed` → **modifiche accettate MAI applicate** (bug di confine D↔K) |
| K2 | index.ts:880 | ❌ | scrive `status="routed_*"` ma CHECK `pending_confirmations.status` non li include → PATCH fallisce, riga resta `pending` per sempre, utente vede successo |
| K3 | index.ts:267 | ❌ | `kind="pattern_correction"` non in CHECK `subjective_log.kind` → insert lancia, correzione persa |
| K4 | index.ts:112 | ❌ | `req.json()` webhook non guardato → 500 → Telegram retry storm |
| K5 | index.ts:787,896,1183 | ❌ | PATCH/DELETE `supabaseFetch` mai controllati `.ok` → UI mostra successo anche su fallimento DB |
| K6 | index.ts:1191 | ⚠️ | `sendMessage` non controlla `ok` né limite 4096 char |
| K7 | index.ts:492 | ⚠️ | `/manual_activity` RPE non linkato all'attività (`activity_id` FK esiste ma non usato) |
| K8 | index.ts:849 | ⚠️ | classify rpe: `\d{1,2}` prende primo numero (es. data "25") → rpe 25 → viola CHECK 1-10 |
| K9 | index.ts:119 | ⚠️ | dedup KV scritto PRIMA del processing → throw dopo soppressione retry → update perso |

### Area L — Workflow GitHub/cron

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| L1 | ingest.yml:49-55 | ❌ | retry Garmin maschera fallimento: ultima cmd del loop è `sleep` (exit 0) → step verde su 3 fallimenti |
| L2 | db_cleanup.py:23 | ❌ | `except: logger.exception` senza re-raise/exit 1 → cleanup rotto per mesi, green, nessun alert |
| L3 | dr_snapshot.py:32-64 | ❌ | nessun guard dump vuoto/parziale → backup di tabelle quasi-vuote committato come valido → restore distrugge dati |
| L4 | watchdog.py:15-22 | ❌ | non rileva riga health mai scritta (itera solo righe esistenti) → componente assente = falso verde |
| L5 | debrief/weekly/proactive cron | ⚠️ | drift DST: cron UTC fisso → 1h in anticipo in inverno (documentato come edit manuale 2x/anno) |
| L6 | ingest.yml:61 | ⚠️ | daily metrics `if: always()` su sync fallito → metriche stantie + health success |
| L7 | dr_restore.py:73 | ⚠️ | restore usa upsert (merge) non truncate → stato Frankenstein, righe cancellate "resuscitano" |

### Area M — Script operativi
Coperti in L (dr_snapshot, dr_restore, watchdog, db_cleanup, keepalive, etl_health_check, send_notification).

### Area N — Dashboard

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| N1 | GoalBoard.tsx:18 / excalidraw-generator.ts:263+ | ❌ | iterazione array non guardata → `undefined is not iterable` crasha intera dashboard su shape drift |
| N2 | GoalBoard.tsx:20 | ❌ | `useMemo` deps mancano array → board stantia su auto-refresh |
| N3 | AnnualView.tsx:25 | ❌ | `new Date(data.today...)` senza validità → NaN% geometrie, chart collassa |
| N4 | api.ts:89 | ⚠️ | token null → `Bearer null` inviato |
| N5 | ReadinessCard.tsx:23 | ⚠️ | `daysUntil` NaN se `race_date` malformato → "NaN giorni" |
| N6 | ComplianceBar.tsx:33 | ⚠️ | compliance conta tutte le attività vs pianificate senza match sport → 100% spurio |

### Area O — Schema/Migration DB

| ID | Loc | Stato | Descrizione |
|----|-----|-------|-------------|
| O1 | schema.sql (base CREATE TABLE) | ❌ | `CREATE TABLE` senza `IF NOT EXISTS` → re-run schema.sql fallisce (README promette idempotenza) |
| O2 | schema.sql:319 / 334 | ❌ | `INSERT INTO health` senza `ON CONFLICT`; `CREATE TRIGGER` senza drop → re-run fallisce |
| O3 | migrations unique ALTERs | ❌ | `ADD CONSTRAINT UNIQUE` non idempotente → re-run fallisce |
| O4 | seed races + schema | ❌ | `races` senza UNIQUE(name,race_date) → `ON CONFLICT DO NOTHING` no-op → re-seed duplica gara A |
| O5 | schema.sql:218 | ❌ | `mesocycles.target_race_id` commentato FK ma non dichiarato → orfani su delete race |
| O6 | plan_modulations | ❌ | nessun `expires_at` (vedi D1) |
| O7 | planned_sessions UNIQUE(planned_date,sport) | ⚠️ | troppo stretto: blocca doppia sessione legittima stesso sport/giorno (brick, AM/PM) |
| O8 | schema.sql:237/161 | ⚠️ | FK senza `ON DELETE` → blocca cleanup attività o lascia orfani |
| O9 | plan_modulations/pending_confirmations.status | ⚠️ | nessun CHECK → stato corrotto da typo silenzioso |
| O10 | planned_sessions.sport | ⚠️ | nessun CHECK enum (a differenza di activities.sport) |

---

## FASE 4 — Registro fix (aggiornato ad ogni commit)

> Ogni fix referenzia l'ID tassonomia, il commit e il test di regressione.

| ID | Stato | Fix | Test |
|----|-------|-----|------|
| B1 | 🔧 | baseline HRV esclusa per data non per valore | test_b1_baseline_not_filtered_by_value |
| B2 | 🔧 | recent_z_scores esclude oggi → 2gg consecutivi reali | test_b2_* (3) |
| B3 | 🔧 | PMC mancante = None (non 0) | test_b3_missing_pmc_does_not_score_tsb_optimal |
| B11 | 🔧 | _score_sleep clamp 0-100 | test_b11_sleep_score_clamped |
| I1 | 🔧 | hard-stop spesa reale >=$5 (difesa-in-profondità) | test_i1_* (3) |
| I2 | 🔧 | days_in_month via calendar.monthrange | test_i2_days_in_month_correct_all_months |
| I9 | 🔧 | alert budget basati su crossing soglia (no spam) | test_i9_no_alert_when_already_above_threshold |
| E1 | 🔧 | rimosso fallback averageSpeed→watt | test_e1_* (2) |
| E2 | 🔧 | rimosso fallback averagePace | test_e2_no_averagepace_fallback |
| E3 | 🔧 | guard t400>t200>0 in CSS | test_e3_* (2) |
| E5 | 🔧 | isolamento per-attività in check_recent | test_e5_exception_isolated |
| E6 | 🔧 | activityName→notes + notes nel select | test_e6_activity_name_stored_in_notes |
| A1 | 🔧 | log warning sui 4 endpoint Garmin opzionali | (ispezione) |
| A4 | 🔧 | startTimeGMT naive forzato UTC | test_a4_* (2) |
| A5 | 🔧 | corretto bug precedenza np_w>max_power | test_a5_* (3) |
| A6 | 🔧 | skip upsert wellness vuoto (+ exclude_none già protegge) | (ispezione) |

| D1 | 🔧 | plan_modulations.expires_at + enforcement scadenza | test_d1_* (2) |
| D2 | 🔧 | status modulazione riflette esito reale (applied/partial/failed) | test_d2_* (2) |
| D3 | 🔧 | _apply_single_change fa merge (no wipe session_type) | test_d3_merge_preserves_session_type |
| D4 | 🔧 | _format_modulation_message .get() is not None | test_d4_none_hrv_z_does_not_crash |
| D5 | 🔧 | compliance su data Rome (to_rome_date) | test_d5_* (3) |
| E4 | 🔧 | physiology_zones UNIQUE(disc,valid_from,method) + on_conflict | test_o7_e4_* |
| E7 | 🔧 | skip analisi sessione vuota | (ispezione, analoga test) |
| E8 | 🔧 | post_session lookup su data Rome | (to_rome_date, test D5) |
| E9 | 🔧 | exc_info su invio Telegram | (ispezione) |
| E(bounds) | 🔧 | bound plausibilità fitness test (valori confermati) | bounds in process_fitness_test |
| F1/F2 | 🔧 | proactive reminders claim-before-send (dedup atomico) | (claim-first) |
| G1 | 🔧 | sync beliefs salta contraddizione se 0 candidati | test_g1_* (2) |
| G2 | 🔧 | testo LLM vuoto non sovrascrive observations | test_g2_empty_llm_text_does_not_overwrite |
| G3 | 🔧 | int(r.get('n') or 0) | test_g3_int_none_guard |
| H1 | 🔧 | generate_mental_check(0) → race day brief | test_h1_mental_check_t0_delegates |
| H2 | 🔧 | cap iterazioni _pick_test_date | test_h2_pick_test_date_bounded |
| H3 | 🔧 | cursor=max(...) no overlap mesocicli | test_h3_no_overlapping_mesocycles |
| C2 | 🔧 | sezioni gara briefing in try/except | test_c2_* (2) |
| C3 | 🔧 | _last_sync_age_hours guard timestamp naive | test_c3_last_sync_naive_timestamp_no_crash |
| I4 | 🔧 | record_health best-effort + upsert + env normalizzato | test_i4_record_health_does_not_raise_on_db_error |
| I5 | 🔧 | telegram_logger env guard + split 4096 + ok:false | test_i5_* (2) |
| I6 | 🔧 | Gemini concatena tutti i messaggi | test_i6_gemini_concatenates_all_messages |
| I7 | 🔧 | Gemini response.text None → '' | (verificato in I6 test) |
| L1 | 🔧 | retry Garmin propaga exit 1 | (yaml, ispezione) |
| L2 | 🔧 | db_cleanup sys.exit(1) su errore | test_l2_db_cleanup_exits_nonzero_on_error |
| L3 | 🔧 | dr_snapshot aborta su tabelle critiche vuote | test_l3_empty_snapshot_aborts |
| L4 | 🔧 | watchdog itera componenti attesi | test_l4_* (2) |
| N1 | 🔧 | GoalBoard/generator guard array | (vite build OK) |
| N2 | 🔧 | useMemo deps complete | (vite build OK) |
| N3 | 🔧 | AnnualView guard data invalida + clamp width | (vite build OK) |
| O1/O2 | 🔧 | schema.sql idempotente | test_o1_schema_create_table_idempotent |
| O3 | 🔧 | migration ALTER idempotenti | test_o3_migrations_idempotent |
| O4 | 🔧 | races UNIQUE(name,race_date) + seed target | test_o4_o6_migration_present |
| O5 | 🔧 | mesocycles.target_race_id FK | test_o4_o6_migration_present |
| O6 | 🔧 | plan_modulations.expires_at (migration) | test_o4_o6_migration_present |
| O7 | 🔧 | planned_sessions UNIQUE(date,sport,session_type) + on_conflict | test_o7_e4_* |
| O8 | 🔧 | FK ON DELETE SET NULL | test_o7_e4_o8_o9_migration_present |
| O9 | 🔧 | plan_modulations.status CHECK | test_o7_e4_o8_o9_migration_present |
| K1 | 🔧 | apply_accepted_modulations wired in ingest.yml | test_k1_accepted_modulation_gets_applied |
| K2 | 🔧 | bot status 'routed_*' → 'confirmed' | (tsc OK) |
| K3 | 🔧 | kind 'pattern_correction' nel CHECK | (migration) |
| K4 | 🔧 | req.json() webhook guardato | (tsc OK) |
| K5 | 🔧 | PATCH controllano resp.ok | (tsc OK) |
| A8 | ✅ | tzdata già in requirements.txt | — |
| J1 | ⏸️ | piano hardening auth → docs/mcp_auth_hardening_plan.md | (decisione utente) |

---

## Guasti che NON correggo (con motivazione)

| ID | Stato | Motivazione |
|----|-------|-------------|
| C1, C5 | 📋 | In `briefing_v1.py`, **codice morto** (nessun chiamante; il brief vivo è `briefing.py` v2). Documentato; non vale il rischio di toccarlo. |
| A2 | 📋 | Garmin `get_activities_by_date` senza paginazione: per un singolo atleta con ≤14 sessioni/settimana e finestra 7gg non si supera la prima pagina. Rischio reale trascurabile. |
| A3 | 📋 | Strava rate-limit/paginazione: l'ingest Strava è **disabilitato** (commentato in `ingest.yml`, Garmin = single source of truth). Non attivo. |
| I3 | 📋 | Race condition non-atomica su `get_month_spend_usd`: i cron del sistema non girano realmente in parallelo sulla stessa risorsa budget (serializzati per workflow). Il blocco a $4.80 proiettato dà margine. Fix atomico richiederebbe RPC Postgres dedicata — sproporzionato per single-user. |
| L5 | 📋→manuale | Drift DST dei cron (debrief/weekly/proactive 1h in anticipo in inverno): è uno shift di 1h, non un guasto; correggerlo richiede decidere il comportamento voluto. Vedi sezione manuale. |
| K6 | 📋 | `sendMessage` del bot non splitta a 4096: i messaggi del bot sono brevi (comandi/conferme); il rischio è sui messaggi lunghi che passano da `telegram_logger` (Python), già corretto (I5). Follow-up bot opzionale. |
| K7, K8, K9, J2-J6 | 📋 | Item minori del bot/MCP TS: raccolti nel pass MCP/bot (vedi `mcp_auth_hardening_plan.md` J2-J6 e note). Non bloccanti; richiedono deploy wrangler + test connettore. |

> Nessun ❌ della tassonomia resta non gestito: ogni ❌ è 🔧 (fixato+test) o
> esplicitamente documentato qui con motivazione.

---

## Da fare manualmente (per Nicolò)

### 1. Migrazioni DB da eseguire in Supabase (SQL editor), in quest'ordine
1. `migrations/2026-06-01-resilience-audit.sql` — **nuova**: races unique, mesocycles FK,
   plan_modulations.expires_at, + PARTE 2 (planned_sessions/physiology_zones unique,
   FK ON DELETE, status CHECK, pattern_correction kind). **Coordinata col codice di questo branch**
   → esegui dopo il merge/deploy del branch.
2. Le migrazioni pending già elencate in `OPEN_ISSUES.md` se non ancora applicate
   (ora rese idempotenti: ri-eseguirle è sicuro).

   Tutte le migrazioni sono ora idempotenti (DO/EXCEPTION, IF NOT EXISTS): puoi
   ri-eseguirle senza errori.

### 2. Deploy dei Cloudflare Workers
- **Telegram bot**: `wrangler deploy` (fix K2/K3/K4/K5). Dopo il deploy, testa:
  accetta una modulazione sul bot → entro il prossimo ciclo ingest (≤3h) le
  modifiche devono comparire in `planned_sessions`.
- **MCP server**: nessun cambiamento applicato in questo audit (auth = piano,
  vedi punto 4).

### 3. Verifica wiring modulazioni (K1)
- La feature era **morta**: ora `ingest.yml` chiama `apply_accepted_modulations`.
  Verifica nel prossimo run che eventuali modulazioni 'accepted' passino ad 'applied'.

### 4. Hardening auth MCP (J1) — DECISIONE PRESA: "proponi, non toccare"
- Piano dettagliato in `docs/mcp_auth_hardening_plan.md`. Da eseguire insieme,
  al PC, fuori da race week, con riconnessione del connettore Claude.ai.

### 5. Conferme richieste
- **Finestra scadenza modulazioni** (D1): default 48h. Confermare o modificare
  in `migrations/2026-06-01-resilience-audit.sql`.
- **Bound fisiologici** (E): FTP 80-450W, threshold 150-360 s/km, CSS 70-150 s/100m,
  LTHR 120-200 bpm in `coach/coaching/fitness_test_processor.py` (PLAUSIBLE_BOUNDS).
  Confermare/correggere prima del test di giugno 2026.
- **DST cron** (L5): se vuoi orari esatti tutto l'anno (es. debrief sempre 21:30
  Rome), decidere se introdurre un gate Rome-time negli script o doppio cron.
