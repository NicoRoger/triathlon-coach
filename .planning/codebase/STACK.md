# Technology Stack
_Last updated: 2026-06-05_ | _Focus: tech_

## Summary

Triathlon Coach AI is a multi-layer system: a Python backend for data ingestion and
analytics, two TypeScript Cloudflare Workers (MCP server + Telegram bot), and a React
dashboard. Python 3.11 runs on GitHub Actions; the two Workers run on Cloudflare's
edge runtime. Supabase (PostgreSQL) is the single source of truth for all structured
data.

---

## Languages

**Primary:**
- Python 3.11 — backend analytics, data ingestion, AI coaching logic, CLI scripts
- TypeScript 5.4 — Cloudflare Workers (MCP server, Telegram bot) and React dashboard

**Secondary:**
- SQL — schema + migrations in `sql/schema.sql` and `migrations/`

---

## Runtime

**Python:**
- Version: 3.11 (pinned in `.github/workflows/ingest.yml` via `actions/setup-python`)
- Package manager: pip
- Lockfile: none (only `requirements.txt`)

**Node / Edge:**
- Node.js 20 (pinned in `deploy-dashboard.yml` via `actions/setup-node`)
- Package manager: npm (lockfile present at `dashboard/package-lock.json`)
- Cloudflare Workers runtime for `workers/mcp-server` and `workers/telegram-bot`
- Wrangler 3.50 for Workers deploy (`wrangler deploy`)

---

## Frameworks

**Frontend:**
- React 18.3 — dashboard UI (`dashboard/src/`)
- Vite 5.2 — build tool and dev server (`dashboard/vite.config.*`)
- Chart.js 4.4 + react-chartjs-2 5.2 — data visualisation
- `@excalidraw/excalidraw` 0.17 — whiteboard/planning canvas

**Backend (Python):**
- Pydantic 2.6 — data validation and schemas (`coach/models/schemas.py`)
- python-dotenv 1.0 — local env loading (`coach/utils/supabase_client.py`)
- pytest 7.4 — test runner (config in `pytest.ini`, tests in `tests/`)

**Edge Workers:**
- `@cloudflare/workers-types` 4.20250401 — TypeScript types for Cloudflare runtime
- Wrangler 3.50 — deploy tooling for both workers

---

## Key Dependencies

**Critical:**
- `supabase>=2.30.0` — Python client for all DB reads/writes (`coach/utils/supabase_client.py`)
- `garminconnect>=0.3.0,<0.3.3` — unofficial Garmin Connect client (`coach/ingest/garmin.py`)
- `anthropic>=0.100.0` — Anthropic Python SDK for LLM calls (`coach/utils/llm_client.py`)
- `google-genai>=1.0.0` — Google Gemini SDK; primary model for high-volume tasks (`coach/utils/llm_client.py`)
- `requests>=2.31` — HTTP client used by Strava ingest and Telegram sender
- `cryptography>=42` — required by garminconnect for OAuth token handling

**Infrastructure:**
- `tzdata>=2024.1` — IANA timezone data for Europe/Rome handling in scripts

---

## LLM Routing

Two AI providers are used with a hybrid routing strategy (`coach/utils/llm_client.py`):

| Provider | Model | Used for |
|----------|-------|----------|
| Google Gemini (free) | `gemini-2.5-flash` | session analysis, pattern extraction, reminders, weekly lessons, proactive questions |
| Anthropic (paid) | `claude-sonnet-4-6` or `claude-haiku-4-5` | modulation decisions, race prediction, post-race analysis, race briefing, weekly narrative |

Budget hard-cap: $5 USD/month. Auto-degrades Sonnet→Haiku above $4.00, blocks non-critical calls above $4.50. Budget tracked in `api_usage` Supabase table (`coach/utils/budget.py`).

---

## Build Tools

- Vite (`dashboard/`) — production build outputs to `dashboard/dist/`
- Wrangler (`workers/mcp-server/`, `workers/telegram-bot/`) — bundles and deploys Workers
- TypeScript 5.4 — compile-time checking across all TS projects (no separate tsconfig detected at root)

---

## Testing

- pytest 7.4 — unit/regression tests in `tests/` directory
- `testpaths = tests` (configured in `pytest.ini`)
- Scripts in `scripts/` are manual smoke-tests, excluded from automated collection

---

## Configuration

**Environment (Python backend):**
- Loaded from `.env` locally via python-dotenv; injected as GitHub Actions secrets in CI
- Key vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GARMIN_SESSION_JSON`,
  `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`,
  `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `HEALTHCHECKS_PING_URL_*`

**Environment (Workers):**
- Set via `wrangler secret put <NAME>`
- MCP server: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `MCP_BEARER_TOKEN`, `GH_PAT_TRIGGER`
- Telegram bot: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

---

## Database

- PostgreSQL via Supabase managed platform
- Extensions: `uuid-ossp`, `pgcrypto`
- Schema defined in `sql/schema.sql`; incremental migrations in `migrations/*.sql`
- JSONB columns used for flexible payloads: `hr_zones_s`, `raw_payload`, `splits`, `weather`
- All timestamps in UTC (TIMESTAMPTZ); timezone conversion to Europe/Rome handled in application layer
- RLS enabled (single-user policy)

---

## Infrastructure / Deployment

**GitHub Actions** (`.github/workflows/`):
- `ingest.yml` — runs every 3 hours on `ubuntu-latest`, syncs Garmin → Supabase, triggers analytics and coaching pipeline
- `morning-briefing.yml` — daily at 06:20 UTC, sends Telegram brief
- `deploy-dashboard.yml` — on push to `main` (dashboard paths): builds with Vite, deploys to Cloudflare Pages
- `weekly-review.yml`, `proactive-check-in.yml`, `proactive-reminders.yml`, `pattern-extraction.yml`, `backfill-analyses.yml`, `db_cleanup.yml`, `dr-snapshot.yml`, `keepalive.yml`, `watchdog.yml`, `debrief-reminder.yml`

**Cloudflare:**
- Dashboard deployed to Cloudflare Pages (`triathlon-dashboard` project)
- MCP server deployed as Cloudflare Worker (`mcp-server`)
- Telegram bot deployed as Cloudflare Worker (`telegram-bot`) with KV namespace for update dedup

---

## Gaps & Unknowns

- No `pyproject.toml` or `setup.py` — project is not a proper Python package; imports rely on `PYTHONPATH=.`
- No pinned Python lockfile (pip-compile or Poetry) — dependency versions may drift across environments
- No frontend test framework detected (no jest/vitest config in `dashboard/`)
- TypeScript `tsconfig.json` not verified at root or in worker directories
- Strava sync is commented out in `ingest.yml` — integration exists in code but disabled in CI
