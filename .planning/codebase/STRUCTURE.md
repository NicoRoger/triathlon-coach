# Codebase Structure

_Last updated: 2026-06-05_ | _Focus: arch_

## Summary

The project is organized as a monorepo with a clear layer-by-layer Python backend (`coach/`), two TypeScript Cloudflare Workers (`workers/`), a Vite/React dashboard (`dashboard/`), GitHub Actions workflows (`.github/workflows/`), operational scripts (`scripts/`), and database migrations (`migrations/`). Python code is split by architectural layer (ingest, analytics, coaching, planning, decision, cognition, models, utils). Skills are Markdown files consumed as LLM prompts at runtime.

## Directory Layout

```
triathlon-coach/
├── coach/                  # Core Python backend package
│   ├── analytics/          # Deterministic computations (PMC, readiness, HRV, beliefs)
│   ├── coaching/           # LLM-powered coaching logic (analysis, modulation, tests)
│   ├── cognition/          # Semantic facade: inference/, prediction/, prescription/
│   │   ├── inference/      # Re-exports belief engine + uncertainty
│   │   ├── prediction/     # Re-exports outcome tracking + test/race prediction
│   │   └── prescription/   # Re-exports priority engine + modulation + adaptive planner
│   ├── decision/           # Priority arbitration engine
│   ├── ingest/             # Garmin + Strava data fetching → Supabase upsert
│   ├── models/             # Pydantic schemas mirroring DB tables
│   ├── planning/           # Rule-based morning briefing generator
│   └── utils/              # Shared utilities: Supabase client, LLM client, budget, dt, health
├── workers/
│   ├── mcp-server/         # Cloudflare Worker: JSON-RPC MCP tool server for Claude.ai
│   │   └── src/index.ts    # All MCP logic in single file
│   └── telegram-bot/       # Cloudflare Worker: Telegram webhook handler
│       └── src/index.ts    # All bot logic in single file
├── dashboard/              # Vite + React read-only training dashboard
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts          # Supabase query helpers
│   │   ├── main.tsx
│   │   └── components/     # React UI components
│   └── dist/               # Built assets (committed for Cloudflare Pages deploy)
├── scripts/                # Operational Python scripts (not importable as package)
├── skills/                 # Markdown skill prompts loaded as LLM system context
├── sql/                    # Full schema DDL + incremental migrations
│   ├── schema.sql          # Canonical full schema
│   └── migrations/         # (see migrations/ below)
├── migrations/             # Dated SQL migration files applied to Supabase
├── docs/                   # Long-term memory documents read by coach agent
├── tests/                  # pytest test suite
│   └── manual/             # Manual test scripts (not run in CI)
├── .github/workflows/      # GitHub Actions scheduled and deployment workflows
├── .planning/              # GSD planning artifacts (not committed to main)
├── CLAUDE.md               # Coach agent system prompt + athlete profile
├── Makefile                # Developer shortcuts
├── requirements.txt        # Python dependencies
└── pytest.ini              # pytest configuration
```

## Directory Purposes

**`coach/analytics/`:**
- Purpose: Pure deterministic Python — PMC calculation, readiness scoring, HRV flagging, belief engine, uncertainty tracking
- Key files: `pmc.py`, `readiness.py`, `daily.py`, `belief_engine.py`, `belief_guardrails.py`, `uncertainty.py`, `risk.py`
- Rule: Zero LLM calls here

**`coach/coaching/`:**
- Purpose: LLM-powered coaching workflows triggered by scheduled jobs
- Key files: `post_session_analysis.py`, `modulation.py`, `fitness_test_processor.py`, `weekly_analysis.py`, `pattern_extraction.py`, `proactive_questions.py`, `proactive_reminders.py`, `race_mental.py`, `adaptive_planner.py`, `outcome_verification.py`, `decision_audit.py`, `hypothesis.py`, `test_prediction.py`, `test_scheduler.py`, `race_calendar_optimizer.py`, `extract_beliefs_from_observations.py`

**`coach/planning/`:**
- Purpose: Generate morning briefing text (rule-based, zero LLM)
- Key files: `briefing.py` (v2, current), `briefing_v1.py` (legacy), `personalized_insert.py`

**`coach/decision/`:**
- Purpose: Priority arbitration — resolves competing coaching signals into a single decision with ranked tradeoffs
- Key files: `priority_engine.py`

**`coach/cognition/`:**
- Purpose: Organizational namespace grouping inference, prediction, prescription sub-layers via re-exports
- Contains only `__init__.py` files with re-exports; no original logic

**`coach/models/`:**
- Purpose: Pydantic v2 models as DB schema mirror; used for validation before all Supabase writes
- Key files: `schemas.py` — defines `Activity`, `DailyWellness`, `PlannedSession`, `SubjectiveLog`, `Sport`, `Phase`, `Source` enums, etc.

**`coach/ingest/`:**
- Purpose: Fetch from Garmin Connect and Strava APIs, transform to internal models, upsert to Supabase
- Key files: `garmin.py`, `strava.py`
- Pattern: Idempotent upsert on `(external_id, source)`

**`coach/utils/`:**
- Purpose: Shared infrastructure: DB client, LLM routing, budget tracking, timezone, health reporting, Telegram logging
- Key files: `supabase_client.py`, `llm_client.py`, `budget.py`, `dt.py`, `health.py`, `telegram_logger.py`, `validators.py`

**`workers/mcp-server/src/index.ts`:**
- Purpose: Single-file Cloudflare Worker implementing MCP JSON-RPC protocol
- Exposes tools: `get_weekly_context`, `get_race_context`, `get_session_review_context`, `get_daily_brief`, `commit_plan_change`, `get_physiology_zones`, `trigger_ingest`, and more
- Auth: Bearer token (`MCP_BEARER_TOKEN`)

**`workers/telegram-bot/src/index.ts`:**
- Purpose: Single-file Cloudflare Worker for Telegram webhook
- Commands: `/brief /log /rpe /debrief /status /budget /undo /history /help`
- Features: reply threading, inline button confirmations, proactive question responses, idempotent dedup via KV

**`skills/`:**
- Purpose: Markdown files loaded as LLM system prompts at runtime by coaching modules
- Each file = one coaching skill (e.g. `session_analysis.md`, `fitness_test.md`, `weekly_review.md`)
- Loaded via `Path(__file__).resolve().parent.parent.parent / "skills" / "<name>.md"`

**`scripts/`:**
- Purpose: Standalone operational scripts — not part of `coach` package
- Key files: `watchdog.py`, `dr_snapshot.py`, `dr_restore.py`, `smoke_test.py`, `backfill_metrics.py`, `budget_report.py`, `keepalive.py`, `update_claude_md_status.py`, `validate_skills.py`, `weekly_review_dump.py`

**`migrations/`:**
- Purpose: Ordered SQL migration files applied manually or via CI to Supabase
- Naming: `YYYY-MM-DD-<description>.sql`
- `sql/schema.sql`: canonical full schema DDL

**`docs/`:**
- Purpose: Long-term memory documents read by the coach agent (not by Python code directly)
- Key files: `training_journal.md`, `race_history.md`, `injury_log.md`, `coaching_observations.md`, `elite_training_reference.md`, `FITNESS_TEST_PROTOCOL.md`

**`.github/workflows/`:**
- Purpose: All scheduled automation (cron) and deployment
- Key workflows: `ingest.yml` (daily Garmin sync), `morning-briefing.yml` (daily brief), `weekly-review.yml`, `pattern-extraction.yml`, `proactive-check-in.yml`, `proactive-reminders.yml`, `watchdog.yml`, `dr-snapshot.yml`, `deploy-dashboard.yml`, `keepalive.yml`, `db_cleanup.yml`, `backfill-analyses.yml`, `debrief-reminder.yml`

## Key File Locations

**Entry Points:**
- `coach/ingest/garmin.py` — `python -m coach.ingest.garmin` (scheduled daily)
- `coach/planning/briefing.py` — `python -m coach.planning.briefing` (scheduled daily)
- `workers/mcp-server/src/index.ts` — MCP tool server (Cloudflare Worker, always-on)
- `workers/telegram-bot/src/index.ts` — Telegram bot (Cloudflare Worker, always-on)

**Configuration:**
- `CLAUDE.md` — Athlete profile, methodology, decision rules, coach persona
- `requirements.txt` — Python dependencies
- `pytest.ini` — pytest config
- `.github/workflows/*.yml` — Scheduled job parameters (cron, env vars)

**Core Logic:**
- `coach/analytics/pmc.py` — CTL/ATL/TSB EWMA calculation
- `coach/analytics/readiness.py` — Composite readiness score + HRV flags
- `coach/analytics/belief_engine.py` — Bayesian belief lifecycle
- `coach/decision/priority_engine.py` — 9-level priority arbitration
- `coach/utils/llm_client.py` — LLM routing (Gemini vs Anthropic) + budget gating

**Testing:**
- `tests/` — pytest suite
- `tests/manual/` — manual scripts not run in CI

## Naming Conventions

**Python files:**
- `snake_case.py` throughout
- Module names describe function: `post_session_analysis.py`, `fitness_test_processor.py`, `belief_guardrails.py`

**TypeScript files:**
- Single `index.ts` per Worker — all logic in one file (Cloudflare Worker pattern)

**SQL migrations:**
- `YYYY-MM-DD-<kebab-description>.sql`

**Skills:**
- `<skill_name>.md` in `skills/` — matches the skill name referenced in CLAUDE.md §7

**Docs:**
- Descriptive snake_case: `training_journal.md`, `coaching_observations.md`

## Code Split Strategy

The Python code is split **by architectural layer**, not by feature or domain:
- `ingest/` → data acquisition
- `analytics/` → deterministic computation
- `coaching/` → LLM-powered intelligence
- `planning/` → output generation
- `decision/` → arbitration
- `cognition/` → semantic grouping (facade)
- `models/` → data contracts
- `utils/` → shared infrastructure

This means a full coaching workflow (e.g., post-session analysis) touches `ingest/` → `analytics/` → `coaching/` → `utils/` in sequence, crossing multiple directories.

## Where to Add New Code

**New scheduled coaching feature** (e.g., monthly load summary):
- Logic: `coach/coaching/<feature_name>.py`
- Skill prompt: `skills/<feature_name>.md`
- Workflow: `.github/workflows/<feature_name>.yml`
- Makefile target: add to `Makefile`

**New analytics metric** (deterministic, no LLM):
- Add to `coach/analytics/` as a new function or module
- Write tests in `tests/`

**New MCP tool for Claude.ai:**
- Add tool definition and handler in `workers/mcp-server/src/index.ts`

**New Telegram command:**
- Add command handler in `workers/telegram-bot/src/index.ts`

**New DB table:**
- Add migration: `migrations/YYYY-MM-DD-<description>.sql`
- Update canonical schema: `sql/schema.sql`
- Add Pydantic model: `coach/models/schemas.py`

**New utility:**
- Shared infra → `coach/utils/<name>.py`
- One-off operational script → `scripts/<name>.py`

## Special Directories

**`.planning/`:**
- Purpose: GSD planning artifacts (phase plans, codebase maps)
- Generated: Yes (by GSD commands)
- Committed: No (branch-scoped working artifacts)

**`dashboard/dist/`:**
- Purpose: Pre-built Vite assets for Cloudflare Pages deployment
- Generated: Yes (`npm run build`)
- Committed: Yes (deployed via `deploy-dashboard.yml`)

**`workers/*/node_modules/`:**
- Purpose: Worker dependencies
- Generated: Yes (`npm install`)
- Committed: No

## Gaps & Unknowns

- `coach/cognition/inference/`, `coach/cognition/prediction/`, `coach/cognition/prescription/` contain only `__init__.py` re-exports; no original logic has been implemented in these directories yet — they are structural placeholders.
- `dashboard/src/components/` contents not inspected; component organization unknown.
- `tests/` internal structure not fully inspected; coverage level unknown (see TESTING.md when written).
- Strava ingest (`coach/ingest/strava.py`) appears to be present but the watchdog comment notes it is disabled as "Garmin is single source of truth."

---

_Structure analysis: 2026-06-05_
