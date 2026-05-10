# Audit Resilienza Ingest Pipeline

**Data:** 2026-05-09
**Componente:** `coach.ingest.garmin` e `ingest.yml`

## 1. Scenari di Failure Garmin

### Auth Failure (Token Scaduto)
- **Sintomo:** Chiamata API Garmin restituisce 401.
- **Reazione Sistema:** Lo script solleva un'eccezione non gestita. Il workflow `ingest.yml` fallisce. Il table `health` NON si aggiorna con `success=True`.
- **Mitigazione in Atto:** Il `watchdog.yml` rileverà che `garmin_sync` non ha avuto successo per > 8 ore e invierà un alert Telegram: "🚨 garmin_sync: Xh dall'ultimo successo".
- **Esito:** ✅ Graceful failure con allarme automatico.

### Rate Limit (429)
- **Sintomo:** Garmin API blocca le chiamate per "too many requests".
- **Reazione Sistema:** Il client solleverà eccezione. Il behavior è identico all'Auth Failure.
- **Esito:** ⚠️ Degraded. Non ci sono backoff exponentiali espliciti nel codice ingest, se fallisce riprova semplicemente all'ora successiva via cron. P2.

### Data Corruption / Sessioni Vuote
- **Sintomo:** Attività salvata manualmente su Garmin con distanza 0 o senza frequenza cardiaca.
- **Reazione Sistema:** `garmin.py` usa `.get()` per i campi opzionali e non richiede strettamente HR o Power per l'inserimento in DB. Le attività vengono salvate in Supabase, poi le view di Supabase o `daily_metrics` gestiscono a valle i NULL (es: `pmc` tratta load 0).
- **Esito:** ✅ Ok.

## 2. Test Idempotenza
- **Test:** Esecuzione di `python -m coach.ingest.garmin` multipla in rapida sequenza.
- **Risultato:** Supabase `activities` ha un `UNIQUE (external_id, source)` constraint, abbinato al `on_conflict` (nella logica upsert).
- **Esito:** ✅ Ok. Perfettamente idempotente.

## 3. Analisi Ordine Workflow (`ingest.yml`)
- **Step 1: Garmin Sync** -> Se fallisce, il processo GitHub Actions si ferma lì, fallendo il job. 
- **Step 2 e 3:** Non verranno eseguiti, evitando di calcolare `daily_metrics` senza dati aggiornati. Questo è il comportamento corretto (Fail Fast).
- **Esito:** ✅ Ok.

## 4. Bug Riscontrati e Fix Proposti
- Nessun P0/P1 critico individuato nel path di Ingest base, dato che i constraints DB impediscono la corruzione dei dati.
- *Issue P2:* Inserire un timeout e un retry block specifico (es. libreria `tenacity`) sulle chiamate Http HTTPX in `garmin.py` per sopravvivere ai glitch di rete temporanei.
