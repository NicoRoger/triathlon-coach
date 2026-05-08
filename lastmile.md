# Step 5.1 — Validazione completezza dati + Test & Hardening

## Contesto

Continuo a lavorare su `triathlon-coach`. Step 5.0 chiuso. Sospetto che la pipeline ingest stia estraendo solo una frazione dei dati che Garmin mette a disposizione. Voglio prima fare un audit serio di completezza, poi testare end-to-end tutto il sistema.

**Repo**: https://github.com/NicoRoger/triathlon-coach
**Branch**: main

## Task 0 — Audit completezza dati Garmin (PRIORITÀ MASSIMA)

### 0.1 — Inventario degli endpoint Garmin attualmente chiamati

Apri `coach/ingest/garmin.py` e lista TUTTI i metodi `garminconnect.Garmin.get_*()` che chiamiamo. Atteso:
- `get_activities_by_date(start, end)`
- `get_activity_details(id)`
- `get_user_summary(date)`
- `get_sleep_data(date)`
- `get_hrv_data(date)`
- `get_max_metrics(date)` (VO2max)
- `get_training_status(date)`

Verifica se ne mancano altri **rilevanti** per l'allenamento. Esempi di endpoint che `garminconnect` espone e che potremmo non chiamare:
- `get_body_battery(start, end)` — body battery time series, non solo min/max
- `get_stress_data(date)` — stress curve
- `get_respiration_data(date)` — respirazione notturna
- `get_steps_data(date)` — passi orari
- `get_floors(date)` — piani saliti
- `get_intensity_minutes(start, end)` — minuti intensità WHO
- `get_pulse_ox(date)` — saturazione ossigeno notturna
- `get_race_predictor()` — predizioni Garmin per 5K, 10K, mezza, maratona
- `get_training_readiness(date)` — score Garmin proprietary
- `get_endurance_score(date)` — endurance score Garmin
- `get_hill_score(date)` — hill score
- `download_activity(id, dl_fmt)` — file FIT/GPX/TCX/CSV con tutti i dati raw secondo per secondo
- `get_activity_splits(id)` — split per km/lap
- `get_activity_split_summaries(id)` — sommari split
- `get_activity_weather(id)` — meteo durante l'attività
- `get_activity_hr_in_timezones(id)` — tempo nelle 5 zone HR
- `get_activity_typed_splits(id)` — split tipizzati (bike vs run in brick)
- `get_activity_exercise_sets(id)` — esercizi forza con reps/weights
- `get_personal_record()` — PR Garmin
- `get_devices()` — dispositivi registrati
- `get_solar_data(date)` — esposizione solare (relevant per spalla/ricalibrazione)
- `get_heart_rates(date)` — HR continuo nella giornata
- `get_spo2_data(date)` — SpO2

Per ognuno, dichiara: "lo chiamiamo / non lo chiamiamo / non rilevante per il coach".

### 0.2 — Audit del raw_payload esistente

Per ognuna delle tabelle che ha `raw_payload` JSONB:
- `daily_wellness.raw_payload`
- `activities.raw_payload`

Crea uno script `scripts/audit_payload_coverage.py` che:
1. Prende un campione di 5 righe recenti
2. Estrae ricorsivamente TUTTI i path nel JSON (es. `sleep.dailySleepDTO.sleepScores.overall.value`)
3. Per ognuno verifica se viene mappato in una colonna nativa della tabella
4. Output: tabella `path → colonna_native | NON_MAPPATO`

Salva output in `docs/audit_garmin_completeness_2026-05-07.md`.

### 0.3 — Identifica dati di valore non estratti

Dall'output di 0.1 + 0.2, costruisci una tabella in `docs/audit_garmin_completeness_2026-05-07.md`:

| Endpoint/path Garmin | Estratto attualmente? | Valore per il coach | Decisione |
|----------------------|----------------------|---------------------|-----------|
| sleep.dailySleepDTO.avgSleepStress | NO | Alto: stress notturno = recovery quality | DA AGGIUNGERE |
| sleep.sleepScoreFeedback (testuale) | NO | Medio: feedback Garmin "stress positivo" | DA VALUTARE |
| activities.weatherInfo (T°, vento) | NO | Alto in race week, basso in training | DA AGGIUNGERE |
| activity_splits dettagliati | NO | Alto per analisi pace consistency | DA AGGIUNGERE |
| training_readiness daily score Garmin | NO | Alto: alternative a HRV per readiness | DA AGGIUNGERE |
| solar_data | NO | Basso | SKIP |
| download GPX/FIT files | NO | Variabile (utile per analisi profilo) | DA VALUTARE |

Criterio decisionale: "DA AGGIUNGERE" se aiuta direttamente decisioni del coach (sessione di oggi, race plan, gestione infortuni, predizione gara). "DA VALUTARE" se interessante ma non urgente. "SKIP" se rumore.

### 0.4 — Implementa l'estrazione dei "DA AGGIUNGERE"

Per ogni dato classificato "DA AGGIUNGERE":

a. **Se è già nel raw_payload**: aggiungi mapping in `_normalize_*()` e crea migration SQL per nuova colonna. Riprocessa dati storici con script in `scripts/`.

b. **Se richiede endpoint nuovo**: aggiungi chiamata in `coach/ingest/garmin.py` (gestita opzionalmente con try/except, niente fallimento se Garmin non lo restituisce per quel giorno).

c. **Se richiede download di file (GPX/FIT)**: implementa con cautela. Storage: bucket dedicato Supabase Storage `garmin-tracks` (cifrato), referenziato in `activities.track_path`. Solo per attività degli ultimi 90 giorni o gare. NON backfilltare 700 giorni di storico, costa tempo e spazio.

### 0.5 — Validazione del miglioramento

Riprocessa gli ultimi 30 giorni di dati con la pipeline aggiornata. Audit risultati:
PRIMA dello Step 5.1:

daily_wellness colonne popolate: X/Y (Z%)
activities colonne popolate: A/B (C%)

DOPO lo Step 5.1:

daily_wellness colonne popolate: X'/Y' (Z'%)
activities colonne popolate: A'/B' (C'%)


Se l'aumento di copertura è < 30%, c'è poco valore aggiunto e va spiegato perché. Se è > 30%, abbiamo successo.

### 0.6 — Aggiorna documentazione

- `docs/audit_garmin_completeness_2026-05-07.md`: report completo
- `docs/SYSTEM_STATUS.md`: aggiorna con nuovi campi
- `CLAUDE.md` §12 "Note operative": aggiungi riferimento a nuovi dati disponibili
- `coach/ingest/garmin.py`: docstring aggiornata con tutti gli endpoint chiamati

## Task 1-5 — Test & Hardening

[Resto del prompt come prima — i 12 test, runbook, smoke test, ecc.]

[Stesso contenuto di Step 5.1 originale, dal Task 1 in poi]

## Output atteso

1. ✅ Audit completezza Garmin completo, doc dedicata
2. ✅ Nuovi campi aggiunti dove ha senso, dati storici riprocessati
3. ✅ scripts/smoke_test.py
4. ✅ scripts/audit_payload_coverage.py
5. ✅ E2E_TEST_LOG aggiornato con 12 test
6. ✅ RUNBOOK con 5 procedure recovery
7. ✅ Documentazione tutta aggiornata
8. ✅ Commit pushato

## Vincoli importanti per Task 0

- **Performance**: ogni chiamata API a Garmin è un round-trip. Non aggiungere 10 chiamate nuove giornaliere senza verificare che il workflow sotto i 15min di timeout
- **Rate limit**: Garmin in passato ha rate-limited fino a banni temporanei se troppe chiamate. Rispetta cautela
- **Storage GPX/FIT**: file da 1-5MB ognuno per attività lunga. 100 attività = ~200MB. Free tier Supabase Storage 1GB. Quindi ok ma occhio
- **Cifratura**: i file GPX contengono geolocalizzazione precisa. Cifrali in storage con AES-256-GCM (riusa la chiave DR_ENCRYPTION_KEY o nuova)
- **Risks**: prima di backfillare storico Garmin, fai un piccolo POC su 5-10 attività e misura tempo. Estrapola

## Note per il coach AI

I dati nuovi devono essere effettivamente USATI dal coach, non solo memorizzati. Aggiorna le skill in `skills/` per dirgli di leggere i nuovi campi quando rilevanti:

- `weekly_review.md`: cita avg_sleep_stress se anomalo, cita training_readiness Garmin score se discrepa con readiness nostro
- `propose_session.md`: in race week, considera weather forecast se disponibile
- `race_week_protocol.md`: weather del race day mandatory nella checklist T-2

E aggiorna `CLAUDE.md` §6 "Stile comunicativo" perché il brief mattutino consideri le nuove dimensioni.

## Cosa fare se Task 0 dura troppo

Task 0 è impegnativo. Se a metà sessione vedi che non chiudi tutto:
- Completa SOLO Task 0 (audit + decision matrix), implementa le top 3-5 priorità
- Lascia il resto come TODO documentato
- Skippa o rimanda Task 1-5 alla prossima sessione

Meglio Task 0 ben fatto che 6 task incompleti.