# Multi-atleta — design e stato

Il sistema nasce single-athlete per scelta esplicita. Questo documento descrive
come diventa multi-atleta, cosa è già fatto e cosa manca.

## Decisioni prese

| Domanda | Scelta | Conseguenza |
|---|---|---|
| Un sistema o due istanze? | **Un sistema, due atlete** | `athlete_id` su 21 tabelle; una sola codebase, ogni fix vale per entrambe |
| Come interagisce la seconda atleta? | **Telegram proprio, brief propri** | Routing per `telegram_chat_id`, sia in entrata sia in uscita |
| Fonte dati | **Strava** (Garmin per Nicolò) | Ingest per atleta; niente dati wellness (vedi sotto) |

## Il limite da conoscere: Strava non dà wellness

L'API Strava espone attività, HR, potenza, passo, dislivello. **Non** espone
HRV, punteggio del sonno, body battery né HR a riposo — dati che su Garmin
arrivano da `daily_wellness` e che pesano per metà nel readiness.

Conseguenze per un'atleta su Strava:

| Componente | Garmin | Strava |
|---|---|---|
| PMC (CTL/ATL/TSB) | ✅ | ✅ (hrTSS da HR media, serve LTHR misurata) |
| Analisi post-sessione | ✅ | ✅ |
| Zone e test fitness | ✅ | ✅ |
| HRV z-score e flag di fatica | ✅ | ❌ |
| Punteggio sonno | ✅ | ❌ |
| Readiness composito | 4 fattori | **2 fattori** (TSB + soggettivo) |

Per questo `athletes.has_wellness_data` è una colonna esplicita: il layer
analytics deve **sapere** che quei dati non esistono, invece di dedurlo
dall'assenza — che è indistinguibile da un sync rotto e farebbe scattare
allarmi falsi.

La contromisura di coaching è quella che userebbe un allenatore vero con
un'atleta senza wearable avanzato: pesare di più il soggettivo (check-in
mattutino con sonno percepito, energia, dolori) e dichiarare la minore
confidenza nelle prescrizioni.

## Fasi

### ✅ Fase 1 — Fondazione schema (`2026-08-09-multi-athlete-foundation.sql`)

- Tabella `athletes` (slug, timezone, chat Telegram, fonte dati, flag wellness)
- `athlete_id` su 21 tabelle, con backfill sull'atleta esistente
- **Vincoli UNIQUE ricostruiti con `athlete_id`** — il punto che romperebbe in
  silenzio: `daily_wellness.date`, `daily_metrics.date`, `beliefs.belief_key`,
  `(trigger_type, sent_date)`, le chiavi di `planned_sessions`,
  `physiology_zones`, `races`, `mesocycles` e il vincolo parziale su
  `active_constraints` erano tutti globali. Senza modificarli, la seconda
  atleta non riuscirebbe a salvare nemmeno una giornata di wellness.
- `DEFAULT` all'atleta esistente su `athlete_id`: il codice non ancora
  aggiornato continua a scrivere righe valide. **Va rimosso** a fine Fase 2.

La migration è additiva e idempotente: applicarla non rompe nulla di ciò che
gira oggi.

### ⬜ Fase 2 — Scoping delle query

Ogni job gira **per atleta**. Il contesto arriva da env (`ATHLETE_SLUG`) e i
workflow diventano una matrix. Circa 290 query da filtrare su `athlete_id`.

Ordine consigliato: analytics → planning → coaching → ingest. A fine fase si
rimuove il `DEFAULT` dalla colonna, così una query non filtrata fallisce in
modo rumoroso invece di scrivere sull'atleta sbagliato.

### ⬜ Fase 3 — Ingest per atleta

Garmin resta per Nicolò. Per la seconda atleta si riattiva
`coach/ingest/strava.py` (già scritto e verificato: paginazione e timeout
corretti) con credenziali per atleta. Attenzione al finding dell'audit: se un
giorno un atleta avesse **entrambe** le fonti attive, le attività verrebbero
contate due volte nel PMC — serve dedup per sovrapposizione temporale.

### ⬜ Fase 4 — Telegram multi-chat

`telegram_chat_id` → `athlete_id` in entrata; in uscita ogni messaggio deve
sapere a chi va. Oggi `telegram_logger` legge un unico `TELEGRAM_CHAT_ID`.

### ⬜ Fase 5 — MCP e dashboard

Il coach su Claude.ai deve poter dire "di quale atleta parliamo": parametro
`athlete` sui tool, o token separati. La dashboard ha bisogno di
autenticazione per atleta.

### ⬜ Fase 6 — Readiness ricalibrato

Con `has_wellness_data = false`, il readiness usa TSB + soggettivo con pesi
rinormalizzati e dichiara la confidenza ridotta nel brief.

## Cose che restano hardcoded sull'atleta attuale

Da ripulire durante le fasi 2-6:

- `pattern_extraction.py`: il nome "Nicolò" finisce nel testo delle belief generate
- `workers/telegram-bot`: le keyword infortunio (`spalla|fascite`) sono le sue
- `CLAUDE.md` §2: profilo, struttura settimanale e pattern mentali sono suoi —
  serviranno profili per atleta (l'anamnesi è già generata dal DB, quindi
  quella parte è pronta)
