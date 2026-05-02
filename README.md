# Triathlon Coach AI

Sistema agentico personale per il ritorno al triathlon élite. Cloud-first, costo €0
oltre la subscription Claude Pro già attiva.

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

## Quickstart

Prima volta: leggi `docs/SETUP.md` (90 minuti circa la prima setup, poi è autonomo).

Operatività quotidiana: leggi `docs/RUNBOOK.md`.

Architettura completa con failure mode e mitigazioni: `docs/ARCHITECTURE.md`.

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
│   └── mcp-server/            # MCP per Claude.ai connector
├── sql/
│   └── schema.sql             # Schema Supabase
├── skills/                    # Skill files per Claude Code
├── .github/workflows/         # Cron jobs
├── scripts/                   # DR, keepalive, utilities
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   └── RUNBOOK.md
└── tests/
```

## Stato del progetto

Blueprint v0.1. Roadmap implementativa in `docs/ARCHITECTURE.md` §Roadmap.
