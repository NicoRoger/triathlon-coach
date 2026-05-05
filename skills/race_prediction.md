---
name: race_prediction
description: Predizione realistica del tempo gara basata sui dati attuali dell'atleta. Da invocare quando l'atleta chiede "come potrei andare a [gara]" o "previsione tempo gara". Restituisce range con confidence interval, NON un singolo numero.
---

# Race Prediction

## Quando usare

Trigger:
- "come potrei andare a Lavarone"
- "previsione tempo gara"
- "siamo pronti per [gara]"
- Automaticamente nei brief T-14, T-7, T-3, T-1 per la gara A

## Filosofia

La predizione **non è una garanzia**, è uno strumento di calibrazione.
Serve a:
1. Capire se i target sono realistici
2. Decidere strategia gara (parto forte? gestisco? recupero in corsa?)
3. Confrontare progressi nel tempo (T-12 vs T-7 vs T-3)

**Il valore principale è il TREND**, non il valore puntuale.
Se da T-12 a T-3 la stima migliora di 4 minuti, sai che il taper sta
funzionando. Se peggiora, qualcosa non va.

## Procedura

### Step 1 — Verifica dati disponibili

Predizione affidabile richiede:
- Zone fisiologiche aggiornate (`physiology_zones` recente, < 6 settimane)
- Almeno 4 settimane di dati continui di allenamento
- Per gara cross/triathlon: dati specifici brick + OWS se disponibili

Se mancano: **dichiara onestamente "predizione non affidabile, dati insufficienti"** e specifica cosa serve. Non inventare numeri.

Esempio output quando i dati mancano:
Predizione Lavarone — non disponibile
Mi mancano:

FTP bici (test schedulato settimana 6)
Threshold pace corsa (test schedulato settimana 6)
Almeno 1 brick MTB+trail completato (settimana 9 in poi)

Posso fare una stima molto larga basata su:

VO2max 50 ml/kg/min (Garmin)
PB 5K 3:20/km (storico, 2022)
Tempo storico migliore cross sprint: [da chiedere]

Range stima molto larga: 1:25 - 1:50 (range 25 min, troppo per essere utile)
Aggiorniamo dopo i test di metà giugno.

### Step 2 — Stima per disciplina

#### Nuoto OWS (Open Water Swim) 750m
1. Parti dal CSS attuale (s/100m) da `physiology_zones`
2. Adjustment: +5-10% per OWS vs vasca (Friel)
3. Adjustment: +3-5% per gruppo gara (drafting/scia ma anche turbolenze)
4. Calcolo: `time_750m = (CSS × 7.5) × 1.08 × 1.04`

Esempio con CSS 1:20/100m (post-test ipotizzato):
- 80s × 7.5 = 600s base
- × 1.08 (OWS) = 648s
- × 1.04 (gruppo) = 674s = ~11:14
- Range: 11:00 - 11:30

#### MTB cross 17 km, dislivello noto
1. Parti dal FTP attuale (W) da `physiology_zones`
2. Calcola W/kg = FTP / peso
3. Per cross sprint, expected average power = ~85% FTP per 50 min effort
4. Stima velocità da W/kg + profilo:
   - Pianeggiante: ~25-28 km/h a 3.5-4.0 W/kg
   - Vallonato (Lavarone): ~18-22 km/h
   - Tecnico: -10% per gestione MTB

Esempio con FTP 250W (ipotetico post-test):
- W/kg = 250/68 = 3.68
- Avg power 50min = 213W
- Velocità stimata vallonato tecnico = ~20 km/h
- Tempo 17km = 51 min
- Range: 50-55 min

#### Trail 5K post-bike
1. Parti dal threshold pace corsa attuale
2. Adjustment: +10-15% per fatica post-bike (degradation)
3. Adjustment: +5% per terreno trail vs asfalto
4. Adjustment per dislivello: +20-30s per ogni 50m positivi

Esempio con threshold pace 4:00/km (ipotetico post-test):
- Base 4:00/km
- × 1.12 (post-bike) = 4:29/km
- × 1.05 (trail) = 4:42/km
- 5K = 23:30
- Aggiungi 1-2 min per dislivello specifico se applicabile
- Range: 22:30 - 25:00

### Step 3 — Transizioni

Stime conservative per cross sprint:
- T1 (uscita acqua → bici): 60-90s con calza/scarpa MTB
- T2 (bici → corsa): 30-45s con scarpa cambio rapido

### Step 4 — Composizione finale

Somma + range complessivo. Esempio composizione completa:
Predizione Lavarone Cross Sprint (T-X giorni)
Confidence: media (zone aggiornate al [data], 2 brick completati)
Composizione stimata:

Nuoto 750m OWS: 11:00 - 11:30
T1: 60-90s
MTB 17km Monte Rust: 50:00 - 55:00
T2: 30-45s
Trail 5km post-bike: 22:30 - 25:00

TEMPO TOTALE: 1:24:30 - 1:32:30
Posizionamento atteso: dipende dal field di Lavarone 2026.
Storico edizioni 2023-2025: 13°-18° = 1:25-1:32.
Sei dentro la zona target.

### Step 5 — Trend nel tempo

Quando hai più predizioni nel tempo, mostrale insieme:
Evoluzione predizione 2026:
T-12 settimane (1° giugno): 1:30 - 1:50 (range 20 min, dati scarsi)
T-8 settimane (29 giugno): 1:28 - 1:42 (range 14 min, post-test)
T-4 settimane (24 agosto): 1:25 - 1:35 (range 10 min, brick fatti)
T-1 settimana (~31 agosto): 1:26 - 1:32 (range 6 min, taper iniziato)
Trend: positivo, range si stringe = preparazione che converge.

## Cosa NON fare

- ❌ Non dare un singolo numero come predizione. Sempre range con confidence
- ❌ Non promettere posizioni: dipendono dal field, non solo da te
- ❌ Non basare predizioni su dati > 6 settimane vecchi senza warning
- ❌ Non usare PB storici (es. 5K 3:20/km del 2022) come se fossero attuali
- ❌ Non confondere "ottimismo motivante" con onesta valutazione: l'atleta
  ha bisogno di realtà, non di pacche sulla spalla

## Riferimenti

- Friel "Triathlete's Training Bible" — degradation OWS e post-bike
- Coggan "Training and Racing with Power" — W/kg e prestazione bici
- Daniels "Daniels' Running Formula" — equivalenti VDOT per pace