# Phase 3: Deploy & Pipeline Resilience - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Eseguire tutte le migrazioni SQL pending su Supabase, ridistribuire il Telegram bot con i fix K2-K5, integrare `apply_accepted_modulations` in `ingest.yml`, correggere i fix pipeline L1-L4, e verificare ogni deploy tramite script e test manuale. Nessuna nuova feature — solo fix noti e deploy di codice già committato.

</domain>

<decisions>
## Implementation Decisions

### Ordine operazioni deploy
- **D-01:** Migrazioni SQL prima (prerequisito per K2/K3 che richiedono i nuovi CHECK values) → `wrangler deploy` bot → modifiche `ingest.yml`
- **D-02:** Migrazioni eseguite manualmente via Supabase SQL Editor (dashboard), non tramite script o CLI — controllo diretto, errori visibili subito
- **D-03:** Wrangler configurato localmente con credenziali attive — il deploy bot è eseguibile senza setup aggiuntivo

### apply_accepted_modulations (DEPLOY-04)
- **D-04:** Aggiunto come **step separato** in `ingest.yml` dopo il blocco ingest Garmin — non inline nel modulo Python
- **D-05:** Su failure (o zero modulazioni accepted), **logga e continua** — non blocca l'ingest. L'ingest Garmin è più critico.
- **D-06:** Il step usa `python -m coach.coaching.modulation --apply-accepted` (o equivalente) con `if: always()` rimosso per evitare esecuzione su ingest fallito

### Verifica deploy
- **D-07:** Creare `scripts/verify_migrations.py` — script che interroga `information_schema` e verifica CHECK constraints, UNIQUE indexes, FK presenti per ogni migrazione. Output pass/fail per migrazione.
- **D-08:** Verifica bot Telegram dopo deploy: test manuale via chat Telegram (non script automatico). Phase 4 fa la verifica comportamentale completa.

### Brief idempotency (PIPELINE-04)
- **D-09:** Meccanismo: **check DB su tabella** (es. `bot_messages` con `type='brief'` o tabella `sent_briefs` dedicata) prima di inviare. Se esiste già una riga per `date=today`, skip. Persistente su restart, nessuna dipendenza da KV o orari.
- **D-10:** Il check avviene in `coach/planning/briefing.py` prima della generazione del messaggio — non nel workflow GitHub Actions.

### Claude's Discretion
- Struttura esatta della tabella/query per idempotency (colonne, index) — segui i pattern esistenti in `bot_messages`
- Messaggio di log quando brief è già stato inviato oggi
- Gestione errori nei fix L2/L3/L4 — segui lo stile error handling esistente nel progetto

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit e fix noti
- `docs/audit_resilience_2026-06-01.md` — Censimento completo dei bug. Sezioni K (Telegram bot K2-K5), L (workflow L1-L4), M (script operativi). Ogni fix ha ID e loc precisa.
- `migrations/2026-06-01-resilience-audit.sql` — Migrazione principale dell'audit. Contiene CHECK constraints, UNIQUE, FK ON DELETE, expires_at, kind values.

### Codice da modificare
- `workers/telegram-bot/src/index.ts` — Fix K2-K5 (status routing, kind constraint, webhook guard, resp.ok check)
- `.github/workflows/ingest.yml` — Fix L1 (exit code retry), aggiunta step apply_accepted_modulations
- `coach/planning/briefing.py` — Idempotency check brief
- `scripts/watchdog.py` — Fix L4 (rileva componenti con health row mancante)
- `scripts/dr_snapshot.py` — Fix L3 (abort su tabelle critiche vuote)
- `coach/ingest/garmin.py` o `scripts/db_cleanup.py` — Fix L2 (re-raise su except)

### Schema e migrazioni
- `sql/schema.sql` — Schema di riferimento
- `migrations/` — Tutte le migrazioni pending da verificare

### Requirements
- `.planning/REQUIREMENTS.md` §Deploy & Migrazioni (DEPLOY-01..04), §Resilienza Pipeline (PIPELINE-01..04)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coach/utils/supabase_client.py` — client singleton per query DB (usato in verify_migrations.py)
- `workers/telegram-bot/src/index.ts` — pattern `supabaseFetch` già presente per .ok check (K5 riusa questo pattern)
- `bot_messages` table — già esiste con colonne type/date — candidata naturale per idempotency check brief

### Established Patterns
- Script in `scripts/` usano `logger` + exit code esplicito — verify_migrations.py segue lo stesso stile
- `ingest.yml` usa `python -m coach.ingest.garmin` — apply_accepted_modulations segue lo stesso pattern di invocazione
- Fix L1 (ingest.yml exit code): il retry loop con `sleep` deve terminare con `exit 1` se tutti i tentativi falliscono

### Integration Points
- `apply_accepted_modulations` dipende da `plan_modulations` table con `status='accepted'` — aggiornato dai fix K1/DEPLOY-04
- `sent_briefs` o `bot_messages` check avviene prima di ogni invio in `briefing.py`

</code_context>

<specifics>
## Specific Ideas

- `verify_migrations.py` deve verificare specificamente: CHECK su `kind` in `subjective_log`, CHECK su `status` in `pending_confirmations`, UNIQUE constraints, FK ON DELETE — come elencato in DEPLOY-01/02
- Il step `apply_accepted_modulations` in `ingest.yml` deve avere `continue-on-error: true` per non bloccare ingest su failure

</specifics>

<deferred>
## Deferred Ideas

- Fix A1-A10 (ingest Garmin resilience) — non in scope Phase 3, candidati per Phase 7
- Fix K6-K9 (Telegram bot warnings) — non bloccanti, da valutare in future fasi
- DR restore (L7) — Frankenstein state su restore — documentato, non fix urgente
- DST drift cron (L5) — documentato come edit manuale 2x/anno, non in scope

</deferred>

---

*Phase: 3-deploy-pipeline-resilience*
*Context gathered: 2026-06-06*
