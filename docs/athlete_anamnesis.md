# Anamnesi Atleta — Nicolò Ruggero

> FILE GENERATO AUTOMATICAMENTE da `scripts/generate_anamnesis.py` — non modificare a mano:
> ogni run lo riscrive da zero. Fonte di verità: il database (physiology_zones,
> active_constraints, mesocycles, beliefs, daily_metrics/wellness).
> Profilo statico, storia e pattern mentali restano in CLAUDE.md §2.

## Soglie e zone correnti (misurate)

### Run — LTHR 172 bpm | soglia 4:20/km | HRmax 194
*Metodo: manual_heat_corrected — valido dal 2026-06-21*
- Z1_recovery: >5:25/km
- Z2_endurance: 4:59-5:25/km
- Z3_tempo: 4:33-4:59/km
- Z4_threshold: 4:12-4:33/km
- Z5_vo2max: <4:12/km

### Swim — CSS 1:20/100m
*Metodo: CSS Test 400-200 (vasca lunga 50m, 04/06/2026). 400m in 5:20 (320s), 200m in 2:40 (160s). CSS = (400-200)/(320-160) = 1.25 m/s = 80 s/100m. — valido dal 2026-06-04*
- CSS_minus5: 1:25/100m (endurance)
- CSS: 1:20/100m (threshold)
- CSS_plus5: 1:15/100m (VO2max)

### Bike — LTHR 170 bpm
*Metodo: FTP Test 20min (26/05/2026, Padova, percorso piatto). HR media 20' = 182 bpm. LTHR = 182 × 0.95 = 173, corretta a 170 per caldo (33°C alza HR di 5-8 bpm). Atleta SENZA wattmetro → zone basate su LTHR, non watt. — valido dal 2026-05-26*
- Z1_recovery: <138 bpm
- Z2_aerobic: 138-151 bpm
- Z3_tempo: 151-162 bpm
- Z4_threshold: 162-170 bpm
- Z5_above: >170 bpm

## Vincoli medici attivi

### run — severità media, stato n/d
fascite plantare sinistra: max +10% volume/settimana, cap 14-15km/settimana attuale, asintomatica da 14gg

### swim — severità bassa, in recupero (via libera progressivo)
spalla dx post borsite + tendinopatia CLB: via libera fisio ai carichi (29/06), fuori fase critica. Carichi nuoto liberi, intensità reintroducibile gradualmente. Continuare esercizi fisio.
*Nota: Via libera fisio 29/06 registrato — update bloccato finora dal bug circular JSON in update_constraint, fixato e deployato il 07/07.*

## Stato allenamento corrente

Mesociclo: **Ricostruzione post-stop cardiologico** (fase base) — settimana 1 di 4 (2026-09-29 → 2026-10-25)

Carico al 2026-09-30: CTL 12.07 | ATL 12.13 | TSB -0.06 | readiness 79/100 (ready)

## Baseline fisiologiche (finestra 28gg)
- HR riposo: 51 bpm tipica (range 46-64)
- HRV rMSSD baseline: 75 ms (n=24)

## Pattern osservati (belief non flaggate, weak+)
- [validated_belief n=10 conf=0.95] RPE sottostimato Z3-Z4 (delta -1.5, RPE 2 con gambe pesanti, incoerenza HR 155bpm)
- [validated_belief n=13 conf=0.95] Fatica muscolare braccia ricorrente + scarsa mobilità spalle (RPE 4, n=6 debrief, pace lenta)
- [validated_belief n=11 conf=0.93] Overpacing sistematico in sessioni aerobiche (pace 1:17/100m vs target 1:40/100m, HR 151bpm in Z2 target)
- [validated_belief n=13 conf=0.92] Overpacing Z2 sistematico (HR media 147bpm, NP 243W in Z2 target, 67.4% Z3 in gruppo)
- [validated_belief n=16 conf=0.87] Superamento zone in sessioni tecnica/recupero (HR media 151bpm in Z2 target, 80% Z3 in recovery)
- [weak_belief n=11 conf=0.59] Overpacing in test soglia (HR 194bpm, calo potenza finale, pacing irregolare)

## Storico test fisiologici

| Data | Disciplina | Metodo |
|---|---|---|
| 2026-06-21 | run | manual_heat_corrected |
| 2026-06-04 | swim | CSS Test 400-200 (vasca lunga 50m, 04/06/2026) |
| 2026-05-30 | run | threshold_run_20min_provisional |
| 2026-05-26 | bike | FTP Test 20min (26/05/2026, Padova, percorso piatto) |
