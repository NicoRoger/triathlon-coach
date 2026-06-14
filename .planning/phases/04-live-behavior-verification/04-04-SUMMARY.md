---
phase: 04-live-behavior-verification
plan: "04"
subsystem: evidence-script + live-verification
tags: [verify-03, verify-04, verify-05, verify-06, fitness-04, evidence-script, d-06]
dependency_graph:
  requires: [04-01, 04-02, 04-03]
  provides:
    - scripts/verify_live_behavior.py
  affects:
    - scripts/verify_live_behavior.py
    - plan_modulations (D-06 fallback: accepted->applied live)
    - planned_sessions (3 sessioni aggiornate da modulazione 368aef79)
tech_stack:
  added: []
  patterns:
    - read-only evidence script (pattern verify_analytics.py)
    - D-06 fallback per VERIFY-05 live scenario
key_files:
  created:
    - scripts/verify_live_behavior.py
  modified: []
decisions:
  - "Caratteri freccia Unicode rimossi per compatibilita' Windows cp1252 console"
  - "D-06 fallback eseguito per VERIFY-05: modulazione 368aef79 (post_session_critical 2026-06-06) portata da proposed ad applied via apply-accepted; 3 sessioni aggiornate in planned_sessions (swim 07/06, rest 08/06, bike 09/06)"
  - "_verify_brief_zones controlla physiology_zones + staleness bot_messages (bot_messages non memorizza il testo del messaggio, solo context_data)"
metrics:
  duration_minutes: 20
  completed_date: "2026-06-07"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 1
---

# Phase 04 Plan 04: Live Behavior Evidence Script Summary

**One-liner:** `scripts/verify_live_behavior.py` read-only a 4 sezioni conferma 4/4 OK su dati live — VERIFY-03/04/05/06 + FITNESS-04 chiusi.

## Obiettivo

Creare lo script di evidenza unico read-only `scripts/verify_live_behavior.py` (D-13/D-14/D-15) che consolida la verifica delle 4 aree di Phase 4, e chiudere la fase con checkpoint umano che conferma 4/4 OK sui dati reali.

## Tasks Completati

| Task | Nome | Commit | File |
|------|------|--------|------|
| 1 | Crea verify_live_behavior.py read-only con 4 sezioni | 1cfcac7 | scripts/verify_live_behavior.py |
| fix | Rimuovi caratteri freccia Unicode (encoding Windows) | 042b971 | scripts/verify_live_behavior.py |
| 2 | Checkpoint umano: eseguito D-06 fallback + conferma 4/4 OK | — | plan_modulations, planned_sessions |

## Implementazione

### verify_live_behavior.py

Script modellato su `verify_analytics.py`. Struttura: `load_dotenv()` prima di ogni import `coach.*`; `STALE_DAYS_CUTOFF = 7`; 4 funzioni di sezione con try/except per sezione; `main()` con `=== Riepilogo: N/4 OK ===`.

**Sezioni:**
- `_verify_brief_zones(sb)` — query `bot_messages` (staleness) + `physiology_zones` (proxy zone inline nel brief)
- `_verify_session_analyses(sb)` — conta righe recenti, verifica `model_used='gemini-2.5-flash'`, staleness
- `_verify_plan_modulations(sb)` — breakdown status + check `applied >= 1` + staleness
- `_verify_budget(sb)` — `get_month_spend_usd()` vs `BUDGET_DEGRADED`/`BUDGET_BLOCKED`

### D-06 Fallback (VERIFY-05 live)

Modulation `368aef79` (post_session_critical, 2026-06-06): portata da `proposed` ad `accepted` via update Supabase diretto, poi `python -m coach.coaching.modulation --apply-accepted`. Risultato: applied=1, 3 sessioni aggiornate (`planned_sessions`: swim 2026-06-07, rest 2026-06-08, bike 2026-06-09).

## Risultato Live (2026-06-07)

```
=== Live Behavior Check — 2026-06-07 ===

[BRIEF ZONES]
  Ultimo brief: 2026-06-07 (0 giorni fa — OK)
  [OK] physiology_zones: bike=2026-05-26, run=2026-05-30, swim=2026-06-04
  [OK] briefing.py legge physiology_zones -> Zone misurate nel brief

[SESSION ANALYSES]
  session_analyses: 5 righe (ultima: 2026-06-06, 1 giorni fa — OK)
  [OK] model_used: gemini-2.5-flash su tutte le 5 righe recenti

[PLAN MODULATIONS]
  status breakdown: applied=1, proposed=17
  Ultima modulazione: 2026-06-06 (1 giorni fa — OK)
  [OK] 1 modulazione(i) applicata(e) — flusso accepted->applied OK

[BUDGET TRACKER]
  Spesa Anthropic mese corrente: $0.02 (soglia degrado €4.00: OK)
  [OK] budget.py: BUDGET_DEGRADED = 4.0, BUDGET_BLOCKED = 4.8

=== Riepilogo: 4/4 OK ===
```

## Verification

- `PYTHONPATH=. python scripts/verify_live_behavior.py` → 4/4 OK sui dati reali
- `grep -c "def main" scripts/verify_live_behavior.py` → 1
- `grep -v '^#' scripts/verify_live_behavior.py | grep -c "sys.exit(1)"` → 0
- `grep -n "load_dotenv" scripts/verify_live_behavior.py` → riga 14, prima di ogni `from coach.`
- VERIFY-03: physiology_zones presente, brief inviato oggi [OK]
- VERIFY-04: 5 session_analyses recenti con model_used=gemini-2.5-flash [OK]
- VERIFY-05: flusso accepted->applied eseguito live (D-06), 3 sessioni aggiornate [OK]
- VERIFY-06: spesa $0.02, BUDGET_DEGRADED=4.0 [OK]
- FITNESS-04: physiology_zones swim/run/bike presenti, zone nel brief [OK]

## Known Stubs

Nessuno.

## Self-Check

- [x] scripts/verify_live_behavior.py esiste con `def main`
- [x] Contiene `STALE_DAYS_CUTOFF = 7`
- [x] `from coach.utils.supabase_client import get_supabase`
- [x] `from coach.utils.budget import BUDGET_DEGRADED, BUDGET_BLOCKED, get_month_spend_usd`
- [x] Nessun `sys.exit(1)`
- [x] `load_dotenv()` prima di ogni `from coach.*`
- [x] Script eseguito sui dati reali: 4/4 OK
- [x] Commit 1cfcac7 (feat) e 042b971 (fix encoding) esistono

## Self-Check: PASSED
