# Fitness Test Protocol — Schemi Strutturati

> Questo documento definisce i protocolli di test fitness che il coach DEVE usare
> quando propone un test. Lo schema `structured` viene salvato in `planned_sessions`
> e letto dal processore automatico dopo il sync Garmin.

---

## Convenzione nomi Garmin (NON NEGOZIABILE)

Il coach DEVE sempre comunicare all'atleta il nome esatto da usare su Garmin.
Il processore automatico usa il campo `garmin_activity_name` per il matching.

---

## Test disponibili

### FTP Bike 20min

```json
{
  "test_type": "ftp_bike_20min",
  "protocol": "20min_steady_state",
  "garmin_activity_name": "FTP Test 20min",
  "warmup": "20min progressive Z1→Z2, 3x1min spin-up",
  "main_set": "20min all-out steady state (non partire troppo forte, pacing negativo)",
  "cooldown": "10min Z1 easy spin",
  "extraction": {
    "primary": {
      "field": "avg_power_w",
      "source": "splits",
      "interval_index": 1,
      "formula": "value * 0.95"
    },
    "fallback": {
      "field": "avg_power_w",
      "source": "activity",
      "formula": "value * 0.90"
    }
  },
  "zones_to_update": ["bike_power"],
  "zone_system": "coggan_7zone",
  "claude_md_field": "ftp_attuale_w"
}
```

### FTP Bike Ramp

```json
{
  "test_type": "ftp_bike_ramp",
  "protocol": "ramp_to_exhaustion",
  "garmin_activity_name": "FTP Ramp Test",
  "warmup": "10min Z1 easy spin",
  "main_set": "Start at 100W, increase 20W every minute until failure. Record max power of last completed minute.",
  "cooldown": "10min Z1 easy spin",
  "extraction": {
    "primary": {
      "field": "max_power_w",
      "source": "activity",
      "formula": "value * 0.75"
    },
    "fallback": {
      "field": "avg_power_w",
      "source": "activity",
      "formula": "value * 1.10"
    }
  },
  "zones_to_update": ["bike_power"],
  "zone_system": "coggan_7zone",
  "claude_md_field": "ftp_attuale_w"
}
```

### Threshold Run 30min

```json
{
  "test_type": "threshold_run_30min",
  "protocol": "30min_maximal",
  "garmin_activity_name": "Threshold Run 30min",
  "warmup": "15min progressive Z1→Z2, 4x20s strides",
  "main_set": "30min massimale su terreno pianeggiante. Pacing conservativo primo km, poi steady.",
  "cooldown": "10min Z1 jog",
  "extraction": {
    "primary": {
      "field": "avg_pace_s_per_km",
      "source": "splits",
      "interval_index": 1,
      "formula": "value"
    },
    "fallback": {
      "field": "avg_pace_s_per_km",
      "source": "activity",
      "formula": "value * 1.02"
    }
  },
  "zones_to_update": ["run_pace"],
  "zone_system": "pace_5zone",
  "claude_md_field": "threshold_pace_per_km"
}
```

### CSS Swim 400+200

```json
{
  "test_type": "css_swim_400_200",
  "protocol": "400m_then_200m",
  "garmin_activity_name": "CSS Test 400+200",
  "warmup": "400m mix (100 SL + 100 drill + 100 pull + 100 gambe)",
  "main_set": "400m all-out (rest 5min), 200m all-out. CSS = (400m time - 200m time) / 2 in sec/100m",
  "cooldown": "200m easy",
  "extraction": {
    "primary": {
      "field": "splits",
      "source": "splits",
      "formula": "css_from_splits(splits)"
    },
    "fallback": {
      "field": "avg_pace_s_per_100m",
      "source": "activity",
      "formula": "value * 0.95"
    }
  },
  "zones_to_update": ["swim_pace"],
  "zone_system": "css_3zone",
  "claude_md_field": "css_attuale_per_100m"
}
```

### LTHR Run 30min (auxiliary)

```json
{
  "test_type": "lthr_run",
  "protocol": "30min_maximal",
  "garmin_activity_name": "LTHR Test 30min",
  "warmup": "15min progressive Z1→Z2",
  "main_set": "30min massimale con cardiofrequenzimetro. Stesso protocollo del threshold run, estraiamo HR media degli ultimi 20min.",
  "cooldown": "10min Z1 jog",
  "extraction": {
    "primary": {
      "field": "avg_hr",
      "source": "splits",
      "interval_index": 1,
      "formula": "value * 0.98"
    },
    "fallback": {
      "field": "avg_hr",
      "source": "activity",
      "formula": "value * 0.95"
    }
  },
  "zones_to_update": ["run_hr", "bike_hr"],
  "zone_system": "lthr_5zone",
  "claude_md_field": "lthr"
}
```

---

## Tempistiche e prerequisiti

- **Mai entro 48h** da un'altra sessione intensa (Z4+)
- **Preceduto da 2 giorni** Z1-Z2 o rest
- **HRV z-score > -0.5** il giorno del test (verificare nel brief mattutino)
- **Non in race week** e non in deload week

## Ciclo test consigliato

1. FTP Bike (20min o ramp) → 3 giorni recovery
2. Threshold Run (30min) → 3 giorni recovery
3. CSS Swim (400+200m) → 3 giorni recovery
4. LTHR (opzionale, dal run test)

Ciclo completo: 12-15 giorni. Pianificare solo in blocchi di sviluppo (mai in taper).
Frequenza: ogni 4-6 settimane.
