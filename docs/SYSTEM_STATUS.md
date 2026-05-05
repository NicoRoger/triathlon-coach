# System Status — Snapshot 5 maggio 2026

## Tabelle DB (Supabase Postgres)

| Tabella | Descrizione | Stato |
|---------|-------------|-------|
| `activities` | Attività da Garmin/Strava (swim, bike, run, brick, strength, other) | ✅ Popolata, sync ogni 3h |
| `daily_wellness` | Dati giornalieri: HRV, sonno, body battery, stress, RHR, training status, VO2max | ✅ Popolata, sync ogni 3h |
| `daily_metrics` | Metriche calcolate: CTL/ATL/TSB, HRV z-score, readiness score/label, flags | ✅ Calcolata post-ingest |
| `planned_sessions` | Sessioni pianificate (sport, tipo, durata, descrizione, zone target) | ✅ Schema pronto, tool MCP attivo |
| `subjective_log` | Log soggettivi: RPE, malattia, infortuni, debrief serale, note libere | ✅ Popolata via Telegram bot |
| `health` | Health check per componente (last_success_at, failure_count) | ✅ Monitorata da watchdog |

## GitHub Actions — Workflow attivi

| Workflow | File | Schedule | Funzione |
|----------|------|----------|----------|
| `ingest` | `ingest.yml` | Ogni 3h (`0 */3 * * *`) | Pull Garmin + compute daily metrics |
| `morning-briefing` | `morning-briefing.yml` | 06:30 Rome (`30 5 * * *`) | Brief mattutino rule-based → Telegram |
| `debrief-reminder` | `debrief-reminder.yml` | 21:30 Rome (`30 19 * * *`) | Reminder debrief serale → Telegram |
| `watchdog` | `watchdog.yml` | Ogni ora (`:15`) | Health check componenti → alert se anomalia |
| `dr-snapshot` | `dr-snapshot.yml` | 02:00 UTC (`0 2 * * *`) | Snapshot DB cifrato + commit ref |
| `keepalive` | `keepalive.yml` | 12:00 UTC (`0 12 * * *`) | Ping Supabase anti-pause |
| `weekly-review` | `weekly-review.yml` | Domenica 19:00 Rome (`0 17 * * 0`) | Reminder weekly review → Telegram |

**Totale: 7 workflow attivi.**

## Tool MCP esposti (workers/mcp-server/src/index.ts)

| Tool | Descrizione | Scrive su DB? |
|------|-------------|---------------|
| `get_recent_metrics` | daily_metrics ultimi N giorni (CTL/ATL/TSB/HRV) | No |
| `get_planned_session` | Sessione pianificata per data | No |
| `get_activity_history` | Attività completate, filtrabili per sport | No |
| `query_subjective_log` | Log soggettivi (RPE, malattia, infortuni, note) | No |
| `propose_plan_change` | Propone modifica piano (NON scrive) | No |
| `commit_plan_change` | Scrive sessione in planned_sessions (upsert idempotente) | ✅ Sì, dopo conferma atleta |

**Totale: 6 tool esposti.**

## Skill files (skills/)

| Skill | File | Aggiunto in step |
|-------|------|-----------------|
| Query metrics | `query_metrics.md` | 4.0 (originale) |
| Propose session | `propose_session.md` | 4.0 (originale) |
| Adjust week | `adjust_week.md` | 4.0 (originale) |
| Generate mesocycle | `generate_mesocycle.md` | 4.0 (originale) |
| Log debrief | `log_debrief.md` | 4.0 (originale) |
| Weekly review | `weekly_review.md` | 4.2 |
| Race week protocol | `race_week_protocol.md` | 4.4 |
| Race prediction | `race_prediction.md` | 4.4 |

**Totale: 8 skill files.**

## Moduli Python (coach/)

| Modulo | Funzione |
|--------|----------|
| `coach/ingest/garmin.py` | Sync Garmin Connect → Supabase |
| `coach/ingest/strava.py` | Sync Strava → Supabase (commentato in workflow, pronto) |
| `coach/analytics/pmc.py` | PMC (CTL/ATL/TSB), stime TSS per sport |
| `coach/analytics/readiness.py` | Readiness score composito, flag deterministici |
| `coach/analytics/daily.py` | Pipeline daily metrics post-ingest |
| `coach/planning/briefing.py` | Brief mattutino rule-based (v2 narrativo, race week mode) |
| `coach/utils/supabase_client.py` | Client Supabase singleton |
| `coach/utils/health.py` | Record health check |

## Cloudflare Workers

| Worker | Funzione |
|--------|----------|
| `workers/telegram-bot/` | Bot Telegram (comandi, parsing log, debrief) |
| `workers/mcp-server/` | MCP server per Claude.ai (6 tool) |

## Test

| File test | Test | Stato |
|-----------|------|-------|
| `tests/test_pmc.py` | 8 test (EWMA, PMC zero/single/steady/fill, TSS stime) | ✅ Pass |
| `tests/test_readiness.py` | 8 test (HRV z-score, flags, readiness override/green/caution) | ✅ Pass |

**16/16 test verdi al 5 maggio 2026.**

## Stato complessivo

Il sistema è operativo per uso quotidiano. Tutti i flussi (ingest → analytics → briefing → debrief → weekly review) sono implementati e testati. Il ciclo di pianificazione settimanale (4.1-4.5) è completo con tool MCP, skill files, workflow e brief race week.

**Prossimo step:** Step 5 — esportazione workout strutturati su Garmin Connect (post test fitness giugno 2026).
