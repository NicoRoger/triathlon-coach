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

Nessun mesociclo attivo.

Carico al 2026-08-09: CTL 20.88 | ATL 1.27 | TSB 19.61 | readiness 73/100 (caution)

Prossime gare:
- 2026-08-29 (20gg): Lavarone Cross Sprint [A] — Lavarone

## Baseline fisiologiche (finestra 28gg)
- HR riposo: 51 bpm tipica (range 44-59)
- HRV rMSSD baseline: 81 ms (n=28)

## Pattern osservati (belief non flaggate, weak+)
- [weak_belief n=7 conf=0.93] RPE sottostimato in bici Z3-Z4 (delta -1.5, RPE 2 con gambe pesanti)
- [weak_belief n=7 conf=0.93] Tendenza a superare le zone di intensità previste nelle sessioni di tecnica/recupero (HR media 151bpm in Z2, picchi a 175bpm)
- [validated_belief n=12 conf=0.85] Difficoltà a mantenere il focus tecnico in sessioni lunghe di nuoto (durata > 3000s, distanza > 3km, RPE non allineato)

## Storico test fisiologici

| Data | Disciplina | Metodo |
|---|---|---|
| 2026-06-21 | run | manual_heat_corrected |
| 2026-06-04 | swim | CSS Test 400-200 (vasca lunga 50m, 04/06/2026) |
| 2026-05-30 | run | threshold_run_20min_provisional |
| 2026-05-26 | bike | FTP Test 20min (26/05/2026, Padova, percorso piatto) |
