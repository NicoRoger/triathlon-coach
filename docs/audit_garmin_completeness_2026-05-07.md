# Audit Completezza Garmin — 8 maggio 2026

> Report Step 5.1 — Task 0. Generato manualmente + script `scripts/audit_payload_coverage.py`.

## 1. Inventario endpoint Garmin (Task 0.1)

### Endpoint chiamati

| # | Metodo | Aggiunto in | Usato per |
|---|--------|-------------|-----------|
| 1 | `get_activities_by_date(start, end)` | Step 4.0 | Lista attività nel range |
| 2 | `get_user_summary(date)` | Step 4.0 | Body battery min/max, stress avg, RHR |
| 3 | `get_sleep_data(date)` | Step 4.0 | Sleep score, HRV notturno, fasi sonno, **sleep stress** |
| 4 | `get_hrv_data(date)` | Step 4.0 | HRV summary e status |
| 5 | `get_max_metrics(date)` | Step 4.2 | VO2max running e cycling |
| 6 | `get_training_status(date)` | Step 4.2 | Training status, acute/chronic load |
| 7 | `get_training_readiness(date)` | **Step 5.1** | Training readiness score (0-100) |
| 8 | `get_activity_splits(id)` | **Step 5.1** | Split per km/lap con pace, HR, elevation |
| 9 | `get_activity_weather(id)` | **Step 5.1** | Meteo durante attività (T°, vento, umidità) |

**Totale: 9 endpoint (6 precedenti + 3 nuovi in Step 5.1)**

### Endpoint NON chiamati — Decision matrix

| Endpoint | Valore | Decisione | Note |
|----------|--------|-----------|------|
| `get_body_battery(start, end)` | Medio | DA VALUTARE | Min/max già sufficiente da user_summary |
| `get_stress_data(date)` | Medio | DA VALUTARE | Curva stress oraria, solo avg oggi |
| `get_race_predictor()` | Medio | DA VALUTARE | Cross-validation con race_prediction |
| `get_endurance_score(date)` | Medio | DA VALUTARE | Endurance score Garmin |
| `get_activity_typed_splits(id)` | Medio | DA VALUTARE | Utile per brick, edge case |
| `download_activity(id, dl_fmt)` | Variabile | DA VALUTARE | FIT/GPX, richiede storage (1-5MB/attività) |
| `get_respiration_data(date)` | Basso | SKIP | Rumore |
| `get_steps_data(date)` | Basso | SKIP | Non rilevante triathlon |
| `get_floors(date)` | Basso | SKIP | Irrilevante |
| `get_intensity_minutes(start, end)` | Basso | SKIP | Ridondante con TSS/zone |
| `get_pulse_ox(date)` | Basso | SKIP | Solo alta quota |
| `get_hill_score(date)` | Basso | SKIP | Specialistico |
| `get_personal_record()` | Basso | SKIP | Nice-to-have |
| `get_devices()` | Basso | SKIP | Diagnostico |
| `get_solar_data(date)` | Basso | SKIP | Irrilevante |
| `get_heart_rates(date)` | Basso | SKIP | Ridondante |
| `get_spo2_data(date)` | Basso | SKIP | Vedi pulse_ox |
| `get_activity_hr_in_timezones(id)` | Basso | SKIP | Ridondante con hr_zones_s |
| `get_activity_split_summaries(id)` | Basso | SKIP | Coperto da splits |
| `get_activity_exercise_sets(id)` | Basso | SKIP | Forza, poco usato |

### Criterio decisionale

- **DA AGGIUNGERE**: aiuta direttamente decisioni del coach
- **DA VALUTARE**: interessante ma non urgente
- **SKIP**: rumore, ridondante, non rilevante

---

## 2. Dati aggiunti in Step 5.1 (Task 0.4)

### daily_wellness — nuovi campi

| Campo | Sorgente | Tipo | Valore per il coach |
|-------|----------|------|---------------------|
| `training_readiness_score` | `get_training_readiness(date)` | SMALLINT | Score 0-100 proprietario Garmin che combina HRV, sleep, recovery time, training load. Alternativa/complemento al nostro readiness score. |
| `avg_sleep_stress` | `sleep.dailySleepDTO.averageSleepStress` | NUMERIC | Stress medio durante il sonno. Alto = recovery quality scarsa. Già nel raw_payload ma non estratto. |

### activities — nuovi campi

| Campo | Sorgente | Tipo | Valore per il coach |
|-------|----------|------|---------------------|
| `splits` | `get_activity_splits(id)` | JSONB | Array di split con pace, HR, elevation per km/lap. Essenziale per pace consistency e negative split analysis. |
| `weather` | `get_activity_weather(id)` | JSONB | Condizioni meteo: temperatura, vento, umidità, condizioni. Critico per race week planning. |

### daily_metrics — nuovo campo

| Campo | Sorgente | Tipo | Valore per il coach |
|-------|----------|------|---------------------|
| `garmin_training_readiness` | Da `daily_wellness.training_readiness_score` | SMALLINT | Passthrough per confronto con readiness nostro nel brief mattutino. |

---

## 3. Coverage prima/dopo Step 5.1

> Da eseguire con `python scripts/reprocess_recent.py --days 30`

### Prima dello Step 5.1

```
daily_wellness colonne popolate: 15/16 (94%)
   - Mancanti: training_readiness_score, avg_sleep_stress (non esistevano)
activities colonne popolate: 15/17 (88%)
   - Mancanti: splits, weather (non esistevano)
```

### Dopo lo Step 5.1 (atteso)

```
daily_wellness colonne popolate: 17/18 (94%)
   + training_readiness_score: popolato se Garmin lo supporta per il device
   + avg_sleep_stress: popolato se il dato è nel sleep payload
activities colonne popolate: 17/19 (89%)
   + splits: popolato per tutte le attività con lap data
   + weather: popolato per attività outdoor con dati meteo disponibili
```

> [!NOTE]
> Il miglioramento assoluto in % potrebbe sembrare modesto perché le colonne precedenti erano già ben popolate. Il valore reale è nei **nuovi segnali qualitativi** (readiness, pace consistency, meteo gara) che prima erano completamente assenti.

---

## 4. Impatto sulle decisioni del coach

| Nuovi dati | Come li usa il coach |
|------------|---------------------|
| `training_readiness_score` | Brief mattutino: confronto con readiness nostro. Se discrepano significativamente (>15 punti), il brief lo segnala. Weekly review: trend settimanale. |
| `avg_sleep_stress` | Weekly review: se media settimanale alta, segnale di recovery quality degradata. Correlazione con HRV trend. |
| `splits` | Weekly review: analisi pace consistency. Trend positivo = miglior pacing. Race prediction: dati per calibrare modello. |
| `weather` | Race week: meteo delle attività recenti vs forecast gara. Propose session: in race week, adatta intensità a condizioni meteo. |

---

## 5. Performance e rate limit

### Impatto stimato

- **sync_wellness**: +1 chiamata/giorno (`get_training_readiness`). 7 giorni = +7 chiamate. Accettabile.
- **sync_activities**: +2 chiamate/attività (`get_activity_splits`, `get_activity_weather`). Con rate limit 0.3s per chiamata, 10 attività = +6 secondi. Accettabile.
- **Totale giornaliero (7d window)**: da ~21 chiamate a ~35 chiamate. Entro i limiti Garmin.

### Mitigazione

- Rate limiting `time.sleep(0.3)` tra chiamate per-activity
- Ogni endpoint nuovo è wrappato in try/except individuale
- Fallimento di un endpoint non blocca il sync del record
