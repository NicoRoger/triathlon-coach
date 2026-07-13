# Inventario segreti — dove vivono e come si ruotano

> WP4. I segreti vivono in **3 posti scollegati**: dimenticarne uno durante
> una rotazione ha già rotto il sistema una volta (GH_PAT_TRIGGER scaduto →
> force_sync 403 + brief delle 5 non dispatchato). Questo file è la mappa.

## 1. GitHub Actions (repo → Settings → Secrets and variables → Actions)

| Secret | Usato da | Note |
|---|---|---|
| `SUPABASE_URL` | tutti i workflow Python | URL progetto Supabase |
| `SUPABASE_SERVICE_KEY` | tutti i workflow Python | service_role — bypassa RLS. Con la ANON key le query tornano [] in silenzio |
| `TELEGRAM_BOT_TOKEN` | ingest, briefing, reminders, watchdog… | da @BotFather |
| `TELEGRAM_CHAT_ID` | idem | chat privata di Nicolò |
| `GARMIN_SESSION_JSON` | ingest | sessione OAuth garminconnect; rigenerare con `scripts/garmin_first_login.py` se scade |
| `ANTHROPIC_API_KEY` | ingest (modulation), weekly, pattern | budget hard €5/mese |
| `GEMINI_API_KEY` | ingest, pattern, reminders | free tier |
| `CF_WORKERS_API_TOKEN` | deploy-workers | token Cloudflare scope "Edit Cloudflare Workers" |
| `CF_PAGES_API_TOKEN` | deploy-dashboard (+ fallback workers) | scope Pages |
| `CF_ACCOUNT_ID` | deploy-* | account id Cloudflare (non segreto in senso stretto) |
| `HC_BRIEFING` / `HC_GARMIN` / `HC_STRAVA` / `HC_WATCHDOG` | ping healthchecks.io | opzionali |
| `SHOULDER_ACTIVE` / `PLANTAR_ACTIVE` | briefing | flag legacy infortuni (lo stato vero è in active_constraints) |
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` / `STRAVA_REFRESH_TOKEN` | ingest (step commentato) | dormienti |
| `DR_ENCRYPTION_KEY` | dr-snapshot | cifra gli snapshot |
| `MCP_URL` | smoke-integration | URL del worker mcp-server (opzionale, per il ping) |

## 2. Cloudflare Workers (`wrangler secret put <NAME>` nella dir del worker, o dashboard → Workers → Settings → Variables)

### workers/mcp-server
| Secret | Note |
|---|---|
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | come sopra |
| `MCP_BEARER_TOKEN` | master key dei tool MCP **e** chiave HMAC dell'OAuth: ruotarlo invalida i code in volo e scollega Claude.ai finché non riautorizzi |
| `GH_PAT_TRIGGER` | PAT GitHub scope repo+workflow: force_garmin_sync + dispatch brief 5:00. **Ha una scadenza**: segnarsela |
| `OAUTH_CONNECT_SECRET` | **OBBLIGATORIO (fail-closed WP4)**: senza, il flusso OAuth è chiuso. Genera: `openssl rand -base64 32` |

### workers/telegram-bot
| Secret | Note |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_CHAT_ID` | come sopra (nomi diversi: ALLOWED_CHAT_ID qui, CHAT_ID su GitHub) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | come sopra |
| `TELEGRAM_WEBHOOK_SECRET` | **OBBLIGATORIO (fail-closed WP4)**: senza, il bot rifiuta tutti i webhook (503). Va registrato ANCHE su Telegram: `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<WORKER_URL>&secret_token=<SECRET>"` |

## 3. Locale (`.env`, mai committato)

Sviluppo: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (+ eventuali API key per test manuali). Caricato da python-dotenv.

## Procedure di rotazione

- **SUPABASE_SERVICE_KEY**: rigenerare su Supabase → aggiornare in TUTTI E TRE i posti (GitHub, entrambi i worker, .env). Fino all'allineamento i job falliranno con 401 espliciti (non silenzioso).
- **TELEGRAM_BOT_TOKEN**: @BotFather → aggiornare GitHub + worker telegram-bot → rifare `setWebhook` (il webhook è legato al token) **col secret_token**.
- **GH_PAT_TRIGGER**: nuovo PAT (repo+workflow) → `wrangler secret put GH_PAT_TRIGGER` nel mcp-server (o dashboard). Sintomo di scadenza: force_sync 403 + brief 5:00 assente.
- **MCP_BEARER_TOKEN**: nuovo valore → secret sul worker → riautorizzare la connessione MCP su Claude.ai (l'OAuth ridà il token nuovo).
- **TELEGRAM_WEBHOOK_SECRET / OAUTH_CONNECT_SECRET**: nuovo valore → secret sul worker; per il webhook rifare anche `setWebhook`.

Dopo OGNI rotazione: lancia il workflow `smoke-integration` (manuale) per verifica.
