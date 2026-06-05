# Phase 1: Test Suite & Analytics Correctness - Research

**Researched:** 2026-06-05
**Domain:** Python pytest test suite + analytics layer (HRV, PMC, readiness, risk) + operational script pattern
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Aggiungere `scripts/verify_analytics.py` — script Python persistente, committato, che query la Supabase di produzione con le credenziali reali e stampa i valori analytici per ispezione visiva.

**D-02:** Lo script è **solo informativo** — nessun exit 1 automatico su valori anomali. L'operatore guarda l'output e decide manualmente.

**D-03:** Output del script: tutti e 4 i check seguenti:
  - HRV baseline + z-score oggi (verifica ANALYTICS-01 + B1)
  - PMC (CTL/ATL/TSB) da `daily_metrics` (verifica ANALYTICS-03)
  - Readiness score + label (verifica ANALYTICS-04)
  - Risk volume bucketing per disciplina con date Rome (verifica ANALYTICS-05 / B4)

**D-04:** I test B2 esistenti in `tests/test_audit_resilience.py` coprono il caso principale — nessun test aggiuntivo per edge case non-consecutivo.

**D-05:** Nessun test aggiuntivo per l'edge case non-consecutivo (ieri OK, 2fa basso, oggi basso).

**D-06:** Aggiungere un assert nel test B3 esistente (`test_b3_missing_pmc_does_not_score_tsb_optimal`) o in un test dedicato: `daily.compute_for()` deve scrivere `readiness_label` non-null (stringa "ready"/"caution"/"rest") e `readiness_score` ∈ [0, 100] anche quando i dati PMC sono assenti.

**D-07:** Il bug C1 (`briefing_v1.py`) è codice morto — non toccare in Phase 1.

**D-08:** La verifica "dati reali" per ANALYTICS-01 è separata dai test pytest.

### Claude's Discretion

Nessun elemento a discrezione dell'agente identificato per Phase 1. Le scelte di implementazione sono completamente specificate nelle decisioni D-01..D-08.

### Deferred Ideas (OUT OF SCOPE)

- Edge case non-consecutivo per fatigue_warning (ieri OK, 2fa basso, oggi basso) — backlog
- Fix C1 in `briefing_v1.py` (codice morto)
- Bounds-check automatico con exit 1 nel verify_analytics.py — potenziale health check CI in Phase 3
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VERIFY-01 | Test suite pytest passa verde localmente senza failures su logiche critiche (HRV, PMC, readiness, fitness test, modulation, budget, DR, watchdog) | Suite corrente: 172 test tutti verdi — verificato con `python -m pytest tests/ -q`. Nessun lavoro richiesto per questo requisito: è già soddisfatto. |
| ANALYTICS-01 | Baseline HRV (28d) esclude correttamente oggi e usa la data come chiave (non il valore HRV) — verifica B1 live su dati reali | Fix B1 in `daily.py:98` (`r["date"] != today_iso` invece di filtro per valore). Script `verify_analytics.py` ne verifica il comportamento su dati reali Supabase. |
| ANALYTICS-02 | Flag `fatigue_warning` scatta dopo 2 giorni consecutivi con HRV z < -1.0 SD; `fatigue_critical` dopo 1 giorno con z < -2.0 SD | Tre test esistenti in `test_audit_resilience.py` coprono già il caso (D-04): `test_b2_single_low_day_does_not_warn`, `test_b2_two_consecutive_low_days_warn`, `test_b2_daily_excludes_today_from_recent_z`. Nessun nuovo test richiesto. |
| ANALYTICS-03 | PMC riporta `None` per giorni senza dati (non 0); readiness score non mostra TSB "ottimale" su cold-start | Fix B3 in `daily.py:130-134` (`today_pmc.ctl if today_pmc else None`). Coperto da `test_b3_missing_pmc_does_not_score_tsb_optimal`. Script verifica su dati reali. |
| ANALYTICS-04 | Readiness composite score clamped 0-100; label corretta (non `(None)`) nel `daily_metrics` | Nuovo test assert in blocco B3/B11 esistente: `compute_for()` deve scrivere `readiness_label` ∈ {"ready","caution","rest"} e `readiness_score` ∈ [0,100]. Script verifica su dati reali. |
| ANALYTICS-05 | Risk module calcola volume bucketing su data Rome (non UTC) — nessun crash su `started_at` come datetime | Fix B4 in `risk.py:246` (`to_rome_date(a.get("started_at"))` invece di slicing). Coperto da `test_b4_volume_bucketing_handles_datetime_and_str`. Script stampa i valori bucketing con data Rome. |
</phase_requirements>

---

## Summary

Phase 1 è la fase di verifica e consolidamento dei fix di audit di resilienza già applicati. Non richiede nuove funzionalità di rilievo — richiede (1) un nuovo assert di test per ANALYTICS-04, e (2) un nuovo script operativo `scripts/verify_analytics.py`.

La suite pytest è già verde con 172 test che passano tutti. I fix B1, B2, B3, B4, B11 sono già in `coach/analytics/daily.py`, `readiness.py`, e `risk.py`. La copertura unit test per i bug critici (B1/B2/B3/B4/B11) è già presente in `tests/test_audit_resilience.py`. Manca solo l'assert ANALYTICS-04 (readiness_label/readiness_score non-null con dati PMC assenti) e lo script live.

Il lavoro concreto è: (a) aggiungere `test_b3_readiness_label_not_null` in `test_audit_resilience.py` che riusa l'infrastruttura `_FakeSupabase`/`_make_daily_module` esistente, e (b) scrivere `scripts/verify_analytics.py` che connette al DB reale e stampa 4 sezioni di output leggibili.

**Primary recommendation:** Implementa task minimi — 1 test assert + 1 script operativo. Non toccare nulla d'altro.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HRV baseline calculation | Analytics (Python) | — | `daily.py` + `readiness.py`: pura computazione deterministica, zero LLM |
| PMC (CTL/ATL/TSB) | Analytics (Python) | — | `pmc.py`: EWMA, completamente testabile |
| Readiness score + label | Analytics (Python) | — | `readiness.py`: compute_readiness restituisce ReadinessReport con label sempre non-null |
| Risk volume bucketing | Analytics (Python) | Database (Supabase) | `risk.py`: legge `activities` da Supabase, calcola bucketing con date Rome |
| Live data verification | Operational Script | Database (Supabase) | `scripts/verify_analytics.py`: script informativo, legge daily_metrics + daily_wellness + activities |
| Test regression coverage | Test Suite (pytest) | — | `tests/test_audit_resilience.py`: infrastruttura fake Supabase per unit test isolati |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | 7.4 (pinned in requirements.txt) | Test runner | Già configurato in `pytest.ini` (`testpaths = tests`); 172 test esistenti lo usano |
| python-dotenv | 1.0 | Load .env per script locali | Usato da `supabase_client.py`; tutti gli script lo riusano indirettamente |
| supabase | >=2.30.0 | DB reads via `get_supabase()` | Singleton in `coach/utils/supabase_client.py` — entry point unico per tutti gli script |

### No New Packages Required

Phase 1 non richiede nuove dipendenze. Tutti gli import necessari per `verify_analytics.py` sono già disponibili:
- `coach.utils.supabase_client.get_supabase` — connessione DB
- `coach.analytics.daily.compute_for` — ricalcolo (non necessario, si legge da DB)
- `coach.analytics.readiness.hrv_z_score` — ricalcolo z-score per verifica
- `datetime`, `statistics` — stdlib

---

## Package Legitimacy Audit

> Phase 1 non installa nuovi pacchetti. Audit non applicabile.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
.env (locale) → dotenv → get_supabase()
                              |
                        [Supabase DB]
                         /    |    \
               daily_wellness  daily_metrics  activities
                         \    |    /
                    verify_analytics.py
                         |
                    [stdout leggibile]
                    4 sezioni: HRV | PMC | Readiness | Risk
```

Per i test:
```
_FakeSupabase (dict tables) → _make_daily_module() → daily.compute_for(date)
                                                              |
                                                   sb.last_upsert (capture)
                                                              |
                                                   assert readiness_label in {"ready","caution","rest"}
                                                   assert 0 <= readiness_score <= 100
```

### Recommended Project Structure

Nessuna modifica strutturale. I due deliverable si inseriscono in percorsi esistenti:
```
scripts/
├── verify_analytics.py    # NUOVO — script operativo live
tests/
└── test_audit_resilience.py  # MODIFICA — aggiungere test B3 readiness_label
```

### Pattern 1: Script Operativo (pattern da `scripts/`)

**What:** Script Python standalone che legge dal DB reale e stampa output informativo.
**When to use:** Verifica live su dati di produzione — mai per test automatizzati.
**Structure:**
```python
# Source: pattern consolidato da scripts/smoke_test.py, scripts/backfill_metrics.py
from __future__ import annotations
import logging
from dotenv import load_dotenv
load_dotenv()
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

def main() -> None:
    logging.basicConfig(level=logging.INFO, ...)
    sb = get_supabase()
    # ... query e print ...

if __name__ == "__main__":
    main()
```

**Key constraint:** `load_dotenv()` deve essere chiamato PRIMA di `get_supabase()` (che usa `lru_cache` — se chiamato senza env vars solleva `KeyError` e la cache conserva l'errore). Tutti gli script esistenti rispettano questo ordine.

### Pattern 2: Test con _FakeSupabase (pattern da `test_audit_resilience.py`)

**What:** Carica `daily.py` con supabase stubbed via `sys.modules` injection.
**When to use:** Qualsiasi test che chiama `compute_for()` — NON usare `unittest.mock.patch` su get_supabase perché `lru_cache` può causare leak tra test.
**Structure:**
```python
# Source: tests/test_audit_resilience.py
def test_new_analytics_assert():
    day = date(2026, 5, 30)
    wellness = [{"date": day.isoformat(), "hrv_rmssd": 55.0, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50}]
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["readiness_label"] in {"ready", "caution", "rest"}
    assert isinstance(m["readiness_score"], int)
    assert 0 <= m["readiness_score"] <= 100
```

**Critical detail:** `_make_daily_module(sb)` deve essere chiamato per ogni test — recrea il modulo con un nuovo sb pulito. Non riusare l'istanza del modulo tra test.

### Pattern 3: Output dello script `verify_analytics.py`

**What:** 4 sezioni di output stampate su stdout, leggibili a vista.
**Template esatto (da D-03 in CONTEXT.md):**
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

### Anti-Patterns to Avoid

- **Chiamare `get_supabase()` prima di `load_dotenv()`:** La `lru_cache` sul client Supabase blocca ogni tentativo successivo. Tutti gli script devono chiamare `load_dotenv()` all'inizio del file o all'inizio di `main()`, prima di qualsiasi import da `coach.*` che chiama `get_supabase()` a import-time.
- **Aggiungere exit 1 automatico in `verify_analytics.py`:** La decisione D-02 è esplicita: nessun errore automatico. Il valore dello script è informativo, non ci-gating.
- **Importare `daily.py` direttamente nei test:** L'infrastruttura usa `importlib.util.spec_from_file_location` + `sys.modules` injection. L'import diretto bypasserebbe il fake Supabase e causerebbe connessioni DB reali nei test.
- **Usare `unittest.mock.patch("coach.utils.supabase_client.get_supabase")`:** L'`lru_cache` su `get_supabase()` può causare che il mock rimanga in stato errato tra test. Usare invece `sys.modules["coach.utils.supabase_client"].get_supabase = lambda: sb`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Connessione Supabase | Client custom | `coach.utils.supabase_client.get_supabase()` | Singleton con load_dotenv già integrato; usato da tutti gli script |
| Calcolo z-score HRV | Formula custom in script | `coach.analytics.readiness.hrv_z_score()` | Funzione testata, stessa formula usata da `compute_for()` — consistency garantita |
| Caricamento wellness/metrics | Query custom | Leggere da `daily_metrics` o richiamare `compute_for()` | La tabella `daily_metrics` ha già i valori calcolati e persistiti da ogni run ingest |
| Modulo di date Rome | Conversione timezone custom | `coach.utils.dt.to_rome_date()` e `today_rome()` | Fix B4 vive qui; riusare garantisce coerenza con il codice di produzione |

**Key insight:** Lo script di verifica deve *leggere* i valori già calcolati e persistiti da `daily_metrics` / `daily_wellness`, non ricalcolarli. L'unica eccezione è il z-score HRV, che richiede di ricalcolare baseline sui dati grezzi per verificare che il fix B1 sia attivo.

---

## Common Pitfalls

### Pitfall 1: lru_cache blocca il fake Supabase nei test
**What goes wrong:** Se un test importa `coach.analytics.daily` direttamente (non via `_make_daily_module`), `get_supabase()` viene chiamato con la cache vuota e cerca le variabili d'ambiente reali. Se queste non ci sono, il test crasha; se ci sono, connette al DB di produzione.
**Why it happens:** `get_supabase` è decorato con `@lru_cache(maxsize=1)` in `supabase_client.py`. Il primo call crea e memorizza il client.
**How to avoid:** Usare sempre `_make_daily_module(sb)` che fa `sys.modules["coach.utils.supabase_client"].get_supabase = lambda: sb` PRIMA di eseguire `spec.loader.exec_module(mod)`.
**Warning signs:** Test che passano localmente (con .env) ma falliscono in CI (senza .env).

### Pitfall 2: `verify_analytics.py` mostra None per tutti i campi PMC
**What goes wrong:** Lo script legge da `daily_metrics` ma CTL/ATL/TSB sono tutti None.
**Why it happens:** Le `physiology_zones` non sono ancora state misurate (FTP test programmato per giugno 2026), quindi il TSS per molte attività è None → `aggregate_daily_tss` ritorna lista vuota → `compute_pmc_series` ritorna `[]` → PMC è None. Questo è il comportamento CORRETTO (fix B3 verificato).
**How to avoid:** Lo script deve stampare esplicitamente `None` con una nota: "PMC non disponibile (test FTP/soglia non ancora eseguiti — vedi Phase 2)". Non interpretare come bug.
**Warning signs:** Se CTL=0.00 (non None) compare nel DB, QUELLO è il bug B3 che non è stato fixato.

### Pitfall 3: HRV baseline con 0 giorni storici
**What goes wrong:** Lo script mostra "Baseline 28d: N/A" anche oggi.
**Why it happens:** `len(hrv_history) < 7` è la soglia minima per calcolare il z-score (`hrv_z_score` in `readiness.py:74`). Con meno di 7 giorni di storico, z rimane None.
**How to avoid:** Lo script deve gestire il caso `hrv_z is None` con messaggio "Dati storici insufficienti (< 7 giorni HRV)".
**Warning signs:** Questo è normale in cold-start o dopo un gap di dati Garmin.

### Pitfall 4: Test ANALYTICS-04 che non testa il caso PMC-assente
**What goes wrong:** Il test aggiunto verifica `readiness_label` ma usa dati che producono PMC valido → non verifica il path `today_pmc = None`.
**Why it happens:** Se si aggiungono activities al `_FakeSupabase`, il PMC viene calcolato e il caso None-handling non viene esercitato.
**How to avoid:** Usare `activities: []` (lista vuota) per forzare il path None-PMC, come già fa `test_b3_missing_pmc_does_not_score_tsb_optimal`.
**Warning signs:** Il test passa ma `m["readiness_score"]` è sempre > 50 (indizio che il path `tsb=None → neutral 50` è quello che scatta).

---

## Code Examples

### Esempio 1: Lettura daily_metrics per verify_analytics.py

```python
# Pattern da backfill_metrics.py e smoke_test.py
from coach.utils.supabase_client import get_supabase
from coach.utils.dt import today_rome

def _fetch_today_metrics(sb):
    today = today_rome().isoformat()
    res = (
        sb.table("daily_metrics")
        .select("date,ctl,atl,tsb,hrv_z_score,hrv_baseline_28d,hrv_baseline_28d_sd,readiness_score,readiness_label,flags")
        .eq("date", today)
        .execute()
    )
    return res.data[0] if res.data else None
```

### Esempio 2: Ricalcolo HRV baseline per verifica B1

```python
# Verifica che baseline usi la DATA come chiave, non il valore
from coach.analytics.readiness import hrv_z_score
import statistics

def _verify_hrv_b1(sb, today_iso):
    """Ricalcola z-score lato script per confronto con daily_metrics."""
    since = (date.fromisoformat(today_iso) - timedelta(days=28)).isoformat()
    res = sb.table("daily_wellness").select("date,hrv_rmssd").gte("date", since).execute()
    rows = res.data or []
    hist_rows = [r for r in rows if r["date"] != today_iso]  # esclusione per DATA
    today_row = next((r for r in rows if r["date"] == today_iso), None)
    hrv_history = [r["hrv_rmssd"] for r in hist_rows if r.get("hrv_rmssd") is not None]
    if today_row and today_row.get("hrv_rmssd") and len(hrv_history) >= 7:
        mean = statistics.fmean(hrv_history)
        sd = statistics.pstdev(hrv_history)
        z = hrv_z_score(today_row["hrv_rmssd"], hrv_history)
        return mean, sd, len(hrv_history), z
    return None
```

### Esempio 3: Test ANALYTICS-04 con _FakeSupabase

```python
# Da inserire in tests/test_audit_resilience.py
# Pattern: riusa esattamente _FakeSupabase e _make_daily_module già definiti nel file

def test_b3_readiness_label_not_null():
    """ANALYTICS-04: compute_for deve scrivere readiness_label non-null e
    readiness_score 0-100 anche quando PMC è assente (nessuna activity)."""
    day = date(2026, 5, 30)
    wellness = [{"date": day.isoformat(), "hrv_rmssd": 55.0, "sleep_score": 80,
                 "body_battery_max": 80, "resting_hr": 50}]
    sb = _FakeSupabase({"activities": [], "daily_wellness": wellness, "subjective_log": []})
    daily = _make_daily_module(sb)
    daily.compute_for(day)
    m = sb.last_upsert
    assert m["ctl"] is None  # PMC assente (no activities)
    assert m["readiness_label"] in {"ready", "caution", "rest"}, (
        f"readiness_label deve essere non-null string, got: {m['readiness_label']!r}"
    )
    assert isinstance(m["readiness_score"], int), (
        f"readiness_score deve essere int, got: {type(m['readiness_score'])}"
    )
    assert 0 <= m["readiness_score"] <= 100, (
        f"readiness_score deve essere 0-100, got: {m['readiness_score']}"
    )
```

### Esempio 4: Risk volume bucketing per verify_analytics.py

```python
# Verifica B4: to_rome_date applicato, nessun crash su datetime
from coach.utils.dt import today_rome, to_rome_date
from datetime import timedelta

def _fetch_risk_volumes(sb):
    today = today_rome()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    since = (today - timedelta(days=14)).isoformat()
    res = sb.table("activities").select("started_at,sport,duration_s") \
        .gte("started_at", f"{since}T00:00:00Z").execute()
    by_sport = {}
    for a in (res.data or []):
        d = to_rome_date(a.get("started_at"))
        if d is not None and d >= this_week_start:
            sport = a.get("sport", "unknown")
            by_sport[sport] = by_sport.get(sport, 0) + (a.get("duration_s") or 0) / 60
    return by_sport, today, this_week_start
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Esclusione HRV baseline per valore | Esclusione per data (`r["date"] != today_iso`) | Audit 2026-06-01 (fix B1) | Baseline corretta con HRV stabile |
| `fatigue_warning` dopo 1 giorno | Richiede 2 giorni consecutivi (`hrv_recent_z_scores` esclude oggi) | Audit 2026-06-01 (fix B2) | Rispetta CLAUDE.md §5.1 |
| PMC assente → TSB=0 → score 100 | PMC assente → TSB=None → score neutro 50 | Audit 2026-06-01 (fix B3) | Cold-start corretto |
| `started_at[:10]` slicing | `to_rome_date(started_at)` | Audit 2026-06-01 (fix B4) | No crash su datetime, timezone corretta |
| `_score_sleep` non clampata | `max(0, min(100, sleep_score))` | Audit 2026-06-01 (fix B11) | Score sempre 0-100 |

**Stato corrente confermato:**
- `daily.py:98`: `hist_rows = [r for r in wellness_rows if r["date"] != today_iso]` — fix B1 attivo [VERIFIED: codebase grep]
- `daily.py:113-116`: `recent_z_scores` costruito solo da `hist_rows[-5:]` — fix B2 attivo [VERIFIED: codebase grep]
- `daily.py:130-134`: `ctl=today_pmc.ctl if today_pmc else None` — fix B3 attivo [VERIFIED: codebase grep]
- `risk.py:246`: `to_rome_date(a.get("started_at"))` — fix B4 attivo [VERIFIED: codebase grep]
- `readiness.py:156`: `max(0, min(100, wellness.sleep_score_today))` — fix B11 attivo [VERIFIED: codebase grep]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Il DB Supabase di produzione ha dati `daily_metrics` recenti con `readiness_label` e `readiness_score` popolati dall'ultimo run ingest | Code Examples — verify_analytics.py | Lo script stamperebbe "Nessun dato per oggi" — non un bug, solo un dato mancante. Rischio basso. |
| A2 | `physiology_zones` non sono ancora disponibili (FTP/CSS/soglia non misurati) quindi PMC in produzione mostra None — questo è il comportamento corretto | Common Pitfalls §2 | Se FTP è già stato testato e persistito, il PMC potrebbe avere valori reali. Non cambia il test o lo script. |

---

## Open Questions

1. **Posizione del nuovo test: nuovo metodo vs nuovo file?**
   - What we know: D-06 dice "nel test B3 esistente o in un test dedicato"
   - What's unclear: il test B3 esistente testa già TSB neutral=50; aggiungere assert readiness_label/score nello stesso test o in un metodo separato `test_b3_readiness_label_not_null`?
   - Recommendation: nuovo metodo separato `test_b3_readiness_label_not_null` nello stesso file, subito dopo `test_b3_missing_pmc_does_not_score_tsb_optimal`. Mantiene la logica raggruppata per bug B3 senza appesantire il test esistente.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | verify_analytics.py, pytest | Verificare con `python --version` | 3.11.x | — |
| `.env` con SUPABASE_URL + SUPABASE_SERVICE_KEY | verify_analytics.py (runtime locale) | Solo locale — non in CI | — | Senza .env lo script solleva `KeyError: SUPABASE_URL` |
| supabase Python client | verify_analytics.py | Già in requirements.txt (>=2.30.0) | — | — |
| pytest | Test suite | Già in requirements.txt (7.4) | 7.4 | — |

**Missing dependencies with no fallback:**
- `.env` con credenziali Supabase: richiesto per eseguire `verify_analytics.py` localmente. Lo script è documentato come tool operativo locale — non gira in CI.

**Missing dependencies with fallback:**
- Nessuno.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4 |
| Config file | `pytest.ini` (testpaths = tests) |
| Quick run command | `python -m pytest tests/test_audit_resilience.py -v -k "b3"` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VERIFY-01 | Suite pytest verde | suite | `python -m pytest tests/ -q` | Tutti i file esistono — 172 test verdi confermati |
| ANALYTICS-01 | HRV baseline esclude oggi per data | unit | `python -m pytest tests/test_audit_resilience.py::test_b1_baseline_not_filtered_by_value -v` | Esiste |
| ANALYTICS-02 | fatigue_warning dopo 2 giorni, non 1 | unit | `python -m pytest tests/test_audit_resilience.py -k "b2" -v` | Esiste (3 test) |
| ANALYTICS-03 | PMC None su cold-start | unit | `python -m pytest tests/test_audit_resilience.py::test_b3_missing_pmc_does_not_score_tsb_optimal -v` | Esiste |
| ANALYTICS-04 | readiness_label non-null, score 0-100 | unit | `python -m pytest tests/test_audit_resilience.py::test_b3_readiness_label_not_null -v` | **NON ESISTE** — Wave 0 task |
| ANALYTICS-05 | Risk volume bucketing data Rome | unit | `python -m pytest tests/test_audit_resilience.py::test_b4_volume_bucketing_handles_datetime_and_str -v` | Esiste |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_audit_resilience.py -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** `python -m pytest tests/ -q` verde + `python scripts/verify_analytics.py` output ispezionato

### Wave 0 Gaps
- [ ] `test_b3_readiness_label_not_null` in `tests/test_audit_resilience.py` — copre ANALYTICS-04
- [ ] `scripts/verify_analytics.py` — tool operativo (non un test pytest)

*(Il framework pytest e tutta l'infrastruttura di test sono già presenti e funzionanti.)*

---

## Security Domain

> `security_enforcement: true` in `.planning/config.json`. ASVS Level 1 applicabile.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — script locale, nessun auth endpoint |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A — script eseguito da sviluppatore locale |
| V5 Input Validation | Marginale | Valori letti da DB sono già validati a ingest — nessun input utente in verify_analytics.py |
| V6 Cryptography | No | N/A — nessuna crypto in Phase 1 |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credenziali DB in output script | Information Disclosure | `verify_analytics.py` non deve loggare `SUPABASE_URL` o `SUPABASE_SERVICE_KEY` — usare solo dati analytics in stdout |
| `.env` committato per sbaglio | Information Disclosure | `.env` già in `.gitignore` (pattern standard del progetto) — non alterare |

**Note:** Phase 1 è di sola lettura (query + test). Nessuna scrittura su DB avviene dallo script `verify_analytics.py`. Il test usa `_FakeSupabase` senza connessione DB reale. Il profilo di rischio sicurezza è minimo.

---

## Sources

### Primary (HIGH confidence)
- Codebase: `coach/analytics/daily.py` — comportamento reale post-fix B1/B2/B3
- Codebase: `coach/analytics/readiness.py` — ReadinessReport dataclass, label mapping
- Codebase: `coach/analytics/risk.py` — to_rome_date applicato post-fix B4
- Codebase: `tests/test_audit_resilience.py` — infrastruttura _FakeSupabase/_make_daily_module
- Codebase: `coach/utils/supabase_client.py` — pattern lru_cache get_supabase()
- Codebase: `scripts/smoke_test.py`, `scripts/backfill_metrics.py` — pattern script operativi

### Secondary (MEDIUM confidence)
- `.planning/phases/01-test-suite-analytics-correctness/01-CONTEXT.md` — decisioni utente D-01..D-08
- `.planning/REQUIREMENTS.md` — acceptance criteria VERIFY-01, ANALYTICS-01..05
- `docs/audit_resilience_2026-06-01.md` — tassonomia bug e fix

### Tertiary (LOW confidence)
- Nessuna fonte terziaria: tutta la ricerca è stata condotta sulla codebase reale.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verificato sulla codebase esistente, nessun nuovo pacchetto
- Architecture: HIGH — due deliverable minori, pattern già esistenti nel progetto
- Pitfalls: HIGH — verificati leggendo il codice sorgente (lru_cache, sys.modules injection)

**Research date:** 2026-06-05
**Valid until:** 2026-09-01 (stabile — analytics layer deterministico, no dipendenze esterne fast-moving)
