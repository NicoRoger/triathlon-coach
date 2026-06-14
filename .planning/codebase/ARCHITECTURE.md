# Architecture

_Last updated: 2026-06-05_ | _Focus: arch_

## Summary

Triathlon-coach is a personal AI coaching system for a single athlete. It is a hybrid architecture: a Python backend handles deterministic analytics, data ingestion from Garmin/Strava, LLM calls, and scheduled automation via GitHub Actions; two Cloudflare Workers (TypeScript) handle Telegram bot interactions and an MCP server that exposes data to Claude.ai via JSON-RPC; Supabase is the single source-of-truth database; a Vite/React dashboard provides a read-only training view. The system is event-driven (GitHub Actions schedules → Python scripts) with no persistent Python HTTP server.

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Human Interfaces                               │
│  Claude.ai (web/mobile)          Telegram Bot                        │
│  via MCP tool calls              commands + inline buttons            │
└────────────┬───────────────────────────────┬─────────────────────────┘
             │ JSON-RPC / HTTP               │ Webhook
             ▼                               ▼
┌────────────────────────┐   ┌───────────────────────────────────────┐
│  MCP Server            │   │  Telegram Bot Worker                  │
│  Cloudflare Worker     │   │  Cloudflare Worker                    │
│  `workers/mcp-server/` │   │  `workers/telegram-bot/`              │
│  – tool definitions    │   │  – /brief /log /rpe /debrief /status  │
│  – Supabase queries    │   │  – reply threading + confirmations     │
│  – commit_plan_change  │   │  – proactive question buttons         │
└────────────┬───────────┘   └────────────────┬──────────────────────┘
             │                                │
             ▼                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Supabase (PostgreSQL)                              │
│  activities · daily_wellness · daily_metrics · planned_sessions      │
│  subjective_logs · session_analyses · plan_modulations               │
│  beliefs · recommendations · bot_messages · pending_confirmations    │
│  health · mesocycles · physiology_zones · proactive_questions        │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
┌──────────────────────┐  ┌──────────────────────────────────────────┐
│  Ingest Layer        │  │  Analytics + Coaching Layer (Python)     │
│  `coach/ingest/`     │  │  `coach/analytics/`  `coach/coaching/`  │
│  – garmin.py         │  │  – pmc.py (CTL/ATL/TSB EWMA)            │
│  – strava.py         │  │  – readiness.py (score + flags)         │
│  (upsert, idempotent)│  │  – belief_engine.py (Bayesian beliefs)  │
└──────────────────────┘  │  – post_session_analysis.py             │
                          │  – modulation.py (mid-week proposals)   │
                          │  – fitness_test_processor.py            │
                          │  – weekly_analysis.py                   │
                          └──────────────────────────────────────────┘
             ▲
             │  GitHub Actions (cron schedules)
┌────────────┴──────────────────────────────────────────────────────┐
│  Scheduled Workflows  `.github/workflows/`                         │
│  ingest.yml · morning-briefing.yml · weekly-review.yml            │
│  pattern-extraction.yml · proactive-check-in.yml                  │
│  proactive-reminders.yml · db_cleanup.yml · watchdog.yml          │
│  dr-snapshot.yml · backfill-analyses.yml · keepalive.yml          │
└───────────────────────────────────────────────────────────────────┘
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

**Ingest Layer:**
- Purpose: Fetch external data (Garmin Connect, Strava) and write to Supabase
- Location: `coach/ingest/`
- Idempotent via upsert on `(external_id, source)`
- Depends on: `coach/models/schemas.py`, `coach/utils/supabase_client.py`

**Analytics Layer:**
- Purpose: Pure deterministic computations — PMC (CTL/ATL/TSB via EWMA), composite readiness score, HRV z-score flags
- Location: `coach/analytics/`
- Zero LLM calls; all functions are testable and deterministic
- Depends on: nothing external; pure Python + Supabase data

**Coaching Layer:**
- Purpose: LLM-powered intelligence: post-session analysis, mid-week plan modulation proposals, race prediction, fitness test processing, weekly narrative
- Location: `coach/coaching/`
- Always writes results back to Supabase; sends Telegram notifications
- LLM calls routed through `coach/utils/llm_client.py`

**Planning Layer:**
- Purpose: Generate daily morning briefs (rule-based, zero LLM cost)
- Location: `coach/planning/`
- Reads `planned_sessions`, `daily_wellness`, `daily_metrics`, `activities` from Supabase
- Sends formatted brief to Telegram

**Decision Layer:**
- Purpose: Arbitrate competing coaching priorities with a strict 9-level hierarchy
- Location: `coach/decision/priority_engine.py`
- Priority 1 (safety) always wins; Priorities 1-3 are hard constraints

**Cognition Layer (facade):**
- Purpose: Semantic grouping of inference, prediction, prescription — re-exports from analytics/coaching/decision
- Location: `coach/cognition/inference/`, `coach/cognition/prediction/`, `coach/cognition/prescription/`
- Does not contain logic; is an organizational namespace

**Workers (Cloudflare):**
- Purpose: Edge-deployed stateless HTTP handlers for Telegram webhooks and MCP tool calls
- Location: `workers/mcp-server/`, `workers/telegram-bot/`
- Auth: Telegram uses `TELEGRAM_ALLOWED_CHAT_ID` allowlist; MCP uses `MCP_BEARER_TOKEN`
- State: KV Namespace used for Telegram dedup on `update_id`

## Data Flow

### Daily Ingest → Brief

1. GitHub Actions `ingest.yml` triggers `python -m coach.ingest.garmin` (`coach/ingest/garmin.py`)
2. Garmin data upserted to `activities`, `daily_wellness`, `daily_metrics` tables
3. GitHub Actions `morning-briefing.yml` triggers `python -m coach.planning.briefing` (`coach/planning/briefing.py`)
4. Briefing reads Supabase, runs readiness score via `coach/analytics/readiness.py`, formats text
5. HTTP POST to Telegram Bot API → athlete receives morning brief

### Post-Session Analysis

1. After ingest, `coach/coaching/post_session_analysis.py` detects new activity
2. Loads skill prompt from `skills/session_analysis.md`
3. Calls LLM (Gemini via `coach/utils/llm_client.py`) with activity data + planned session + historical
4. Saves analysis to `session_analyses` table
5. If critical keywords detected → `coach/coaching/modulation.py` generates mid-week modulation proposal
6. Modulation saved to `plan_modulations`, sent to Telegram with inline buttons for athlete confirmation
7. Athlete taps confirm → Telegram Bot Worker writes to `planned_sessions`

### Claude.ai Human-in-the-Loop

1. Athlete opens Claude.ai (web or mobile) with coach system prompt loaded
2. Claude calls MCP tools (e.g. `get_weekly_context`, `get_session_review_context`)
3. MCP Worker queries Supabase, returns JSON context
4. Claude synthesizes and proposes plan changes
5. Athlete confirms → Claude calls `commit_plan_change` MCP tool
6. MCP Worker triggers GitHub Actions via `GH_PAT_TRIGGER` dispatch OR writes directly to Supabase

### Fitness Test Processing

1. Athlete completes test with exact Garmin activity name as prescribed
2. Ingest picks up activity; `coach/coaching/fitness_test_processor.py` detects test type via name
3. Extracts result from splits or activity fallback; calculates zones
4. Updates `physiology_zones` table; patches `CLAUDE.md` field via `scripts/update_claude_md_status.py`
5. Sends Telegram notification with result + zones

## Key Abstractions

**Skills (`skills/*.md`):**
- Markdown files loaded as LLM system prompts at runtime
- Each corresponds to a coaching workflow: `session_analysis.md`, `fitness_test.md`, `weekly_review.md`, etc.
- Loaded by Python modules via `Path(__file__).resolve().parent.parent.parent / "skills" / "*.md"`

**LLM Routing:**
- `coach/utils/llm_client.py` routes by `purpose` string
- Gemini (free): high-volume tasks (`session_analysis`, `pattern_extraction`, `proactive_question`)
- Anthropic API (paid, budget-gated): critical decisions (`modulation`, `race_prediction`, `weekly_analysis`)
- Claude Pro via Claude.ai: human-in-the-loop workflows (not in code, handled interactively)

**Budget Cap:**
- Hard limit €5/month; tracked in `coach/utils/budget.py`
- `BudgetExceededError` raised and caught in all LLM-calling paths
- Auto-degradation from Sonnet → Haiku before hard block at $4.80

**Beliefs:**
- `coach/analytics/belief_engine.py` stores Bayesian athlete beliefs in `beliefs` table
- Lifecycle: `create_belief` → `reinforce_belief` / `contradict_belief` → `decay_old_beliefs`
- Actionable beliefs feed the `DecisionContext` in `coach/decision/priority_engine.py`

## Entry Points

**Scheduled (GitHub Actions):**
- `python -m coach.ingest.garmin` — daily data sync
- `python -m coach.planning.briefing` — morning brief
- `python -m coach.coaching.post_session_analysis --recent` — post-session analysis
- `python -m coach.coaching.pattern_extraction` — weekly pattern extraction
- `python -m coach.coaching.weekly_analysis` — weekly narrative
- `python -m coach.coaching.proactive_questions` — 3x/week proactive check-ins
- `python -m scripts.watchdog` — health monitoring alerts

**Interactive (Telegram):**
- Commands: `/brief`, `/log`, `/rpe`, `/debrief`, `/status`, `/budget`, `/undo`, `/history`, `/help`
- Entry: `workers/telegram-bot/src/index.ts` webhook handler

**Interactive (Claude.ai):**
- MCP tools via `workers/mcp-server/src/index.ts`
- Tools: `get_weekly_context`, `get_race_context`, `get_session_review_context`, `get_daily_brief`, `commit_plan_change`, `get_physiology_zones`, `trigger_ingest`, etc.

**Manual/Operational:**
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
**What happens:** Any LLM call in `coach/analytics/` or `coach/planning/briefing.py`
**Why it's wrong:** Analytics must be deterministic and testable; LLM costs would accrue on every brief
**Do this instead:** Put LLM calls in `coach/coaching/`; analytics returns structured data that coaching layer interprets

### Writing to `planned_sessions` without confirmation
**What happens:** Directly upserting planned sessions from analysis or modulation code
**Why it's wrong:** Violates the athlete-decides principle; athlete may have context the system lacks
**Do this instead:** Write to `plan_modulations` with status `pending`; wait for athlete confirm via Telegram or MCP `commit_plan_change`

### Bypassing budget gating
**What happens:** Calling Anthropic API directly without `coach/utils/llm_client.py`
**Why it's wrong:** Hard monthly budget cap; untracked calls can exhaust budget silently
**Do this instead:** Always use `llm_client.call(purpose=..., ...)` which enforces routing and budget

## Error Handling

**Strategy:** Defensive — catch exceptions at workflow boundaries, log to Supabase `health` table, alert via Telegram.

**Patterns:**
- `BudgetExceededError` caught in all LLM paths; logs warning and skips LLM step gracefully
- `record_health(component, status)` called at end of every scheduled job (`coach/utils/health.py`)
- Watchdog (`scripts/watchdog.py`) reads `health` table and alerts if any component is stale beyond threshold
- Telegram Bot uses KV dedup on `update_id` to prevent duplicate processing of retried webhooks

## Cross-Cutting Concerns

**Logging:** Python `logging` module; log level via env. Telegram used as ops notification channel.
**Validation:** Pydantic models in `coach/models/schemas.py` validate before Supabase writes.
**Timezone:** `coach/utils/dt.py` provides `today_rome()` — all date logic in Europe/Rome timezone.
**Health monitoring:** Every scheduled job writes to `health` table; watchdog checks staleness.
**DR (Disaster Recovery):** `scripts/dr_snapshot.py` and `scripts/dr_restore.py`; daily snapshot workflow in `.github/workflows/dr-snapshot.yml`.

---

_Architecture analysis: 2026-06-05_
