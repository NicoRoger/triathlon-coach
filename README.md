# Triathlon Coach AI

Sistema agentico personale per il ritorno al triathlon élite. Cloud-first, costo €0
oltre la subscription Claude Pro già attiva.

**Stato: v1.0 — operativo per uso quotidiano.** Step 1-4 completati. Il sistema ingesta dati da Garmin ogni 3h, genera brief mattutino, riceve debrief serale, espone 6 tool MCP per il coach conversazionale, e supporta la pianificazione settimanale con ciclo review → proposta → commit.

## Documentazione

| Documento | Contenuto |
|-----------|-----------|
| [USER_GUIDE.md](docs/USER_GUIDE.md) | Come usare il sistema giorno per giorno |
| [SETUP.md](docs/SETUP.md) | Setup iniziale (~90 min la prima volta) |
| [RUNBOOK.md](docs/RUNBOOK.md) | Operatività quotidiana e troubleshooting |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architettura completa, flussi, failure mode |
| [SYSTEM_STATUS.md](docs/SYSTEM_STATUS.md) | Snapshot stato sistema al 5 maggio 2026 |
| [E2E_TEST_LOG.md](docs/E2E_TEST_LOG.md) | Procedura test end-to-end weekly planning |

## Filosofia in 3 righe

1. **Supabase = stato** (single source of truth operativo)
2. **GitHub = memoria + DR** (journal versionato, snapshot DB cifrato)
3. **Claude.ai/Code = intelligenza** (agente conversazionale, niente loop API a pagamento)

PC fisso, Macbook in trasferta e telefono sono tutti **client sostituibili**. Niente
single point of failure su hardware locale.

## Layer

| Layer | Tecnologia | Costo | Funzione |
|-------|------------|-------|----------|
| Ingest | GitHub Actions + `garminconnect` + `stravalib` | €0 | Pull dati ogni 3h |
| Storage | Supabase (Postgres) | €0 | DB autoritativo |
| Analytics | Python puro (modulo `coach/analytics`) | €0 | PMC, zone, readiness |
| Agent | Claude Code + Claude.ai (subscription Pro) | €20/mo (già attivo) | Coach conversazionale |
| Interface | Telegram bot (CF Worker) + MCP server (CF Worker) | €0 | Input/output mobile |
| Memory | Repo git (CLAUDE.md, journal, race history) | €0 | Long-term context |

## Struttura

```
triathlon-coach/
├── CLAUDE.md                  # Profilo atleta + regole agente (CRITICO)
├── coach/                     # Codice Python
│   ├── ingest/                # Garmin/Strava sync
│   ├── analytics/             # PMC, zone, readiness (deterministico)
│   ├── planning/              # Briefing rule-based, generatore mesocicli
│   ├── models/                # Pydantic schemas
│   └── utils/
├── workers/                   # Cloudflare Workers (TS)
│   ├── telegram-bot/          # Bot input/output mobile
│   └── mcp-server/            # MCP per Claude.ai connector (6 tool)
├── sql/
│   └── schema.sql             # Schema Supabase
├── skills/                    # Skill files per Claude Code (8 skill)
├── .github/workflows/         # Cron jobs (7 workflow)
├── scripts/                   # DR, keepalive, audit, utilities
├── docs/                      # Documentazione completa
└── tests/                     # Test suite (16 test)
```

## Roadmap

- [x] **Step 1** — Ingest + Storage (Garmin sync, schema DB, backfill storico)
- [x] **Step 2** — Analytics core (PMC, readiness, flag deterministici)
- [x] **Step 3** — Brief + Telegram (bot, briefing rule-based, debrief serale)
- [x] **Step 4** — Agente conversazionale + Pianificazione settimanale
  - [x] 4.1 — Tool MCP `commit_plan_change`
  - [x] 4.2 — Skill file `weekly_review.md`
  - [x] 4.3 — Workflow `weekly-review.yml`
  - [x] 4.4 — Skill files `race_week_protocol.md` + `race_prediction.md`
  - [x] 4.5 — Brief race week mode
  - [x] 4.6 — Closure documentation + E2E test
- [ ] **Step 5** — Esportazione workout strutturati su Garmin Connect (post test fitness giugno 2026)

## Costi

**Totale aggiuntivo: €0/mese.** Tutto su free tier (Supabase, GitHub Actions, Cloudflare Workers, Telegram, healthchecks.io). L'unica spesa è la subscription Claude Pro già attiva.
