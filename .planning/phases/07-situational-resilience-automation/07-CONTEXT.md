# Phase 7: Situational Resilience & Automation - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Il sistema rileva automaticamente situazioni reali (sessione saltata, malattia, trasferta Croazia, spostamento sessione) e risponde con una proposta di ricalibrazione via Telegram — senza che Nicolò debba chiederla. Tutto su Gemini Flash / fallback Haiku (costo €0 / minimo).

**In scope:**
- Missed session detection nel ciclo ingest 3h (confronto planned_sessions vs activities)
- TSB-gated response: ricalibra settimana (TSB > -10) o alleggerisci (TSB < -20)
- Illness protocol: illness_flag=True → proposta sostituzione sessioni intense con Z2/riposo + 24h recovery tracking + re-entry plan
- Travel command Telegram `/travel YYYY-MM-DD` → scrittura su subjective_log → adattamento piano domenicale (swap swim → run, carico invariato)
- Reschedule rebalancing: quando commit_plan_change MCP riceve un reschedule → check back-to-back hard sessions → proposta settimana ribilanciata
- Empty plan nudge domenicale: se planned_sessions per la settimana entrante è vuota domenica sera → Telegram nudge "nessun piano, pianifica su Claude.ai"
- LLM routing: tutti i nuovi purpose resilience_* su Gemini Flash, fallback Anthropic Haiku se Gemini non disponibile

**Out of scope:**
- Generazione automatica del piano settimanale (Nicolò lo fa con Claude.ai ogni domenica)
- Weekly summary domenicale (weekly-review.yml già lo copre — non duplicare)
- Multi-day travel scheduling (solo flag travel = present/absent per la settimana)
- `/move` command Telegram (rescheduling solo via Claude.ai MCP)

</domain>

<decisions>
## Implementation Decisions

### Gap 1 — Missed session detection (RESILIENCE-02 / AUTO-01)

- **D-01:** Rilevamento deterministico nel ciclo ingest: nuovo step Python in `ingest.yml` dopo il sync, confronta `planned_sessions[ieri]` vs `activities[ieri]` per disciplina. Zero LLM. Se nessuna activity trovata per quel sport in quella data → missed.
- **D-02:** TSB-gated response da RESILIENCE-02 esattamente come definito: TSB > -10 → proposta ricalibrazione settimana (ridistribuisce carico rimanente); TSB < -20 → proposta settimana alleggerita; TSB tra -10 e -20 → nessuna azione (o soft note opzionale a discrezione Claude).
- **D-03:** La logica vive in `adaptive_planner.py` (già esiste). Aggiungere funzione `detect_missed_sessions(date=yesterday)` che chiama `propose_modulation()` già in `modulation.py` con `trigger_event='missed_session'`.

### Gap 2 — Illness protocol (RESILIENCE-04)

- **D-04:** Trigger: `illness_flag=True` in `daily_metrics` nel ciclo ingest → proposta automatica modulation di tipo `illness_protocol`. La logica vive in `modulation.py` (estensione del path illness già presente nei critical_flags).
- **D-05:** Proposta illness: sostituisci sessione/i intense di oggi/domani con Z2 30-40min o riposo. Scrivi `plan_modulations` con `trigger_event='illness_protocol'`.
- **D-06:** Recovery tracking: 24h consecutive senza `illness_flag` (8 cicli ingest) **AND** HRV z-score > -1.0 SD → proposta graduale re-entry (prima sessione Z2 light, poi progressione normale). Timestamp-based: leggi quando illness_flag è comparso per la prima volta.
- **D-07:** LLM: Gemini Flash per generare testo della proposta illness + re-entry plan.

### Gap 3 — Travel / Croazia detection (RESILIENCE-03)

- **D-08:** Meccanismo: nuovo comando Telegram `/travel YYYY-MM-DD` (data partenza). Il bot Worker scrive riga in `subjective_log` con `kind='travel'` e `details={"destination":"croatia","departure":"YYYY-MM-DD"}`.
- **D-09:** Il generatore domenicale (adaptive_planner gira già domenica in pattern-extraction.yml): legge `subjective_log` per travel entries nella settimana entrante. Se presente: carico invariato, swap sessioni nuoto → run Z2 equivalente (durata proporzionale), nota "trasferta Croazia: recovery bonus atteso, carico confermato".
- **D-10:** Assunzione hardcoded: in trasferta Croazia non c'è accesso piscina → swim sempre sostituita con run. Nessun parametro pool=yes/no.

### Gap 4 — Reschedule rebalancing (RESILIENCE-01)

- **D-11:** Trigger: quando MCP `commit_plan_change` riceve un reschedule (tipo `move_session` o `swap_date`), il MCP server triggera via GitHub Actions dispatch un check Python-side.
- **D-12:** Il check Python: verifica se il nuovo giorno target ha già una sessione hard (Z4+) → se sì, propone settimana ribilanciata via Telegram per conferma prima di applicare. Se no, applica direttamente.
- **D-13:** "Sessione hard" = `planned_sessions.intensity_zone >= 4` o `session_type IN ('interval', 'threshold', 'vo2max')`. Logica deterministica in `adaptive_planner.py` o nuovo helper.
- **D-14:** Solo via Claude.ai (commit_plan_change MCP) — nessun comando Telegram `/move`.

### Gap 5 — Empty plan nudge domenicale (AUTO-02 ridefinito)

- **D-15:** AUTO-02 ridefinito: Nicolò apre Claude.ai ogni domenica per il piano → auto-generazione non serve. Il sistema invia solo un nudge se `planned_sessions` per lun-dom prossimi è vuota domenica sera.
- **D-16:** Implementazione: aggiungere check DB a `weekly-review.yml` (non un nuovo workflow). Se domenica sera alle 20:00 Rome nessuna sessione pianificata per la settimana entrante → Telegram message "⚠️ Nessun piano per la settimana prossima, apri Claude.ai per pianificare".
- **D-17:** Il nudge è minimale — nessun CTL/ATL/TSB summary (già nel weekly review domenicale esistente).

### LLM Routing per Phase 7

- **D-18:** Tutti i nuovi purpose aggiunti a `llm_client.py`:
  - `'resilience_missed_session'` → Gemini Flash (proposta testo ricalibrazione)
  - `'resilience_illness'` → Gemini Flash (testo proposta illness/re-entry)
  - `'resilience_travel'` → Gemini Flash (testo adattamento settimana travel)
  - `'resilience_reschedule'` → Gemini Flash (proposta rebalancing)
  - Fallback: Anthropic Haiku se Gemini non disponibile (pattern già in HybridClient)
- **D-19:** Zero chiamate Anthropic Sonnet/Opus per Phase 7 — solo Gemini + Haiku fallback.

### Claude's Discretion

- Testo esatto delle Telegram notification per ogni scenario (missed session, illness, travel, reschedule)
- Threshold esatto tra "sessioni rimanenti nella settimana" per decidere se ricalibrazione è materiale (es. se manca solo 1 giorno a domenica, saltare la proposta)
- Gestione del caso TSB tra -10 e -20 per missed session (soft note o silenzio)
- Formato esatto della proposta di rebalancing settimana (lista sessioni o summary)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Profilo atleta e regole deterministiche
- `CLAUDE.md` §2 (profilo atleta) — struttura settimanale fissa (lun corsa, mar nuoto, mer bici, gio nuoto, ven corsa, sab bici, dom corsa); trasferte Croazia = recovery bonus, non stress; vincoli spalla destra
- `CLAUDE.md` §5.1-5.2 (regole deterministiche) — soglie HRV flag, mappatura flag→azioni, illness_flag = STOP intensità finché baseline non recupera; format §6 per Telegram messages
- `CLAUDE.md` §13 (modalità proattiva) — plan_modulations pattern, aspetta conferma atleta prima di scrivere su planned_sessions

### Requirements Phase 7
- `.planning/ROADMAP.md` §Phase 7 — goal, 6 success criteria, requirements RESILIENCE-01/02/03/04, AUTO-01/02
- `.planning/REQUIREMENTS.md` §RESILIENCE-01, RESILIENCE-02, RESILIENCE-03, RESILIENCE-04, AUTO-01, AUTO-02 — acceptance criteria definitivi

### Codice da modificare
- `coach/coaching/adaptive_planner.py` — aggiungere `detect_missed_sessions()` (D-03) + travel-aware Sunday logic (D-09) + reschedule hard-session check (D-13)
- `coach/coaching/modulation.py` — estendere con illness-specific path: proposta sostituzione sessioni, recovery tracking, re-entry proposal (D-04/D-05/D-06)
- `coach/utils/llm_client.py` — aggiungere routing per 4 nuovi purpose `resilience_*` → Gemini Flash + Haiku fallback (D-18)
- `.github/workflows/ingest.yml` — aggiungere step missed session detection dopo daily metrics compute (D-01)
- `.github/workflows/weekly-review.yml` — aggiungere check `planned_sessions` vuota + nudge Telegram (D-16)
- `workers/telegram-bot/src/index.ts` — aggiungere handler `/travel YYYY-MM-DD` → scrive subjective_log (D-08)
- `workers/mcp-server/src/index.ts` — `commit_plan_change` reschedule path → triggera Python-side rebalancing check (D-11)

### Schema DB e migration
- `sql/schema.sql` — `plan_modulations` (trigger_event, proposed_changes, status), `subjective_log` (kind values check constraint), `daily_metrics` (illness_flag, tsb_score) — reference per nuovi INSERT patterns
- `migrations/` — pattern esistenti per eventuali nuove colonne o constraint kind values update

### Codice di supporto (lettura, no modifica)
- `coach/analytics/readiness.py` — illness_flag detection logic; HRV z-score computation per re-entry check (D-06)
- `coach/analytics/pmc.py` — TSB computation; leggere prima di implementare TSB-gate (D-02)
- `coach/coaching/modulation.py` `propose_modulation()` + `generate_modulation_proposal()` — API esistente da riusare per nuovi trigger
- `coach/planning/briefing.py` — pattern per lettura `daily_metrics` + `planned_sessions` (reference per missed session check)
- `.planning/phases/06-physiological-adaptation-intelligence/06-CONTEXT.md` — D-09 (active_beliefs in get_weekly_context), D-12 (last_fatigue_by_sport) — non duplicare, estendere
- `.planning/phases/05-workout-prescription-quality/05-CONTEXT.md` — D-15 (active_constraints), structured session format per sessioni sostitutive illness/travel

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coach/coaching/modulation.py` `propose_modulation(trigger, trigger_data, proposed_changes)` — API pronta per nuovi trigger (missed_session, illness_protocol, travel_week, reschedule). Non riscrivere — estendere.
- `coach/coaching/modulation.py` `_send_modulation_telegram(message, mod_id)` — inline button ✅/❌ già implementati. Riusare per tutte le nuove proposte.
- `coach/coaching/adaptive_planner.py` `compute_weekly_compliance()` — già calcola missed_sports per la settimana. Base per detect_missed_sessions() intraday.
- `coach/analytics/readiness.py` `illness_flag` — già estratto da subjective_log e propagato in daily_metrics. Il dato è disponibile nel ciclo ingest.
- `coach/analytics/pmc.py` — TSB già calcolato in `daily_metrics.tsb_score`. Usare `daily_metrics` come source per il TSB-gate, non ricalcolare.
- `coach/utils/telegram_logger.py` — helper per send Telegram message outbound (usato in briefing.py + modulation.py). Pattern da seguire per il nudge domenicale.

### Established Patterns
- `ingest.yml` step sequence: Garmin sync → compute daily metrics → post-session analysis → fitness test → apply modulations → ETL health check. Il missed session check va **dopo** compute daily metrics (dipende da illness_flag e TSB).
- `plan_modulations` trigger_event come discriminante tipo proposta: `'fatigue_warning'`, `'illness_flag'` già esistono. Aggiungere: `'missed_session'`, `'illness_protocol'`, `'travel_week'`, `'reschedule_check'`.
- Telegram bot handler pattern (TypeScript): `if (text.startsWith('/travel'))` → parse data → POST to Supabase REST API. Pattern uguale a `/log`, `/rpe`.
- `subjective_log.kind` CHECK constraint esistente: `'rpe', 'illness', 'injury', 'free_note'`. Verificare se `'travel'` va aggiunto via migration.

### Integration Points
- `ingest.yml` → `adaptive_planner.detect_missed_sessions()` → `modulation.propose_modulation(trigger='missed_session')` → `plan_modulations` → Telegram inline button
- `ingest.yml` → `daily_metrics.illness_flag=True` → `modulation.illness_protocol_check()` → `plan_modulations` + recovery tracking
- Telegram bot `/travel` → `subjective_log` → `adaptive_planner` (domenica) → plan adjusted
- MCP `commit_plan_change` reschedule → GitHub Actions dispatch → Python reschedule_check → Telegram proposal

</code_context>

<specifics>
## Specific Ideas

### TSB-gate per missed session (D-02)
Valori esatti da RESILIENCE-02:
- TSB > -10: ricalibra la settimana rimanente (ridistribuisce volume, non elimina sessioni)
- TSB < -20: proposta "settimana alleggerita" (volume -20-30%, intensità mantenuta breve)
- TSB -10 ÷ -20: a discrezione Claude (soft note o silenzio — D-19 Claude's Discretion)

### Travel command format (D-08)
Telegram: `/travel 2026-06-15` (ISO date partenza)
subjective_log row: `{kind: 'travel', logged_at: now, details: {destination: 'croatia', departure_date: '2026-06-15', week_affected: '2026-06-15/2026-06-21'}}`

### Illness recovery check (D-06)
Condition AND: `(now - first_illness_timestamp) >= 24h` AND `latest daily_metrics.hrv_z_score > -1.0`
Non AND OR — entrambe le condizioni devono essere vere per proporre re-entry.

### Kind constraint migration (D-08)
`subjective_log.kind` ha CHECK constraint. Va aggiunto `'travel'` via migration prima di usarlo.

</specifics>

<deferred>
## Deferred Ideas

- **Weekly summary domenicale pre-pianificazione** (CTL/ATL/TSB snapshot in Telegram prima che Nicolò apra Claude.ai) — weekly-review.yml già copre la review; se si vuole arricchire con numeri chiave va in Phase 8 (Brief Quality) o come estensione della weekly review
- **Telegram `/move` command** per spostare sessioni senza aprire Claude.ai — Nicolò preferisce usare MCP, fuori scope Phase 7
- **Auto-generazione piano settimanale con Gemini** (AUTO-02 originale) — Nicolò apre Claude.ai ogni domenica, non serve; deferred indefinitamente

</deferred>

---

*Phase: 7-situational-resilience-automation*
*Context gathered: 2026-06-09*
