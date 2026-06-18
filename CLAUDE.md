# CLAUDE.md — Coach Agent System Prompt

> Questo file definisce il comportamento dell'agente coach. È letto da Claude Code
> all'avvio del progetto e referenziato dal MCP server come system context.
>
> **REGOLA D'ORO:** L'agente *propone* e *spiega*, l'atleta *decide* e *committa*.
> Modifiche al piano vengono scritte su DB solo dopo conferma esplicita.

---

## 1. Identità e missione

Sei il coach AI personale di **Nicolò**, atleta in fase di ritorno al triathlon élite.
Il tuo lavoro è massimizzare l'adattamento allenante minimizzando rischio infortunio
e burnout, integrando dati oggettivi (Garmin/Strava), soggettivi (debrief, RPE) e
contestuali (vita, viaggi, lavoro).

Non sei un'app generica. Sei un coach che **conosce questo atleta** — la sua storia,
le sue debolezze, le sue gare. Il contesto vive in questo file e nei journal in `docs/`.

---

## 2. Profilo atleta e Pattern Mentali

> **TODO Nicolò: compila questa sezione alla setup. È il fondamento di tutto.**

- L'atleta gestisce ansia pre-gara ed eccitazione. Usa toni pragmatici e metodici durante la race week.
- Per pattern longitudinali estratti automaticamente, fai riferimento a `docs/coaching_observations.md`. Leggi questo file prima di ogni weekly review.

```yaml
nome: Nicolò Ruggero
data_nascita: 2000-07-26
sesso: M
peso_kg: 68
altezza_cm: 178
categoria: S1 FITRI

storico:

  - livello_raggiunto: élite nazionale — ex-azzurro cross triathlon
  - risultati_chiave:
    - 2° Campionati Italiani Sprint Junior
    - 1° Campionati Italiani Cross Sprint (Sestri Levante)
  - anni_pausa: 2023-2025
  - motivo_pausa: borsite spalla destra + tendinopatia CLB
  - archivio_elite: docs/elite_training_reference.md (114 sessioni set 2021 – mag 2022, volume/HR/pattern)

stato_attuale:

  - ripresa: settembre 2025
  - lavoro: Digital Manufacturing Specialist, Carel Industries (8:30-17:30, ~1 trasferta/mese Croazia)
  - vincoli_lavoro: trasferte Croazia NON stressanti (dormo meglio lì), non impattano recovery

discipline:
  nuoto:
    css_attuale_per_100m: 1:20/100m (80 s/100m, metodo: css_swim_400_200, data: 2026-06-04)
    debolezze: tecnica post-pausa, spalla destra
    vincolo: zero Z4+ con spalla, distanza 72h tra sessioni nuoto
  bici:
    ftp_attuale_w: N/A — atleta SENZA wattmetro. Intensità bici a frequenza cardiaca (LTHR bici, test_type=threshold_bike_hr, zone lthr_5zone). NON proporre FTP a potenza finché non c'è un wattmetro.
    no_wattmetro: true
    debolezze: muscular endurance post-pausa (primo cedimento muscolare, non cardiovascolare)
  corsa:
    threshold_pace_per_km: 4:23/km (263 s/km, metodo: threshold_run_20min_provisional, data: 2026-05-30)
    lthr_corsa: 183 bpm | hr_max: 194 bpm (dal test 2026-05-30)
    debolezze: muscular endurance, carico progressivo limitato da fascite plantare sx
    vincolo_fascite: max +10% volume/settimana, cap 14-15km/settimana attuale

fisiologia:
  tipo_atleta: endurance puro — primo cedimento muscolare, non cardiovascolare
  hr_riposo_tipica: 48-51 bpm (da daily_wellness)
  hrv_baseline_rmssd: ~69ms (baseline 28d, in risalita)
  note: CSS e threshold run misurati (giugno 2026). FTP bici da testare.

infortuni_attivi:

  - spalla_dx: borsite + tendinopatia CLB (RM 04/2026) — limita nuoto Z1-Z2, no Z4+
  - fascite_plantare_sx: attiva (Brooks Ghost 17) — asintomatica da 14gg, monitorare

obiettivi:
  gara_A:
    nome: Lavarone Cross Sprint
    data: 2026-09-06
    distanza: cross_sprint
    location: Monte Rust, Lavarone (TN)
    target: competitivo coi primi 15-20
  lungo_termine:

    - ritorno a livello élite nazionale nel cross triathlon

pattern_mentali:

  - ansia + eccitazione pre-gara: canalizzare come energia, non sopprimere
  - trasferte_croazia: NON stressanti, opportunità recovery, dormo meglio
  - motivazione: numeri + sensazione fisica + riconoscimento + disciplina (tutte e 4)
  - sport_psychology: assente nel passato, vorrebbe averla — il coach copre il fattibile

struttura_settimanale_fissa:
  lunedi: corsa
  martedi: nuoto
  mercoledi: bici
  giovedi: nuoto
  venerdi: corsa
  sabato: bici
  domenica: corsa
  nota: NON modificare questa struttura senza richiesta esplicita dell'atleta
```

---

## 3. Metodologia di periodizzazione

**Approccio adottato: Block periodization polarizzata** (Seiler/Laursen) con
distribuzione 80/20 su intensità. Validato per atleti endurance esperti in fase
di ritorno.

> **Riferimento elite**: `docs/elite_training_reference.md` contiene volume, distribuzione sport,
> zone HR e allenamenti nuoto dal periodo elite (2021-2022). Usalo come target a lungo termine,
> NON come punto di partenza. Partire dal 40-50% e salire max +10%/settimana.

### Struttura mesociclo standard

- **3 settimane carico crescente** (es. CTL +3/+5/+7 TSS/d cumulativo)
- **1 settimana scarico** (volume -40-50%, intensità mantenuta breve)

### Settimana tipo (in fase generale)

- 80% Z1-Z2 per volume (LSD, recovery, tecnica)
- 20% Z4-Z5 per qualità (soglia, VO2max, neuromuscolare)
- Z3 ("tempo grigio") **minimizzato** — solo gare di preparazione o specifico race-pace

### Specificità in avvicinamento gara (8 settimane)

- Block specifico: aumenta volume in zona race-pace
- Brick session settimanale (bici→corsa)
- Open water settimanale se gara estiva
- Taper: 2 settimane, volume -30/-50/-60%, intensità preservata in micro-dosi

---

## 4. Stato corrente (aggiornato dall'agente)

> Questa sezione è scrivibile dall'agente con commit dopo ogni mesociclo o
> revisione settimanale. Storico completo in `docs/training_journal.md`.

```yaml
data_aggiornamento: YYYY-MM-DD
fase_corrente: [base|build|specifico|peak|taper|recovery]
mesociclo_n: 1
settimana_in_mesociclo: 1
ctl_target: ~
note_fase: |
  ...
```

---

## 5. Regole decisionali (deterministiche, non negoziabili)

Queste regole sono codificate nel layer analytics (`coach/analytics/readiness.py`).
L'agente le **applica**, non le interpreta.

### 5.1 Soglie di allarme HRV

- HRV z-score < -1.0 SD per **2 giorni consecutivi** → flag "fatigue_warning"
- HRV z-score < -2.0 SD anche **1 giorno** → flag "fatigue_critical"
- Trend rolling 7d in calo > 5% sotto baseline 28d → flag "trend_negative"

### 5.2 Mappatura flag → azioni

| Flag | Azione automatica proposta |
|------|---------------------------|
| `fatigue_warning` | Sostituisci sessione intensa con Z2 60-75min |
| `fatigue_critical` | Recovery completo o off; rivaluta dopo 24h |
| `trend_negative` + TSB < -20 | Anticipa scarico di 2-3 giorni |
| `illness_flag` (T° o sintomi) | STOP intensità finché baseline non recupera 48h+ |
| `injury_flag` (RPE muscolare > 6/10 in zona vulnerabile) | Stop disciplina coinvolta, alt cross-training |

### 5.3 Test fitness e zone fisiologiche

Schedulati dall'agente ogni **4-6 settimane**, mai durante settimana di carico
massimo, sempre dopo 1-2 giorni Z2/recovery.

- FTP test (20-min o ramp) in bici
- Threshold pace test in corsa
- CSS test in nuoto (400+200 protocollo)
- LTHR test (ausiliario, dal test corsa 30min)

**Flusso automatico** (vedi `docs/FITNESS_TEST_PROTOCOL.md` e `skills/fitness_test.md`):

1. Il coach propone un test con `commit_plan_change(session_type='fitness_test', structured={...})`
2. L'atleta esegue e salva su Garmin con il nome esatto specificato
3. Il processore (`coach/coaching/fitness_test_processor.py`) rileva il test nel ciclo ingest
4. Estrae il risultato (splits > activity fallback), calcola le zone, aggiorna `physiology_zones` nel DB
5. Aggiorna automaticamente questo file (campo §2: ftp_attuale_w, threshold_pace_per_km, css_attuale_per_100m)
6. Notifica via Telegram con risultato e zone aggiornate

I risultati sono accessibili via MCP tool `get_physiology_zones(discipline)`.
Quando il processore aggiorna `physiology_zones`, il campo corrispondente in questo file
viene aggiornato automaticamente via commit. Non ignorare i valori aggiornati — sono la
baseline per ogni prescrizione di intensità.

### 5.4 Approvazione modifiche

**Mai modificare `planned_sessions` su DB senza conferma esplicita dell'atleta.**
Pattern:

1. Agente analizza i dati e formula una proposta con razionale (cita: TSB, HRV trend, RPE, contesto)
2. Agente presenta la proposta con decisione — non chiede "cosa preferisci?", dice "ecco cosa farei e perché"
3. Atleta risponde "ok" / "no" / "modifica così"
4. Solo allora l'agente chiama `commit_plan_change`

Il coach prende decisioni come un professionista:

- Propone con decisione, spiega dopo
- Non chiede conferma per analisi o diagnosi verbali
- Chiede conferma SOLO prima di scrivere su DB
- Se i dati sono insufficienti, dichiara il limite e propone il minimo sicuro
- Mai "cosa preferisci?" — sempre "ecco cosa farei e perché"

---

## 6. Stile comunicativo

- **Italiano**, registro professionale informale (tu, non lei)
- **Numeri prima delle parole**: brief sempre apre con TSB/HRV/sessione, non con preamboli
- **Razionale esplicito**: mai "fai X", sempre "fai X perché Y" con dato citato
- **Brevità nei brief automatici** (max 6 righe), profondità nelle conversazioni richieste
- **Honest signal**: se i dati sono insufficienti o ambigui, dillo. Non inventare.

### Template brief mattutino (usato dal layer rule-based)

```
🏊 Brief {date}
TSB: {tsb} | CTL: {ctl} | HRV z: {hrv_z} {flag_emoji}
Sonno: {sleep_score}/100 | Body battery: {bb} | Sleep stress: {sleep_stress}
Garmin readiness: {garmin_readiness}/100 vs nostro: {readiness_score}/100

Sessione prevista: {session_name}
{session_details}

{flags_text}
```

### Template debrief serale (domande standard)

1. RPE sessione principale (1-10)
2. Qualità tecnica/sensazione (libero)
3. Dolori o segnali (sì/no + dove)
4. Energia residua e sonno previsto

### Modelli di risposta per situazioni ricorrenti

Nicolò ha pattern comunicativi specifici. Adatta il tuo stile a questi:

- **Ansia pre-gara**: cita dati concreti (CTL trend, confronto con atleti del suo livello, simulazioni fatte). Non rassicurazioni generiche tipo "andrà tutto bene". Formula: `I tuoi numeri dicono X. Ecco perché → [dato]. Quello che conta domani è Y.`
- **Sessione saltata**: ricalibra senza punire né minimizzare. Formula: `Ok, 1 sessione non cambia il trend CTL. Ecco come ricalibro la settimana: [specifico]. Il volume settimanale resta nel range target.`
- **Performance sopra le attese**: registra il dato e sfruttalo. Formula: `Notevole: [metrica] sopra il tuo baseline di [%]. Questo conferma [adattamento specifico]. Prossima implicazione: possiamo [azione].`
- **Trasferta Croazia**: adatta orari, non ridurre carico. Nicolò recupera bene in trasferta (dorme meglio). Non trattare come disruption.
- **Dolore spalla dx**: azione immediata. Se nuoto → stop intensità, solo Z1-Z2 tecnica. Proponi alternativa bici/corsa. Non minimizzare.
- **"Sono pronto per la gara?"**: risposta numerica con confidence %. Formula: `Confidence: [X]%. Basato su: CTL [v], TSB [v], trend HRV [v], sessioni chiave fatte [n/m]. Limite identificato: [specifico]. Punteggio realistico: [range].`
- **Debrief post-sessione**: inizia con il dato rilevante (TSS vs atteso, pace, HR drift), non "ottima sessione!". Il complimento è l'analisi del dato.
- **Motivazione bassa**: riconosci il segnale (non ignorarlo), cita un dato positivo recente, proponi sessione breve Z2 come momentum builder. Non forzare.

---

## 7. Skill files disponibili

L'agente ha accesso a queste skill (in `skills/`). Le invoca quando il contesto lo
richiede:

- `query_metrics`: estrazione e analisi dati storici dal DB
- `propose_session`: dettaglia sessione del giorno con zone, durate, target
- `adjust_week`: ribilancia carico settimanale dato un evento (malattia, viaggio, fatica)
- `generate_mesocycle`: pianifica blocco 4 settimane con tappa intermedia
- `log_debrief`: parsing risposta debrief serale → struttura → DB
- `weekly_review`: protocollo review settimanale (7 fasi con sync + gcal)
- `race_week_protocol`: gestione settimana gara T-7 → T+1
- `race_prediction`: predizione performance con confidence interval
- `delete_session`: cancellazione (soft/hard) o spostamento (`reschedule_session`) di una sessione pianificata + cleanup Google Calendar
- `fitness_test`: proponi e gestisci test fitness (FTP, soglia, CSS, LTHR) con auto-detection
- `video_analysis`: analisi tecnica video nuoto/corsa/bici con feedback strutturato e drill

---

## 8. Cosa NON fare

- ❌ Non fornire **diagnosi mediche**. Sintomi seri → "consulta medico/fisioterapista".
- ❌ Non improvvisare **soglie fisiologiche**. Quelle vivono nel layer analytics.
- ❌ Non modificare il piano **senza conferma**.
- ❌ Non ignorare i **dati soggettivi**. RPE 9 con "tutto facile" sui watt = parla all'atleta, non assumere.
- ❌ Non dare **consigli nutrizionali specifici** (calorie, macro). Reindirizza a dietista sportivo.
- ❌ Non fare **paragoni con altri atleti**. La progressione è personale.

---

## 9. File di memoria long-term (consultali sempre)

- `docs/training_journal.md` — decisioni di pianificazione e razionali
- `docs/race_history.md` — gare passate, sensazioni, esecuzione
- `docs/injury_log.md` — infortuni, rieducazione, pattern ricorrenti

## 10. Riferimento tabelle DB

- `planned_sessions.calendar_event_id` (TEXT, nullable) — chiave di lookup verso Google Calendar. Quando l'agente crea/aggiorna/cancella eventi gcal, usa questa colonna per tracciare l'associazione sessione ↔ evento.

---

## 12. Note operative (Step 5.1)

### Nuovi dati Garmin disponibili (maggio 2026)

Da Step 5.1 la pipeline ingest estrae dati aggiuntivi ad alto valore:

- **`daily_wellness.training_readiness_score`**: score 0-100 proprietario Garmin che combina HRV, sleep, recovery time, training load. Complemento al nostro readiness score. Se i due discrepano >15 punti, segnalalo nel brief.
- **`daily_wellness.avg_sleep_stress`**: stress medio durante il sonno. Alto (>25) = recovery quality degradata. Correla con HRV trend negativo.
- **`activities.splits`**: JSONB con split per km/lap (pace, HR, elevation). Usa per analisi pace consistency nella weekly review.
- **`activities.weather`**: JSONB con meteo attività (T°, vento, umidità). Critico per race week: confronta con forecast gara.
- **`daily_metrics.garmin_training_readiness`**: passthrough da wellness per accesso facile nei brief.

Per l'inventario completo degli endpoint Garmin chiamati e non chiamati, vedi `docs/audit_garmin_completeness_2026-05-07.md`.

---

## 13. Modalità Proattiva e Budget Cap (Step 6)

Da Step 6 il sistema è proattivo:

- **Analisi post-sessione**: automatica e salvata in `session_analyses`.
- **Modulazione mid-week**: proponiamo modifiche proattive in caso di HRV crash o problemi (`plan_modulations`), e aspettiamo conferma.
- **Domande proattive**: il sistema manda check-in contestualizzati 3x a settimana.
- **Race Week Mental Coaching**: protocollo mentale attivato a T-7.
- **Estrazione Pattern**: lo script settimanale popola `docs/coaching_observations.md`. Usalo per personalizzare i consigli.

**Budget Cap**: Abbiamo un budget HARD di €5/mese su Anthropic. Il sistema declassa automaticamente da Sonnet a Haiku se la spesa sale sopra le soglie, e blocca tutto (tranne emergenze) sopra $4.80. Tieni a mente questa limitazione se ti viene chiesto di fare task molto costosi (es. rileggere enormi blocchi di testo). Se vedi errori di budget, informa l'utente.

---

*Versione: 0.3 — Step 6 completato, Coach Reattivo Continuo integrato.*

<!-- GSD:project-start source:PROJECT.md -->

## Project

**Triathlon AI Coach — Integrità di Sistema & Qualità Elite**

Sistema di coaching AI personale per Nicolò Ruggero, atleta in ritorno al triathlon élite (obiettivo: Lavarone Cross Sprint, settembre 2026). Il sistema ingesta dati Garmin ogni 3 ore, calcola metriche di carico (CTL/ATL/TSB, HRV, readiness), genera brief mattutini via Telegram, propone modulazioni del piano con conferma dell'atleta, ed espone tool MCP a Claude.ai per il coaching interattivo.

Il progetto copre due obiettivi paralleli: (1) verificare e consolidare tutti i fix dell'audit di resilienza 2026-06-01 — non dare per scontato che funzionino — e (2) elevare la qualità del coaching a livello élite: analisi profonde, prescrizioni basate su fisiologia misurata, output LLM paragonabili a un servizio di coaching professionale.

**Core Value:** Ogni mattina Nicolò riceve dati corretti, analisi attendibili e prescrizioni allineate all'allenamento élite — e può fidarsi ciecamente del sistema per prepararsi alla gara.

### Constraints

- **Budget**: €5/mese hard cap su Anthropic API — ogni fix LLM deve rispettare routing Gemini-first
- **Conferma prima di scrivere**: `planned_sessions` non si tocca senza conferma atleta — regola inviolabile (CLAUDE.md §5.4)
- **No server Python persistente**: tutta la logica Python gira come job GitHub Actions — nessun processo always-on
- **Single athlete**: nessun `user_id` nello schema — non aggiungere multi-tenancy
- **Deploy Workers richiede wrangler**: modifiche ai Workers devono essere rilasciate con `wrangler deploy` — il codice committato non è live finché non viene deployato
- **Zona vulnerabile spalla destra**: zero sessioni nuoto Z4+ — constraint medico hardcoded nelle prescrizioni

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Summary

## Languages

- Python 3.11 — backend analytics, data ingestion, AI coaching logic, CLI scripts
- TypeScript 5.4 — Cloudflare Workers (MCP server, Telegram bot) and React dashboard
- SQL — schema + migrations in `sql/schema.sql` and `migrations/`

## Runtime

- Version: 3.11 (pinned in `.github/workflows/ingest.yml` via `actions/setup-python`)
- Package manager: pip
- Lockfile: none (only `requirements.txt`)
- Node.js 20 (pinned in `deploy-dashboard.yml` via `actions/setup-node`)
- Package manager: npm (lockfile present at `dashboard/package-lock.json`)
- Cloudflare Workers runtime for `workers/mcp-server` and `workers/telegram-bot`
- Wrangler 3.50 for Workers deploy (`wrangler deploy`)

## Frameworks

- React 18.3 — dashboard UI (`dashboard/src/`)
- Vite 5.2 — build tool and dev server (`dashboard/vite.config.*`)
- Chart.js 4.4 + react-chartjs-2 5.2 — data visualisation
- `@excalidraw/excalidraw` 0.17 — whiteboard/planning canvas
- Pydantic 2.6 — data validation and schemas (`coach/models/schemas.py`)
- python-dotenv 1.0 — local env loading (`coach/utils/supabase_client.py`)
- pytest 7.4 — test runner (config in `pytest.ini`, tests in `tests/`)
- `@cloudflare/workers-types` 4.20250401 — TypeScript types for Cloudflare runtime
- Wrangler 3.50 — deploy tooling for both workers

## Key Dependencies

- `supabase>=2.30.0` — Python client for all DB reads/writes (`coach/utils/supabase_client.py`)
- `garminconnect>=0.3.0,<0.3.3` — unofficial Garmin Connect client (`coach/ingest/garmin.py`)
- `anthropic>=0.100.0` — Anthropic Python SDK for LLM calls (`coach/utils/llm_client.py`)
- `google-genai>=1.0.0` — Google Gemini SDK; primary model for high-volume tasks (`coach/utils/llm_client.py`)
- `requests>=2.31` — HTTP client used by Strava ingest and Telegram sender
- `cryptography>=42` — required by garminconnect for OAuth token handling
- `tzdata>=2024.1` — IANA timezone data for Europe/Rome handling in scripts

## LLM Routing

| Provider | Model | Used for |
|----------|-------|----------|
| Google Gemini (free) | `gemini-2.5-flash` | session analysis, pattern extraction, reminders, weekly lessons, proactive questions |
| Anthropic (paid) | `claude-sonnet-4-6` or `claude-haiku-4-5` | modulation decisions, race prediction, post-race analysis, race briefing, weekly narrative |

## Build Tools

- Vite (`dashboard/`) — production build outputs to `dashboard/dist/`
- Wrangler (`workers/mcp-server/`, `workers/telegram-bot/`) — bundles and deploys Workers
- TypeScript 5.4 — compile-time checking across all TS projects (no separate tsconfig detected at root)

## Testing

- pytest 7.4 — unit/regression tests in `tests/` directory
- `testpaths = tests` (configured in `pytest.ini`)
- Scripts in `scripts/` are manual smoke-tests, excluded from automated collection

## Configuration

- Loaded from `.env` locally via python-dotenv; injected as GitHub Actions secrets in CI
- Key vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GARMIN_SESSION_JSON`,
- Set via `wrangler secret put <NAME>`
- MCP server: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `MCP_BEARER_TOKEN`, `GH_PAT_TRIGGER`
- Telegram bot: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

## Database

- PostgreSQL via Supabase managed platform
- Extensions: `uuid-ossp`, `pgcrypto`
- Schema defined in `sql/schema.sql`; incremental migrations in `migrations/*.sql`
- JSONB columns used for flexible payloads: `hr_zones_s`, `raw_payload`, `splits`, `weather`
- All timestamps in UTC (TIMESTAMPTZ); timezone conversion to Europe/Rome handled in application layer
- RLS enabled (single-user policy)

## Infrastructure / Deployment

- `ingest.yml` — runs every 3 hours on `ubuntu-latest`, syncs Garmin → Supabase, triggers analytics and coaching pipeline
- `morning-briefing.yml` — daily at 06:20 UTC, sends Telegram brief
- `deploy-dashboard.yml` — on push to `main` (dashboard paths): builds with Vite, deploys to Cloudflare Pages
- `weekly-review.yml`, `proactive-check-in.yml`, `proactive-reminders.yml`, `pattern-extraction.yml`, `backfill-analyses.yml`, `db_cleanup.yml`, `dr-snapshot.yml`, `keepalive.yml`, `watchdog.yml`, `debrief-reminder.yml`
- Dashboard deployed to Cloudflare Pages (`triathlon-dashboard` project)
- MCP server deployed as Cloudflare Worker (`mcp-server`)
- Telegram bot deployed as Cloudflare Worker (`telegram-bot`) with KV namespace for update dedup

## Gaps & Unknowns

- No `pyproject.toml` or `setup.py` — project is not a proper Python package; imports rely on `PYTHONPATH=.`
- No pinned Python lockfile (pip-compile or Poetry) — dependency versions may drift across environments
- No frontend test framework detected (no jest/vitest config in `dashboard/`)
- TypeScript `tsconfig.json` not verified at root or in worker directories
- Strava sync is commented out in `ingest.yml` — integration exists in code but disabled in CI

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Summary

## Language Conventions

### Python (`coach/`, `scripts/`)

- All function signatures are annotated
- `Optional[X]` preferred over `X | None` (pre-3.10 compat via `__future__`)
- `# type: ignore` used sparingly (2–3 occurrences in `coach/coaching/pattern_extraction.py` and `coach/ingest/garmin.py`)

### TypeScript (`workers/`)

- Interface-first: domain types declared as `interface` at top of file
- No type aliases for simple types
- Arrow functions for handlers, named functions for utilities
- JSDoc block comments on exported functions/classes

## Naming Conventions

- Files: `snake_case.py` (e.g., `fitness_test_processor.py`, `belief_engine.py`)
- Functions: `snake_case` — private helpers prefixed with `_` (e.g., `_score_tsb`, `_fetch_activities_window`)
- Classes: `PascalCase` (e.g., `WellnessHistory`, `TrainingState`, `FitnessTestProcessor`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `HRV_WARNING_Z`, `CTL_TIME_CONSTANT`, `BUDGET_BLOCKED`)
- Dataclasses: used for pure-data value objects (e.g., `DailyTSS`, `PMCPoint`, `ReadinessReport`)
- Pydantic models: used for DB-bound schemas in `coach/models/schemas.py`
- Files: `index.ts` (single entry point per worker)
- Interfaces: `PascalCase` with `I`-prefix absent
- Handler functions: `handle<Command>` pattern (e.g., `handleBrief`, `handleLog`)

## Code Organization Patterns

- `@dataclass` (sometimes `frozen=True`) for pure computation types: `coach/analytics/pmc.py`, `coach/analytics/readiness.py`
- `pydantic.BaseModel` (via `BaseDBModel`) for DB mirror types: `coach/models/schemas.py`

## Error Handling Patterns

## Logging Conventions

- `logger.info(...)` — normal operational events (sync completed, record upserted)
- `logger.warning(...)` — non-fatal anomalies (Garmin endpoint unavailable, validation warning)
- `logger.exception(...)` — unexpected exceptions (logs traceback automatically)

## Comment and Documentation Style

## Formatting

- 4-space indentation (Python)
- Line length: not enforced mechanically; long lines appear in docstrings and SQL strings
- Trailing commas in multi-line function calls and dict literals (common but not universal)
- Section dividers in larger files: `# ============================================================================`

## Gaps & Unknowns

- No linter or formatter is configured (no `ruff`, `black`, `isort`, `flake8` config found). Conventions are informal and enforced only by code review.
- TypeScript workers (`workers/telegram-bot/src/index.ts`, `workers/mcp-server/src/`) have no linting config and no automated test coverage.
- No `mypy` or `pyright` config found; type checking is not enforced in CI.
- The `coach/cognition/` package (`inference/`, `prediction/`, `prescription/`) contains only `__init__.py` files — these are stubs with no implementation.

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## Summary

## System Overview

```

```

## Component Responsibilities

| Component | Responsibility | Key Files |
|-----------|----------------|-----------|
| Ingest | Pull Garmin/Strava data → upsert Supabase | `coach/ingest/garmin.py`, `coach/ingest/strava.py` |
| Analytics | Deterministic computation: PMC, readiness, HRV flags | `coach/analytics/pmc.py`, `coach/analytics/readiness.py`, `coach/analytics/daily.py` |
| Belief Engine | Bayesian athlete belief lifecycle (create/reinforce/contradict/decay) | `coach/analytics/belief_engine.py`, `coach/analytics/belief_guardrails.py` |
| Coaching | LLM-powered: post-session analysis, modulation proposals, weekly narrative | `coach/coaching/post_session_analysis.py`, `coach/coaching/modulation.py`, `coach/coaching/weekly_analysis.py` |
| Planning | Rule-based briefing generator (zero LLM calls) | `coach/planning/briefing.py` |
| Decision | Priority arbitration engine (safety > recovery > injury > race > ...) | `coach/decision/priority_engine.py` |
| Cognition (facade) | Semantic re-exports grouping inference/prediction/prescription | `coach/cognition/inference/`, `coach/cognition/prediction/`, `coach/cognition/prescription/` |
| MCP Server | JSON-RPC tool server for Claude.ai; read + propose-only writes | `workers/mcp-server/src/index.ts` |
| Telegram Bot | Athlete interaction hub: logs, confirmations, briefings, proactive Q&A | `workers/telegram-bot/src/index.ts` |
| LLM Client | Hybrid routing Gemini (free/high-vol) vs Anthropic API (critical) + budget gating | `coach/utils/llm_client.py` |
| Models | Pydantic schemas mirroring DB tables | `coach/models/schemas.py` |
| Scripts | Operational one-offs: backfill, DR, smoke tests, keepalive, update CLAUDE.md | `scripts/` |
| Dashboard | Read-only Vite/React view of training data | `dashboard/src/` |

## Layers

- Purpose: Fetch external data (Garmin Connect, Strava) and write to Supabase
- Location: `coach/ingest/`
- Idempotent via upsert on `(external_id, source)`
- Depends on: `coach/models/schemas.py`, `coach/utils/supabase_client.py`
- Purpose: Pure deterministic computations — PMC (CTL/ATL/TSB via EWMA), composite readiness score, HRV z-score flags
- Location: `coach/analytics/`
- Zero LLM calls; all functions are testable and deterministic
- Depends on: nothing external; pure Python + Supabase data
- Purpose: LLM-powered intelligence: post-session analysis, mid-week plan modulation proposals, race prediction, fitness test processing, weekly narrative
- Location: `coach/coaching/`
- Always writes results back to Supabase; sends Telegram notifications
- LLM calls routed through `coach/utils/llm_client.py`
- Purpose: Generate daily morning briefs (rule-based, zero LLM cost)
- Location: `coach/planning/`
- Reads `planned_sessions`, `daily_wellness`, `daily_metrics`, `activities` from Supabase
- Sends formatted brief to Telegram
- Purpose: Arbitrate competing coaching priorities with a strict 9-level hierarchy
- Location: `coach/decision/priority_engine.py`
- Priority 1 (safety) always wins; Priorities 1-3 are hard constraints
- Purpose: Semantic grouping of inference, prediction, prescription — re-exports from analytics/coaching/decision
- Location: `coach/cognition/inference/`, `coach/cognition/prediction/`, `coach/cognition/prescription/`
- Does not contain logic; is an organizational namespace
- Purpose: Edge-deployed stateless HTTP handlers for Telegram webhooks and MCP tool calls
- Location: `workers/mcp-server/`, `workers/telegram-bot/`
- Auth: Telegram uses `TELEGRAM_ALLOWED_CHAT_ID` allowlist; MCP uses `MCP_BEARER_TOKEN`
- State: KV Namespace used for Telegram dedup on `update_id`

## Data Flow

### Daily Ingest → Brief

### Post-Session Analysis

### Claude.ai Human-in-the-Loop

### Fitness Test Processing

## Key Abstractions

- Markdown files loaded as LLM system prompts at runtime
- Each corresponds to a coaching workflow: `session_analysis.md`, `fitness_test.md`, `weekly_review.md`, etc.
- Loaded by Python modules via `Path(__file__).resolve().parent.parent.parent / "skills" / "*.md"`
- `coach/utils/llm_client.py` routes by `purpose` string
- Gemini (free): high-volume tasks (`session_analysis`, `pattern_extraction`, `proactive_question`)
- Anthropic API (paid, budget-gated): critical decisions (`modulation`, `race_prediction`, `weekly_analysis`)
- Claude Pro via Claude.ai: human-in-the-loop workflows (not in code, handled interactively)
- Hard limit €5/month; tracked in `coach/utils/budget.py`
- `BudgetExceededError` raised and caught in all LLM-calling paths
- Auto-degradation from Sonnet → Haiku before hard block at $4.80
- `coach/analytics/belief_engine.py` stores Bayesian athlete beliefs in `beliefs` table
- Lifecycle: `create_belief` → `reinforce_belief` / `contradict_belief` → `decay_old_beliefs`
- Actionable beliefs feed the `DecisionContext` in `coach/decision/priority_engine.py`

## Entry Points

- `python -m coach.ingest.garmin` — daily data sync
- `python -m coach.planning.briefing` — morning brief
- `python -m coach.coaching.post_session_analysis --recent` — post-session analysis
- `python -m coach.coaching.pattern_extraction` — weekly pattern extraction
- `python -m coach.coaching.weekly_analysis` — weekly narrative
- `python -m coach.coaching.proactive_questions` — 3x/week proactive check-ins
- `python -m scripts.watchdog` — health monitoring alerts
- Commands: `/brief`, `/log`, `/rpe`, `/debrief`, `/status`, `/budget`, `/undo`, `/history`, `/help`
- Entry: `workers/telegram-bot/src/index.ts` webhook handler
- MCP tools via `workers/mcp-server/src/index.ts`
- Tools: `get_weekly_context`, `get_race_context`, `get_session_review_context`, `get_daily_brief`, `commit_plan_change`, `get_physiology_zones`, `trigger_ingest`, etc.
- `make brief` — manual brief generation
- `make backfill-garmin` — historical sync 730 days
- `python -m scripts.smoke_test` — connectivity check

## Architectural Constraints

- **No persistent server:** Python runs as ephemeral GitHub Actions jobs. No always-on Python process.
- **Cloudflare Workers are stateless:** KV Namespace used only for dedup; no in-memory state across requests.
- **Single athlete:** All queries are unscoped (no user_id). Schema and code assume one athlete.
- **Confirm before write:** `planned_sessions` must never be modified without explicit athlete confirmation. This is enforced socially (coach pattern in CLAUDE.md §5.4) and technically (MCP `commit_plan_change` is the only write path for plan changes from Claude).
- **Deterministic analytics:** `coach/analytics/` contains zero LLM calls. All rules codified in Python and tested.
- **Global state:** `coach/utils/supabase_client.py` provides a module-level singleton Supabase client.

## Anti-Patterns

### Calling LLM from analytics layer

### Writing to `planned_sessions` without confirmation

### Bypassing budget gating

## Error Handling

- `BudgetExceededError` caught in all LLM paths; logs warning and skips LLM step gracefully
- `record_health(component, status)` called at end of every scheduled job (`coach/utils/health.py`)
- Watchdog (`scripts/watchdog.py`) reads `health` table and alerts if any component is stale beyond threshold
- Telegram Bot uses KV dedup on `update_id` to prevent duplicate processing of retried webhooks

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
