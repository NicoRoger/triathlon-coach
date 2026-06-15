---
phase: 03-deploy-pipeline-resilience
reviewed: 2026-06-07T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - .github/workflows/ingest.yml
  - scripts/verify_migrations.py
  - tests/test_audit_resilience.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-07
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

---

## Sommario

Tre file revisionati: il workflow `ingest.yml` (fix D-06 rimozione `if: always()` da Apply-accepted-modulations), il nuovo script `verify_migrations.py` (verifier deterministico con exit-code contract), e `tests/test_audit_resilience.py` (aggiunta copertura esplicita PIPELINE-04 idempotency).

Il fix D-06 su `ingest.yml` è corretto: la rimozione di `if: always()` dallo step "Apply accepted modulations" significa che il passo ora eredita la semantica `success()` predefinita di GitHub Actions e non applicherà mai modulazioni su dati stantii dopo un fallimento del Garmin sync. Gli altri `if: always()` nel file (Compute daily metrics, ETL health check) sono intenzionali e corretti.

Trovato un difetto di correttezza critico in `verify_migrations.py`: la verifica dei vincoli controlla solo il **nome** del constraint, non la tabella su cui è definito — un constraint omonimo su una tabella diversa passerebbe il check. Trovate tre issues di livello Warning, tra cui una nel workflow (metriche calcolate su dati stantii quando Garmin fallisce) e due nei test (time-window del guard di idempotency non verificata, tipo parametro `sb` non annotato).

---

## Critical Issues

### CR-01: verify_migrations.py — verifica constraint per nome senza validare la tabella di appartenenza

**File:** `scripts/verify_migrations.py:113-123`

**Issue:** Le costanti `EXPECTED_UNIQUE_CONSTRAINTS`, `EXPECTED_FK_CONSTRAINTS` e `EXPECTED_CHECK_CONSTRAINTS` sono definite come tuple `(tabella, nome_vincolo)`, ma nella funzione `main()` il check ignora la colonna `_table` e verifica solo che il **nome** del constraint esista nell'insieme restituito da `_fetch_constraints(sb)`. Quell'insieme è una `set` flat di soli nomi, senza informazione sulla tabella di appartenenza.

Conseguenza concreta: se un constraint di nome identico (es. `plan_modulations_status_check`) venisse per errore applicato a una tabella sbagliata, o se una migrazione venisse eseguita parzialmente lasciando intatto un vecchio constraint con lo stesso nome su una tabella diversa, il verifier restituisce PASS con exit 0, mascherando il problema. L'utilizzo dei tuple a due elementi con il prefisso `_table` (underscore = ignorato) rende questo difetto di design esplicito ma non risolto.

La stessa osservazione vale per `_fetch_constraints`, che ritorna solo `{row["constraint_name"]}` senza `table_name`, rendendo impossibile la verifica dell'ownership anche volendo aggiungerla in `main()`.

**Fix:**
```python
# In _fetch_constraints: restituire set di tuple (table_name, constraint_name)
def _fetch_constraints(sb) -> set[tuple[str, str]]:
    # ... primary path:
    return {(row["table_name"], row["constraint_name"]) for row in resp.data}
    # ... fallback RPC (get_public_constraints deve restituire table_name):
    return {(row["table_name"], row["constraint_name"]) for row in resp.data}

# In main(): usare la tabella nel check
for table, name in EXPECTED_UNIQUE_CONSTRAINTS:
    found = (table, name) in live_constraints
    results.append((f"{table}.{name}", found))
```

Nota: richiede che anche le RPC `get_public_constraints()` e `get_public_columns()` in Supabase restituiscano la colonna `table_name` (è già inclusa nella SELECT di `information_schema.table_constraints` al path primario, riga 54).

---

## Warnings

### WR-01: ingest.yml — "Compute daily metrics" gira con dati stantii quando Garmin sync fallisce

**File:** `.github/workflows/ingest.yml:70-72`

**Issue:** Lo step "Compute daily metrics" ha `if: always()`, quindi viene eseguito anche quando il Garmin sync esce con codice 1 (dopo 3 tentativi falliti). In questo scenario, `coach.analytics.daily` calcola CTL/ATL/TSB, z-score HRV e readiness usando i dati più recenti già in DB (stantii) e li **scrive** in `daily_metrics` con il timestamp del giorno corrente. Il risultato è un record `daily_metrics` con data odierna ma basato su dati di uno o più giorni prima, che apparirà come "fresco" al briefing mattutino e alle query downstream.

Il problema è diverso dall'issue D-06 già corretto: quel fix blocca giustamente le modulazioni, ma la pipeline analitica continua a produrre output con dati stantii marcati come odierni.

**Fix:** Valutare se il comportamento `always()` su questo step sia intenzionale. Se si vuole preservarlo (ad es. per avere almeno una baseline di readiness anche senza sync Garmin), aggiungere un commento esplicito che documenti la scelta. Se invece si preferisce coerenza, cambiare in `if: success()`. Una via di mezzo: mantenere `always()` ma che `coach.analytics.daily` verifichi l'età dei dati Garmin prima di scrivere e loggi un warning esplicito se i dati hanno più di 8h.

```yaml
- name: Compute daily metrics
  # NOTA: if: always() intenzionale — calcola readiness anche su dati stantii
  # (Garmin fallito). daily.py deve loggare warning se dati > 8h.
  if: always()
  run: python -m coach.analytics.daily
```

### WR-02: tests/test_audit_resilience.py — test idempotency PIPELINE-04 non verifica la finestra temporale

**File:** `tests/test_audit_resilience.py:1050-1065`

**Issue:** `test_pipeline04_brief_idempotency_skips_when_already_sent` inietta una riga con `sent_at: "2026-06-07T06:00:00+00:00"`. La funzione `_brief_already_sent_today()` in produzione filtra su `.gte("sent_at", cutoff)` dove `cutoff = now - 6h`. Ma `_IdempotencyFakeQuery.gte()` (riga 1025) ignora i suoi argomenti e restituisce `self` senza filtrare le righe — la fake accetta sempre tutte le righe, qualunque sia il timestamp.

Conseguenza: se `_brief_already_sent_today` venisse refactored a usare un offset diverso (es. 24h invece di 6h) o rimuovesse il filtro `gte` per errore, `test_pipeline04_brief_idempotency_skips_when_already_sent` continuerebbe a passare perché la row con `sent_at` hardcoded viene restituita incondizionatamente. Il test prova solo che "se c'è una riga, ritorna True" — non prova che "ritorna True solo per righe nella finestra corretta".

**Fix:** Per testare la logica della finestra, iniettare una riga con `sent_at` nel passato remoto (es. >7h fa) e verificare che il risultato sia `False`. Questo richiede o un `gte` che filtra davvero nella fake, oppure un test separato con monkeypatching di `datetime.now`.

```python
def test_pipeline04_brief_idempotency_old_brief_does_not_block():
    """Una riga morning_brief più vecchia di 6h non deve bloccare il nuovo invio."""
    from unittest.mock import patch
    from datetime import datetime, timezone, timedelta
    from coach.planning.briefing import _brief_already_sent_today

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    fake_sb = _IdempotencyFakeSupabase(rows=[{"id": "old", "sent_at": old_ts}])
    # _brief_already_sent_today deve restituire False per righe fuori finestra
    # ATTENZIONE: con la fake attuale questo test FALLIREBBE (gte non filtra)
    # — serve aggiornare _IdempotencyFakeQuery.gte() per filtrare davvero.
    with patch("coach.planning.briefing.datetime") as mock_dt:
        mock_dt.now.return_value = datetime.now(timezone.utc)
        result = _brief_already_sent_today(fake_sb)
    assert result is False
```

### WR-03: scripts/verify_migrations.py — funzioni `_fetch_constraints` / `_fetch_columns` prive di type annotation su `sb`

**File:** `scripts/verify_migrations.py:43, 74`

**Issue:** Le convenzioni del progetto (CLAUDE.md, sezione "Language Conventions") richiedono che tutte le firme di funzione abbiano annotazioni di tipo. Le due funzioni private `_fetch_constraints(sb)` e `_fetch_columns(sb)` hanno il parametro `sb` senza annotazione. Lo stesso vale per `main()` che non dichiara `-> None`.

```python
# main() non ha return type annotation
def main() -> None:  # presente, OK
```

Riletto: `main() -> None` alla riga 102 è già annotata. Il problema è solo `sb` nelle due helper private. Il tipo corretto per `sb` è `supabase.Client` (già importato transitivamente via `get_supabase`).

**Fix:**
```python
from supabase import Client

def _fetch_constraints(sb: Client) -> set[tuple[str, str]]:
    ...

def _fetch_columns(sb: Client) -> set[tuple[str, str]]:
    ...
```

---

## Info

### IN-01: verify_migrations.py — path primario `information_schema` è dead code in produzione Supabase

**File:** `scripts/verify_migrations.py:50-61`

**Issue:** Come documentato nel commento (riga 47-48) e nella 03-01-SUMMARY, PostgREST su Supabase restituisce PGRST106 su `information_schema`, quindi il path primario (righe 50-61) non funziona mai in produzione e cade sempre nel fallback RPC. Il path primario esiste per ambienti con accesso Postgres diretto, ma nella realtà operativa di questo progetto (GitHub Actions → Supabase cloud) è sistematicamente bypassed.

Questo è un difetto di manutenibilità: chiunque legga il codice assume che il path primario venga eseguito, scrive test per esso, o lo modifica credendo che impatti la produzione. La 03-01-SUMMARY lo riconosce ma non è documentato nel codice.

**Fix (minimo):** Aggiungere un commento esplicito:
```python
# NOTA: In produzione Supabase, questo path restituisce PGRST106 (information_schema
# non esposta via PostgREST) e cade sempre nel fallback RPC. Il path primario è
# mantenuto per ambienti con accesso Postgres diretto (es. test locali con pg).
try:
    resp = (
        sb.schema("information_schema")
        ...
```

### IN-02: tests/test_audit_resilience.py — linea 325 con spaziatura inconsistente nel `with` statement

**File:** `tests/test_audit_resilience.py:325`

**Issue:** La riga 325 ha una spaziatura anomala tra la virgola e il secondo `patch()`:
```python
    with patch.object(budget, "datetime", _DT_leap),          patch("coach.utils.budget.get_supabase") as mock_sb:
```
Ci sono 10 spazi extra prima di `patch(...)`. Non impatta la correttezza ma viola le convenzioni di formattazione del progetto (4-space indentation, no excessive whitespace).

**Fix:**
```python
    with patch.object(budget, "datetime", _DT_leap), \
         patch("coach.utils.budget.get_supabase") as mock_sb:
```

---

_Reviewed: 2026-06-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
