# Setup Guide

Setup iniziale completo: ~90 minuti la prima volta. Poi è autonomo.

## Prerequisiti

- Account GitHub
- Account Supabase (free)
- Account Cloudflare (free)
- Account Telegram + Telegram desktop per setup bot
- Account healthchecks.io (free)
- Garmin Connect attivo
- Strava attivo (raccomandato, backup di Garmin)
- Claude Pro attivo (€20/mese)
- Claude web/mobile con connector MCP; Claude Code opzionale per manutenzione repo

## Step 1 — Repo

```bash
gh repo create triathlon-coach --private
git clone <repo-url>
cd triathlon-coach
# Copia struttura blueprint
make setup-env  # crea .env da template
```

## Step 2 — Supabase

1. https://supabase.com → New project (free tier, region EU - Frankfurt più vicina)
2. Project settings → API → copia `URL`, `anon key`, `service_role key`
3. SQL editor → carica `sql/schema.sql` → run
4. Storage → create bucket `dr-snapshots` (private)

Salva su `.env`:
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=xxx
SUPABASE_SERVICE_KEY=xxx  # solo per GitHub Actions, mai in client
```

## Step 3 — Garmin

```python
# scripts/garmin_first_login.py — esegui una volta
# Genera token cache in ~/.garminconnect/
from garminconnect import Garmin
g = Garmin("email@example.com", "password")
g.login()
print("Token salvato.")
```

Copia il contenuto della cache in un secret GitHub `GARMIN_SESSION_JSON` (base64).

## Step 4 — Strava

1. https://www.strava.com/settings/api → crea app
2. Authorize URL con scope `read,activity:read_all`
3. Scambia code per refresh_token (script in `scripts/strava_first_auth.py`)
4. Secrets:
```
STRAVA_CLIENT_ID=xxx
STRAVA_CLIENT_SECRET=xxx
STRAVA_REFRESH_TOKEN=xxx
```

## Step 5 — Telegram bot

1. Apri @BotFather su Telegram
2. `/newbot` → scegli nome (es. `nicolo_coach_bot`)
3. Copia token
4. Manda `/start` al tuo bot da Telegram, prendi nota del tuo `chat_id`
   (curl `https://api.telegram.org/bot<TOKEN>/getUpdates`)

Secrets:
```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx  # solo il tuo, allow-list
```

## Step 6 — Cloudflare Workers

```bash
npm install -g wrangler
wrangler login

cd workers/telegram-bot
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_ALLOWED_CHAT_ID
wrangler secret put SUPABASE_URL
wrangler secret put SUPABASE_SERVICE_KEY
wrangler deploy

# Imposta webhook Telegram → Worker
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://telegram-bot.<account>.workers.dev/webhook"
```

Stesso processo per `mcp-server`.

## Step 7 — GitHub Actions secrets

Settings → Secrets → Actions → aggiungi tutti:
```
SUPABASE_URL
SUPABASE_SERVICE_KEY
GARMIN_SESSION_JSON
STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET
STRAVA_REFRESH_TOKEN
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
HEALTHCHECKS_PING_URL
DR_ENCRYPTION_KEY  # genera: openssl rand -base64 32
```

## Step 8 — MCP custom connector in Claude.ai/mobile

1. https://claude.ai/settings/connectors
2. Add custom connector
3. URL: `https://mcp-server.<account>.workers.dev/mcp`
4. Auth: Bearer token (configurato come secret nel Worker)
5. Test rapido da Claude mobile: `dammi il piano dei prossimi 7 giorni`
5. Test in chat: "che dati hai su di me?"

## Step 9 — Backfill storico

```bash
make backfill-garmin  # ultimi 24 mesi
make backfill-strava  # check coerenza
```

Verifica su Supabase Studio che `activities`, `daily_wellness` siano popolate.

## Step 10 — Compila profilo

Apri `CLAUDE.md` § Profilo atleta. Compila tutti i campi. Più sei accurato qui, più
l'agente sarà utile dal giorno 1.

Opzionale, per manutenzione tecnica del repository apri Claude Code:
```bash
cd triathlon-coach
claude  # avvia Claude Code
```

Prima domanda di test: *"Analizza il mio CTL degli ultimi 3 mesi e dimmi in che fase
sono."*

## Step 11 — Healthchecks

1. https://healthchecks.io → crea check "ingest" (every 3h, grace 1h)
2. Crea check "watchdog" (every 1h, grace 15min)
3. Copia URL ping in secret `HEALTHCHECKS_PING_URL_INGEST` etc.

## Verifica finale

```bash
make smoke-test
```

Esegue: ping Supabase, query test, parse Garmin, parse Strava, send Telegram test.
Tutto verde → sei operativo.
