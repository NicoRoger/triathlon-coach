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
2. Chiama `get_weekly_context()`. Estrai:
   - `active_constraints` (solo resolved_at IS NULL): **QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md**. La fonte di verità è il DB — non prescrivere sessioni in contrasto con nessun vincolo attivo.
   - `active_mesocycle` + `current_progression_step`: passo corrente della progressione qualità.
   - `daily_metrics`: TSB, HRV z-score, readiness score.
   - `daily_wellness`: sleep score, temperatura prevista (weather).
   - `active_beliefs` (confidence >= 0.55): leggi i beliefs fisiologici attivi. Per ogni belief rilevante alla disciplina del giorno, applicalo inline con tag `[athlete-belief: <belief_key>] — <motivazione specifica>`. Il tag appare nella riga del main set o del razionale dove il belief ha influenzato la scelta (non in sezione separata). La citazione `[athlete-belief: ...]` è **obbligatoria** quando `active_beliefs` contiene un belief pertinente alla disciplina prescritta.
   - `last_fatigue_by_sport`: fatica dell'ultima sessione per la disciplina del giorno. Se `type == 'muscular'` e `confidence >= 0.6`: verifica che il main set non superi la soglia neuromuscolare (referenza belief `endurance_failure_type`).
3. Leggi `get_recent_metrics(days=7)` per capire stato corrente (TSB/HRV/readiness se non già in get_weekly_context)
4. Leggi `physiology_zones` correnti per disciplina
5. Leggi `docs/coaching_observations.md` e `docs/athlete_beliefs.md` per pattern/beliefs rilevanti per oggi (giorno settimana, sport, fase)
6. Adatta la prescrizione alla readiness:
   - Se readiness ≥ 75 e nessun flag → sessione come da piano
   - Se readiness 50-74 → riduci intensità di 1 step (es. soglia → tempo, VO2 → soglia)
   - Se readiness < 50 → proponi recovery o riposo (richiede `propose_plan_change`)
6. **In race week** (Step 6.1): controlla `activities.weather` delle attività recenti.
   Se temperatura prevista >30°C o vento forte, adatta intensità (-5-10% target) e
   aggiungi note su idratazione extra. Vedi anche forecast esterno se disponibile.
7. Output strutturato con:
   - Warm-up esplicito (durata, zona)
   - Main set (intervalli, durate, zone, recupero)
   - Cool-down
   - Note tecniche/contestuali
   - **Condizioni meteo** se disponibili da weather data (Step 6.1)

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

## Citation obbligatoria (Fase 2.4)

Quando giustifichi la scelta di intensità/zone/struttura della sessione, cita la base scientifica con tag inline:

`[source: <autore> <anno>]`

Esempi:
- Z2 lungo → `[source: Seiler 2010]`
- Soglia → `[source: Coggan 2003]`
- Recovery <50% readiness → `[source: Halson 2014 recovery monitoring]`

Quando `active_beliefs` (da `get_weekly_context`) contiene un belief pertinente alla disciplina prescritta, la citazione `[athlete-belief: <belief_key>]` è **obbligatoria** — non opzionale. Usa il `belief_key` come identificatore (es. `[athlete-belief: endurance_failure_type]`). Il tag appare inline nel main set o nel razionale, non in sezione separata. Esempio:
```
Main set: 5×6min @ Z4, rec 2min Z1
[athlete-belief: endurance_failure_type] — capped a 5 reps (cedimento muscolare Nicolò su interval >6 reps)
```

## Cosa NON fare
- Mai prescrivere intensità/zone se le `physiology_zones` per quella disciplina
  sono `NULL` o oltre 12 settimane vecchie. Suggerisci test fitness invece.
- Mai ignorare flag attivi. Se `illness_flag` o `injury_flag` → recovery, fine.
- Mai inventare riferimenti scientifici. Se incerto, usa `[source: principio generale endurance]`.
