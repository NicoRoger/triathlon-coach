# Phase 1: Test Suite & Analytics Correctness - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Verificare che la test suite pytest sia verde e che ogni logica analytics critica (HRV, PMC, readiness, risk) produca output corretti — sia su dati artificiali (unit test) che su dati reali di Nicolò in Supabase (script di verifica live).

I test esistono già (172 test, tutti verdi). Il lavoro di Phase 1 è:
1. Aggiungere uno script di verifica live (`scripts/verify_analytics.py`) che query Supabase e stampa i valori effettivi per ispezione visiva
2. Aggiungere un assert in un test esistente che `daily.compute_for()` scriva `readiness_label` non-null e `readiness_score` ∈ [0, 100] in `daily_metrics`

Non rientra in Phase 1: deploy, migrazioni DB, qualità del brief, verifica del comportamento live end-to-end.

</domain>

<decisions>
## Implementation Decisions

### Strategia di verifica "dati reali" (ANALYTICS-01)

- **D-01:** Aggiungere `scripts/verify_analytics.py` — script Python persistente, committato, che query la Supabase di produzione con le credenziali reali e stampa i valori analytici per ispezione visiva
- **D-02:** Lo script è **solo informativo** — nessun exit 1 automatico su valori anomali. L'operatore guarda l'output e decide manualmente
- **D-03:** Output del script: tutti e 4 i check seguenti:
  - **HRV baseline + z-score oggi**: media e SD baseline 28d (con verifica che oggi sia escluso), z-score corrente, flag risultante (warning/critical/ok) — verifica ANALYTICS-01 + B1
  - **PMC (CTL/ATL/TSB)**: valori correnti da `daily_metrics` — verifica nessun 0 ingiustificato al posto di None — ANALYTICS-03
  - **Readiness score + label**: composite score (0-100) e label testuale da `daily_metrics` — verifica ANALYTICS-04
  - **Risk volume bucketing per disciplina**: volume settimanale per sport con date Rome da `coach/analytics/risk.py` — verifica ANALYTICS-05 / B4

### Test consecutivi fatigue_warning (ANALYTICS-02)

- **D-04:** I test B2 esistenti in `tests/test_audit_resilience.py` coprono il caso principale:
  - `test_b2_single_low_day_does_not_warn` — 1 giorno basso, nessun warning
  - `test_b2_two_consecutive_low_days_warn` — 2 giorni consecutivi, warning scatta
  - `test_b2_daily_excludes_today_from_recent_z` — oggi escluso da recent_z_scores
- **D-05:** Nessun test aggiuntivo per l'edge case non-consecutivo — copertura attuale sufficiente per Phase 1

### Test output daily_metrics (ANALYTICS-04)

- **D-06:** Aggiungere un assert nel test B3 esistente (`test_b3_missing_pmc_does_not_score_tsb_optimal`) o in un test dedicato: `daily.compute_for()` deve scrivere `readiness_label` non-null (stringa "ready"/"caution"/"rest") e `readiness_score` ∈ [0, 100] in `daily_metrics` anche quando i dati PMC sono assenti

### Scope confini

- **D-07 [informational]:** Il bug C1 (label `(None)` in `briefing_v1.py`) è in codice morto — non toccare in Phase 1. Il brief attivo è `briefing.py` (v2) e non renderizza `readiness_label`
- **D-08:** La verifica "dati reali" per ANALYTICS-01 è separata dai test pytest — lo script è un tool operativo, non un test automatizzato

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisiti Phase 1
- `.planning/REQUIREMENTS.md` §VERIFY, §ANALYTICS — requisiti VERIFY-01 e ANALYTICS-01/02/03/04/05 con acceptance criteria dettagliati
- `.planning/ROADMAP.md` §Phase 1 — goal, success criteria (5 items), requirements mappati

### Audit di resilienza (fonte dei bug da verificare)
- `docs/audit_resilience_2026-06-01.md` — tabella completa dei bug, fix committati, test di regressione. In particolare:
  - §B1: baseline HRV filtrata per valore invece che per data (fix in `daily.py`)
  - §B2: fatigue_warning scattava dopo 1 giorno invece di 2 (fix in `daily.py`)
  - §B3: PMC mancante passato come 0 non None (fix in `daily.py` + `readiness.py`)
  - §B4: risk.py — started_at datetime/str crash bucketing volume (fix in `risk.py`)
  - §B11: `_score_sleep` non clampava 0-100 (fix in `readiness.py`)
  - §C1: label readiness (None) — documentato come codice morto, non fixato

### Logiche analytics da verificare
- `coach/analytics/readiness.py` — compute_flags, compute_score, ReadinessReport.label; soglie §5.1 CLAUDE.md
- `coach/analytics/daily.py` — compute_for; costruzione hrv_recent_z_scores (B2 fix), baseline HRV (B1 fix)
- `coach/analytics/pmc.py` — CTL/ATL/TSB EWMA; None handling per giorni senza dati
- `coach/analytics/risk.py` — volume bucketing con date Rome (B4 fix)

### Test suite esistente
- `tests/test_audit_resilience.py` — test B1/B2/B3/B4/B11 e modulation/watchdog
- `tests/test_readiness.py` — flag logic, score bounds, label
- `tests/test_pmc.py` — EWMA math
- `tests/test_regressions.py` — TestTsbNoneHandling, TestStartedAtStringParsing

### Metodologia (non alterare)
- `CLAUDE.md` §5.1 — soglie deterministiche HRV (z < -1.0 SD per 2gg → warning, z < -2.0 SD per 1gg → critical)
- `CLAUDE.md` §5.4 — mai modificare planned_sessions senza conferma atleta

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/test_audit_resilience.py` — `_FakeSupabase`, `_make_daily_module`, `_load()` helper: riutilizzare per il test ANALYTICS-04 su `readiness_label` in `daily_metrics`
- `coach/utils/supabase_client.get_supabase()` — usato dallo script `verify_analytics.py` per connettersi al DB reale (richiede `.env` con `SUPABASE_URL` e `SUPABASE_SERVICE_KEY`)
- `coach/analytics/daily.compute_for(date)` — entry point diretto per ricalcolare le metriche di un giorno

### Established Patterns
- Script in `scripts/` seguono lo stesso pattern: import da `coach.*`, logging via `logging.getLogger(__name__)`, `load_dotenv()` all'inizio, `if __name__ == "__main__": main()`
- Test con dipendenze Supabase usano `sys.modules` injection + `importlib.util.spec_from_file_location` (NON direct import) — da rispettare per qualsiasi nuovo test
- `PYTHONPATH=.` richiesto per tutti i comandi pytest — non c'è `setup.py`

### Integration Points
- `scripts/verify_analytics.py` legge da `daily_metrics`, `daily_wellness`, `activities` — stesse tabelle usate da `daily.compute_for()`
- Il test ANALYTICS-04 si aggancia all'infrastruttura `_FakeSupabase` esistente in `test_audit_resilience.py`

</code_context>

<specifics>
## Specific Ideas

- Lo script `verify_analytics.py` deve stampare output leggibile tipo:
  ```
  === HRV Analytics ===
  Baseline 28d: media=67.3ms, SD=8.1ms (29 giorni, oggi escluso)
  Z-score oggi: -0.4σ → OK
  Flag: nessuno

  === PMC ===
  CTL: 42.1 | ATL: 38.7 | TSB: +3.4

  === Readiness ===
  Score: 74/100 | Label: caution

  === Risk: Volume Bucketing (settimana corrente) ===
  swim: 2800m | bike: 145km | run: 18.5km (date: Europe/Rome)
  ```
- Il test ANALYTICS-04 si inserisce nel blocco B3/B11 esistente in `test_audit_resilience.py`, non in un file nuovo

</specifics>

<deferred>
## Deferred Ideas

- Edge case non-consecutivo per fatigue_warning (ieri OK, 2fa basso, oggi basso) — valutare in un backlog, non critico per Phase 1
- Fix C1 in `briefing_v1.py` (codice morto) — se mai si riattiva v1, va fixato allora
- Bounds-check automatico con exit 1 nel verify_analytics.py — potrebbe diventare un health check CI in Phase 3

</deferred>

---

*Phase: 1-Test Suite & Analytics Correctness*
*Context gathered: 2026-06-05*
