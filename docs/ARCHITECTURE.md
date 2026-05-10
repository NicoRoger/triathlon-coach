# Architecture

## Vista d'insieme

```
            ┌─── Garmin Cloud ────┐
            │   Strava Cloud      │
            └──────────┬──────────┘
                       │ pull (3h)
                       ▼
   ┌──────────────────────────────────────┐
   │  GitHub Actions  (cron + workflows)  │
   │  - ingest.yml                        │
   │  - briefing.yml                      │
   │  - debrief-reminder.yml              │
   │  - watchdog.yml                      │
   │  - dr-snapshot.yml                   │
   │  - keepalive.yml                     │
   └──────────┬──────────────┬────────────┘
              │              │
              ▼              ▼
   ┌──────────────────┐  ┌──────────────────┐
   │  Supabase        │  │  GitHub repo     │
   │  (Postgres)      │  │  CLAUDE.md       │
   │  STATO operativo │  │  journal.md      │
   │                  │  │  snapshot DB     │
   └────────┬─────────┘  └────────┬─────────┘
            │                     │
            └─────────┬───────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │  Claude.ai/mobile + Claude Code opt  │
   │  via custom MCP connector            │
   └──────────────────────────────────────┘
            ▲                     ▲
            │ MCP                 │ Telegram webhook
   ┌────────┴────────┐    ┌───────┴──────────┐
   │  MCP Server     │    │  Telegram Bot    │
   │  (CF Worker)    │    │  (CF Worker)     │
   └─────────────────┘    └────────┬─────────┘
                                   │
                                   ▼
                              tu (telefono)
```

## Stack tecnologico

| Componente | Tech | Perché |
|------------|------|--------|
| DB | Supabase Postgres (free tier) | RLS nativo, SQL completo, snapshot facile |
| Cron jobs | GitHub Actions | 2000min/mese gratis, log integrati, niente VM |
| Workers | Cloudflare Workers | 100k req/giorno gratis, no cold start, webhook nativo |
| Bot | Telegram Bot API | Coda offline nativa, dictation iOS gratis, push affidabile |
| Agente | Claude.ai/mobile Pro + remote MCP; Claude Code opzionale | Già pagato, accessibile da smartphone, niente API LLM per review manuali |
| Fonti dati | `python-garminconnect`, `stravalib` | Stabili, attivamente manutenute |
| Lang | Python 3.11 (analytics/ingest) + TypeScript (Workers) | Uno per dominio, niente compromessi |

## I 7 flussi e i loro failure point

### A) Ingest oggettivo (cron 3h)

**Flusso:** GitHub Action → API Garmin/Strava → normalize → upsert Supabase →
update `health.last_sync_at`.

**Failure mode:**
- `garminconnect` rotto da update Garmin → **mitigazione**: retry exponential backoff
  (3 tentativi), se fallisce 24h alert su Telegram. Fallback: forwarding email
  Garmin summary parsato, oppure drop manuale FIT files in `data/manual_fit/`.
- Token Strava scaduto → refresh automatico via refresh_token.
- Rate limit Strava (200 req/15min, 2000/giorno) → batch + paginazione corretta.

### B) Ingest soggettivo (real-time)

**Flusso:** Telegram → bot CF Worker → parse strutturato (regex/keyword + Claude su
testi liberi se necessario, ma il parsing rapido è deterministico) → Supabase.

**Failure mode:**
- Zero rete → Telegram coda offline nativa. Parte al ritorno segnale.
- Worker down → Telegram conserva il messaggio, riprocessamento idempotente via
  `update_id`.
- Messaggio ambiguo → bot chiede chiarimento, non assume.

### C) Briefing mattutino (cron 06:30 Europe/Rome)

**Flusso:** Action → freshness check → query Supabase → genera markdown
rule-based (`coach/planning/briefing.py`) → push Telegram.

**Failure mode:**
- Dati stantii (>18h) → header con warning esplicito.
- Telegram API down → retry; se persistente, salva in repo come issue.
- **Nessuna chiamata API Claude** in questo flusso (zero costo). L'analisi profonda
  è on-demand quando apri Claude.ai.

### D) Debrief serale (cron 21:30)

**Flusso:** bot scrive a Nicolò con 4 domande → risposte → parse → Supabase +
append a `docs/training_journal.md` via commit Action.

**Failure mode:**
- Nicolò ignora → reminder a 22:30 e nel briefing del giorno dopo. Se mancano >2
  giorni consecutivi, flag esplicito nel brief.
- Risposte fuori formato → bot fa follow-up domanda per domanda.

### E) Conversazione coach (on-demand)

**Flusso:** Claude.ai/mobile → MCP connector → MCP Worker → Supabase → risposta
contestualizzata.

**Failure mode:**
- MCP Worker down → degraded: Claude.ai funziona ancora, ma senza dati live.
  Workaround: copia/incolla brief Telegram dell'ultima ora.
- Rate limit subscription Pro → aspetti reset (5h). In emergenza, Gemini come
  second-opinion gratuito.

### F) Pianificazione mesociclo (manuale settimanale)

**Flusso preferito:** Claude mobile/web → `get_weekly_context` via MCP → analizza
→ propone piano → conferma esplicita → `commit_plan_change` → Supabase.

**Flusso tecnico opzionale:** Macbook → Claude Code → modifica repository, test,
documentazione e manutenzione.

**Failure mode:**
- Divergenza git ↔ DB → **DB è proiezione di git** per la tabella `plans`. Single
  source di verità = git. Se divergono, vince git.

### G) Health check (cron 1h)

**Flusso:** watchdog Action legge `health.*` di tutti i flussi → soglie → push
Telegram + email se anomalia.

**Failure mode:**
- Watchdog stesso muore → **dead man's switch esterno** via healthchecks.io
  (free): se non riceve ping orario, manda alert.

## Mitigazioni trasversali

### Supabase pause su inattività
Free tier mette in pausa dopo 7 giorni senza connessioni. Mitigato da:
- Cron ingest 3h (tocca DB sempre)
- `keepalive.yml` daily come safety net
- Snapshot DB cifrato pushato su git ogni notte (DR completo, recover ~10min)

### Cost runaway
Architettura interamente free-tier. Unica spesa potenziale era API Claude → eliminata
spostando agente su subscription Pro. Hard cap inutile, non c'è dove sforare.

### Secrets management
- GitHub Secrets per Action (Garmin/Strava/Telegram/Supabase tokens)
- Cloudflare Secrets per Workers (Telegram bot token, Supabase service key)
- Mai in repo. Rotazione trimestrale calendarizzata.

### Time zones
- DB sempre in UTC (`TIMESTAMPTZ`)
- Rendering in `Europe/Rome` lato client
- Gare con TZ esplicita (campo dedicato in tabella `races`)

### Approvazione decisioni critiche
Modifiche `plans` richiedono conferma esplicita atleta. Le soglie fisiologiche dure
(HRV crash, malattia) sono regole deterministiche, non giudizio LLM.

### Cold start su nuovo device
- Macbook nuovo: `git clone` + `make setup` + login Claude Code → 5min
- Telefono nuovo: login Telegram → fine
- PC fisso che muore: irrilevante, non è nel percorso critico

## Cosa NON è nell'architettura (e perché)

- **OpenAI/Whisper API** → costo evitato. Dictation iOS nativa nei vocali Telegram.
- **TrainingPeaks/Intervals.icu integrazione** → non necessaria, abbiamo già Garmin/Strava
  e ricreiamo PMC nel layer analytics. Aggiungibile dopo se utile.
- **Auto-modifica del piano** → policy di sicurezza: l'agente propone, l'atleta committa.
- **Macchine locali always-on** → eliminate per resilienza. PC/Mac sono client.

## Costi reali

| Servizio | Free tier | Uso atteso | Margine |
|----------|-----------|------------|---------|
| Supabase | 500MB DB, 5GB bandwidth | <50MB DB, <100MB/mese | enorme |
| GitHub Actions | 2000min/mese | ~150min/mese | 13× |
| Cloudflare Workers | 100k req/giorno | ~500/giorno | 200× |
| Telegram | unlimited | unlimited | n/a |
| healthchecks.io | 20 check | 5-7 check | ok |
| Claude Pro | (subscription) | (già pagata) | n/a |

**Totale aggiuntivo: €0/mese.**

## Roadmap implementativa

### Fase 1 — Ingest + Storage (settimana 1-2)
- [ ] Setup Supabase, applica `sql/schema.sql`
- [ ] Configura secrets GitHub
- [ ] Implementa `coach/ingest/garmin.py` e backfill 24 mesi
- [ ] Implementa `coach/ingest/strava.py`
- [ ] Action `ingest.yml` schedulata e verificata

**Deliverable:** DB popolato con storico, sync automatico ogni 3h.

### Fase 2 — Analytics core (settimana 3)
- [ ] PMC (CTL/ATL/TSB) con decadimenti corretti per multisport
- [ ] Zone dinamiche (FTP/threshold/CSS) calcolate da DB
- [ ] Readiness score composito + flag deterministici

**Deliverable:** funzioni Python testate, output coerenti con i tuoi numeri storici noti.

### Fase 3 — Brief + Telegram (settimana 4)
- [ ] Worker bot Telegram base (echo + comandi `/brief`, `/log`)
- [ ] `briefing.yml` Action con push automatico 06:30
- [ ] Debrief serale strutturato

**Deliverable:** ricevi brief mattutino e fai debrief serale dal telefono.

### Fase 4 — Agente conversazionale (settimana 5)
- [ ] Compila profilo atleta in CLAUDE.md
- [ ] Skill files iniziali (query_metrics, propose_session)
- [ ] MCP server worker
- [ ] Aggiungi connector custom in Claude.ai
- [ ] Prima conversazione coach completa

**Deliverable:** chiedi a Claude.ai mobile "come sono messo?" e risponde con dati.

### Fase 5 — Pianificazione (settimana 6)
- [ ] Generatore mesociclo (Claude Code skill)
- [ ] Workflow review settimanale
- [ ] Tabella `plans` come proiezione di git

**Deliverable:** Claude Code propone mesociclo completo, tu approvi e va in DB.

### Fase 6 — Resilienza (settimana 7)
- [ ] DR snapshot daily
- [ ] Watchdog + healthchecks.io
- [ ] Test failover (spegni una cosa, verifica che il sistema regga)

**Deliverable:** sistema resiliente verificato, runbook completo.

### Fase 7 — Affinamento (settimana 8+)
- [ ] Iterazione su CLAUDE.md basata su uso reale
- [ ] Aggiunta skill man mano che emergono pattern
- [ ] Eventuale dashboard Streamlit (opzionale, se senti il bisogno)

**Deliverable:** sistema in steady state che migliora con l'uso.
