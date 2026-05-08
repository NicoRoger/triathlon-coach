---
name: propose_session
description: Dettaglia la sessione del giorno (o di una data specifica) con zone, durate, target. Usa quando l'atleta chiede "cosa faccio oggi", "dimmi la sessione" o quando il brief mattutino non basta.
---

# Propose Session

## Quando usare
- "Cosa faccio oggi?"
- "Dettagliami la sessione"
- "Adatta la sessione di oggi alla mia readiness attuale"

## Procedura
1. Leggi `get_planned_session(today)` via MCP
2. Leggi `get_recent_metrics(days=7)` per capire stato corrente
3. Leggi `physiology_zones` correnti per disciplina
4. Adatta la prescrizione alla readiness:
   - Se readiness ≥ 75 e nessun flag → sessione come da piano
   - Se readiness 50-74 → riduci intensità di 1 step (es. soglia → tempo, VO2 → soglia)
   - Se readiness < 50 → proponi recovery o riposo (richiede `propose_plan_change`)
5. **In race week** (Step 5.1): controlla `activities.weather` delle attività recenti.
   Se temperatura prevista >30°C o vento forte, adatta intensità (-5-10% target) e
   aggiungi note su idratazione extra. Vedi anche forecast esterno se disponibile.
6. Output strutturato con:
   - Warm-up esplicito (durata, zona)
   - Main set (intervalli, durate, zone, recupero)
   - Cool-down
   - Note tecniche/contestuali
   - **Condizioni meteo** se disponibili da weather data (Step 5.1)

## Template output
```
🏃 Soglia corsa — 60min totali

Warm-up: 15min progressivo Z1→Z2 (HR <140)
Main: 4×6min @ Z4 threshold pace (es. 4:05/km), recupero 2min Z1
Cool-down: 10min Z1

Target TSS: ~70
Razionale: TSB -5, HRV stabile, ultima soglia 5gg fa.

⚠️ Se a fine warm-up le gambe sono pesanti, sostituisci con 60min Z2 puri.
```

## Zone reference (versionate in DB)
Sempre lette da `physiology_zones` corrente. Non hardcodare valori.

## Cosa NON fare
- Mai prescrivere intensità/zone se le `physiology_zones` per quella disciplina
  sono `NULL` o oltre 12 settimane vecchie. Suggerisci test fitness invece.
- Mai ignorare flag attivi. Se `illness_flag` o `injury_flag` → recovery, fine.
