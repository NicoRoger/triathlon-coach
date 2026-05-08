# System Status — Snapshot 6 maggio 2026

## Tabelle DB (Supabase Postgres)

| Tabella | Descrizione | Stato |
|---------|-------------|-------|
| `activities` | Attività da Garmin/Strava (swim, bike, run, brick, strength, other) | ✅ Popolata, sync ogni 3h |
| `daily_wellness` | Dati giornalieri: HRV, sonno, body battery, stress, RHR, training status, VO2max | ✅ Popolata, sync ogni 3h |
| `daily_metrics` | Metriche calcolate: CTL/ATL/TSB, HRV z-score, readiness score/label, flags | ✅ Calcolata post-ingest |
| `planned_sessions` | Sessioni pianificate (sport, tipo, durata, descrizione, zone target, calendar_event_id) | ✅ Schema pronto, tool MCP attivo |
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
| `commit_plan_change` | Scrive sessione in planned_sessions (upsert idempotente, supporta calendar_event_id) | ✅ Sì, dopo conferma atleta |
| `force_garmin_sync` | Forza sync Garmin via GitHub Actions dispatch (freshness check 1h + polling 90s) | No (triggera workflow) |

**Totale: 7 tool esposti.**

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
| Delete session | `delete_session.md` | 5.0 |

**Totale: 9 skill files.**

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
| `workers/telegram-bot/` | Bot Telegram (comandi, parsing log, debrief con colonne native) |
| `workers/mcp-server/` | MCP server per Claude.ai (7 tool incl. force_garmin_sync) |

## Test

| File test | Test | Stato |
|-----------|------|-------|
| `tests/test_pmc.py` | 8 test (EWMA, PMC zero/single/steady/fill, TSS stime) | ✅ Pass |
| `tests/test_readiness.py` | 8 test (HRV z-score, flags, readiness override/green/caution) | ✅ Pass |

**16/16 test verdi al 6 maggio 2026.**

## Changelog Step 5.0 (6 maggio 2026)

- **Feature 1**: Tool MCP `force_garmin_sync` + Fase 0 nella weekly review
- **Feature 2**: Esportazione Google Calendar via MCP connector (Fase 6 weekly review, adjust_week aggiornata, nuova skill delete_session, migration SQL `calendar_event_id`, commit_plan_change esteso)
- **Feature 3**: Fix parser debrief nel Telegram bot (colonne native `motivation`, `illness_flag`, `injury_flag` ora popolate)

## Changelog Step 5.1 (8 maggio 2026)

- **Audit completezza Garmin**: inventario completo endpoint, decision matrix per 20+ endpoint → `docs/audit_garmin_completeness_2026-05-07.md`
- **Nuovi endpoint**: `get_training_readiness`, `get_activity_splits`, `get_activity_weather` (3 nuovi, totale 9)
- **Nuovi campi DB**: `daily_wellness.training_readiness_score`, `daily_wellness.avg_sleep_stress`, `activities.splits`, `activities.weather`, `daily_metrics.garmin_training_readiness`
- **Migration**: `migrations/2026-05-08-garmin-completeness.sql`
- **Script**: `scripts/audit_payload_coverage.py` (audit raw_payload), `scripts/reprocess_recent.py` (validazione coverage)
- **Skills aggiornate**: weekly_review (sleep_stress, training_readiness), propose_session (weather race week), race_week_protocol (weather T-2)
- **Rate limiting**: 0.3s sleep tra chiamate per-activity per evitare ban Garmin

## Stato complessivo

Il sistema è operativo per uso quotidiano. Tutti i flussi (ingest → analytics → briefing → debrief → weekly review) sono implementati e testati. Il ciclo di pianificazione settimanale (4.1-4.5) è completo con tool MCP, skill files, workflow e brief race week. Step 5.0 aggiunge sync forzato pre-review, integrazione Google Calendar e fix parser debrief. Step 5.1 aggiunge audit completezza Garmin con 3 nuovi endpoint e 5 nuovi campi DB per dati ad alto valore (readiness, sleep stress, splits, weather).

**Prossimo step:** Step 5.1 Task 1-5 — Test & Hardening (12 test, runbook esteso, smoke test migliorato).
