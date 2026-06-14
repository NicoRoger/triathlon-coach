# External Integrations
_Last updated: 2026-06-05_ | _Focus: tech_

## Summary

The system integrates with six external services: Garmin Connect for primary training
data, Strava as a backup source, Supabase as the managed PostgreSQL backend, Telegram
for athlete notifications and commands, Anthropic and Google Gemini for AI inference,
and Cloudflare for edge compute and static hosting. GitHub Actions orchestrates all
scheduled workflows. Healthchecks.io provides dead-man's-switch monitoring for critical
cron jobs.

---

## APIs & External Services

### Garmin Connect
- **Purpose:** Primary source of training data — activities, wellness, HRV, sleep, body battery, VO2max, training readiness, per-lap splits, activity weather
- **Client:** `garminconnect>=0.3.0,<0.3.3` (unofficial, OAuth1/2)
- **Implementation:** `coach/ingest/garmin.py`
- **Auth:** Session tokens cached as base64 JSON in env var `GARMIN_SESSION_JSON`; initial auth via `scripts/garmin_first_login.py`
- **Endpoints called:**
  - `get_activities_by_date(start, end)`
  - `get_user_summary(date)` — body battery, stress avg, RHR, steps
  - `get_sleep_data(date)` — sleep score, HRV nocturnal, stages, sleep stress
  - `get_hrv_data(date)` — HRV summary and status
  - `get_max_metrics(date)` — VO2max run/bike
  - `get_training_status(date)` — acute/chronic load
  - `get_training_readiness(date)` — Garmin proprietary readiness 0-100
  - `get_activity_splits(id)` — per-km/lap splits
  - `get_activity_weather(id)` — weather during activity
- **Cadence:** Pulled every 3 hours via GitHub Actions `ingest.yml` with 3-retry logic

### Strava
- **Purpose:** Backup activity source (currently disabled in CI, code present)
- **Client:** `requests` (raw REST)
- **Implementation:** `coach/ingest/strava.py`
- **Auth:** OAuth2 refresh-token flow; tokens in env vars `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`; initial setup via `scripts/strava_first_auth.py`
- **Base URL:** `https://www.strava.com/api/v3`
- **Status:** Sync step commented out in `ingest.yml` — available as fallback, not active

### Telegram Bot API
- **Purpose:** Two-way athlete communication — morning briefs, debrief logging, RPE capture, plan confirmations, proactive check-ins, budget alerts, provider fallback alerts
- **Client:** Raw HTTP via `requests` (Python side); Cloudflare Worker (`workers/telegram-bot/`) handles incoming webhooks
- **Implementation:**
  - Outbound: `coach/utils/telegram_logger.py`, `coach/planning/briefing.py`
  - Inbound: `workers/telegram-bot/src/index.ts` (Cloudflare Worker webhook receiver)
- **Auth:** `TELEGRAM_BOT_TOKEN` (bot token), `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_CHAT_ID` (single-user allow-list)
- **Features:** Reply threading, inline keyboards for confirmations, `/brief`, `/log`, `/rpe`, `/debrief`, `/status`, `/budget`, `/undo`, `/history`, `/help`
- **Dedup:** Update dedup via Cloudflare KV namespace (`PROCESSED_UPDATES`, id `9d1822af8eff446e832c004178d578ad`)

---

## Data Storage

### Supabase (PostgreSQL)
- **Purpose:** Single source of truth for all structured data
- **Connection vars:** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (service role) or `SUPABASE_ANON_KEY`
- **Python client:** `supabase>=2.30.0` singleton via `coach/utils/supabase_client.py`
- **TypeScript access:** Direct Supabase REST API calls in MCP Worker (`workers/mcp-server/src/index.ts`) using `Authorization: Bearer` with service key
- **Key tables:**
  - `activities` — completed workouts (Garmin/Strava), with JSONB `splits` and `weather`
  - `daily_wellness` — HRV, sleep, body battery, training readiness (per day)
  - `daily_metrics` — computed CTL/ATL/TSB/HRV z-score/readiness (per day)
  - `planned_sessions` — upcoming training plan with optional `calendar_event_id`
  - `subjective_log` — RPE, illness, injury, debrief notes
  - `mesocycles` — training blocks with phase metadata
  - `api_usage` — Anthropic API call log for budget tracking
  - `health` — ETL component health (last_success, failure_count)
  - `bot_messages` — Telegram message log for reply threading and idempotency
  - `session_analyses` — AI-generated post-session analysis results
  - `plan_modulations` — proactive mid-week plan change proposals
  - `physiology_zones` — current FTP, threshold pace, CSS, LTHR, HRmax (per discipline)
  - `predictions`, `outcomes`, `hypotheses`, `coaching_beliefs`, `decision_audit` — cognitive layer tables
- **Schema:** `sql/schema.sql`; incremental migrations in `migrations/*.sql` (latest: `2026-06-01-resilience-audit.sql`)

### Cloudflare KV
- **Purpose:** Telegram update dedup for the bot Worker
- **Binding:** `PROCESSED_UPDATES` (namespace id `9d1822af8eff446e832c004178d578ad`)
- **Implementation:** `workers/telegram-bot/wrangler.toml`

---

## AI / LLM Providers

### Anthropic
- **Models used:** `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-opus-4-6`
- **Auth:** `ANTHROPIC_API_KEY`
- **Implementation:** `coach/utils/llm_client.py` — `LLMClient` class
- **Features:** Prompt caching (ephemeral, `cache_control`), budget-aware model selection, auto-downgrade Sonnet→Haiku above $4.00 spend, hard block above $4.80
- **Purposes routed here:** modulation, race_prediction, post_race_analysis, race_briefing, weekly_analysis

### Google Gemini
- **Model:** `gemini-2.5-flash`
- **Auth:** `GEMINI_API_KEY`
- **SDK:** `google-genai>=1.0.0`
- **Implementation:** `coach/utils/llm_client.py` — `GeminiClient` class
- **Purposes routed here:** session_analysis, post_session_analysis, pattern_extraction, reminder_generation, verification_citations, weekly_lesson, proactive_question, communication_text
- **Failover:** If Gemini call fails, `HybridClient` automatically falls back to Anthropic Haiku and sends a Telegram alert

---

## Claude.ai Web (MCP Connector)
- **Purpose:** Human-in-the-loop coaching interface — Claude.ai (Pro) connects to the MCP Worker as a custom connector, giving the coach agent read access to athlete data and the ability to propose/commit plan changes
- **Implementation:** `workers/mcp-server/src/index.ts`
- **Protocol:** JSON-RPC 2.0 over HTTPS
- **Auth:** OAuth 2.0 minimal (single-user), PKCE flow; bearer token `MCP_BEARER_TOKEN`
- **Tools exposed:** `get_weekly_context`, `get_race_context`, `get_session_review_context`, `get_upcoming_plan`, `get_recent_metrics`, `get_planned_session`, `get_activity_history`, `query_subjective_log`, `propose_plan_change`, `commit_plan_change`, `get_physiology_zones`, `get_technique_history`, `force_garmin_sync`, `commit_mesocycle`, `delete_planned_session`, `commit_subjective_log`, `get_health`

---

## CI/CD & Hosting

### GitHub Actions
- **Purpose:** Scheduled automation orchestrator for all backend jobs
- **Workflows:** 13 workflows in `.github/workflows/`
- **Key schedules:**
  - `ingest.yml` — every 3 hours (Garmin sync + analytics pipeline)
  - `morning-briefing.yml` — 06:20 UTC daily (Telegram brief)
  - `weekly-review.yml` — weekly narrative
  - `dr-snapshot.yml` — disaster recovery snapshots
  - `watchdog.yml` — health monitor
- **GitHub API usage:** `GH_PAT_TRIGGER` PAT (scope: `repo` + `workflow`) used by MCP server's `force_garmin_sync` tool to trigger `workflow_dispatch` on `ingest.yml`
- **Secrets storage:** All credentials stored as GitHub Actions repository secrets

### Cloudflare Pages
- **Purpose:** Dashboard hosting
- **Project:** `triathlon-dashboard`
- **Deploy:** `wrangler pages deploy dist` triggered by `deploy-dashboard.yml` on push to `main`
- **Auth:** `CF_PAGES_API_TOKEN`, `CF_ACCOUNT_ID`

### Cloudflare Workers
- **Projects:** `mcp-server`, `telegram-bot`
- **Compatibility date:** `2025-04-01`
- **Observability:** enabled in both `wrangler.toml` files (Cloudflare built-in logging)

---

## Monitoring & Observability

### Healthchecks.io
- **Purpose:** Dead-man's-switch monitoring for critical scheduled jobs
- **Implementation:** HTTP ping at job success/failure via `HEALTHCHECKS_PING_URL_*` env vars
- **Monitored jobs:** Garmin sync (`HC_GARMIN`), Strava sync (`HC_STRAVA`), morning briefing (`HC_BRIEFING`)
- **Code:** `coach/utils/health.py` (`record_health()`), called from ingest modules

### Internal Health Table
- **Purpose:** Component-level ETL health tracking
- **Implementation:** `health` table in Supabase, upserted by `record_health()` after each ingest run
- **Accessed via:** MCP tool `get_health` and `scripts/etl_health_check.py`

### Telegram Alerts
- **Purpose:** Real-time operator alerts for failures and budget warnings
- **Triggers:** Budget threshold crossings, Gemini→Anthropic provider fallback, ETL failures, watchdog anomalies

---

## Webhooks & Callbacks

**Incoming:**
- Telegram webhook → `workers/telegram-bot/` Cloudflare Worker (POST from Telegram servers)

**Outgoing:**
- Healthchecks.io ping URLs (HTTP GET on job success/failure)
- Telegram Bot API (HTTP POST to `api.telegram.org`)
- GitHub Actions API (HTTP POST `workflow_dispatch` for `force_garmin_sync`)
- Strava OAuth token refresh (HTTP POST to `https://www.strava.com/oauth/token`)

---

## Environment Variables Reference

| Variable | Used by | Purpose |
|----------|---------|---------|
| `SUPABASE_URL` | Python + Workers | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Python + Workers | Supabase service role key |
| `SUPABASE_ANON_KEY` | Python (fallback) | Supabase anon key |
| `GARMIN_SESSION_JSON` | Python | Base64 Garmin OAuth tokens |
| `STRAVA_CLIENT_ID` | Python | Strava app client ID |
| `STRAVA_CLIENT_SECRET` | Python | Strava app secret |
| `STRAVA_REFRESH_TOKEN` | Python | Strava OAuth refresh token |
| `ANTHROPIC_API_KEY` | Python | Anthropic API access |
| `GEMINI_API_KEY` | Python | Google Gemini API access |
| `TELEGRAM_BOT_TOKEN` | Python + Worker | Telegram bot credential |
| `TELEGRAM_CHAT_ID` | Python | Outbound target chat ID |
| `TELEGRAM_ALLOWED_CHAT_ID` | Worker | Inbound allowlist chat ID |
| `MCP_BEARER_TOKEN` | MCP Worker | Claude.ai connector auth |
| `GH_PAT_TRIGGER` | MCP Worker | GitHub workflow dispatch PAT |
| `HEALTHCHECKS_PING_URL_*` | Python | Healthchecks.io ping URLs |
| `SHOULDER_ACTIVE` | Python | Injury flag for brief personalization |
| `PLANTAR_ACTIVE` | Python | Injury flag for brief personalization |

---

## Gaps & Unknowns

- Google Calendar integration is referenced in `CLAUDE.md` (§10: `calendar_event_id` column) and in MCP tool `commit_plan_change`, but no Google Calendar API client or credentials are present in code — integration appears planned but not implemented
- Strava sync is disabled in CI (`ingest.yml`) with the step commented out; unclear if currently tested
- No error tracking service (e.g. Sentry) is integrated; errors surface only via Telegram alerts and GitHub Actions logs
- Cloudflare Workers observability is enabled but specific dashboards/alerts are not configured in-repo
