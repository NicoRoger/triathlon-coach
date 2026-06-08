---
name: propose_session
description: Dettaglia la sessione del giorno (o di una data specifica) con zone, durate, target. Usa quando l'atleta chiede "cosa faccio oggi", "dimmi la sessione" o quando il brief mattutino non basta.
---

# Propose Session

## Quando usare
- "Cosa faccio oggi?"
- "Dettagliami la sessione"
- "Adatta la sessione di oggi alla mia readiness attuale"

## Procedura obbligatoria (NON saltare nessuno step)

### Step 0 — GATE FISIOLOGICO (obbligatorio, nessuna prescrizione senza questo)
Chiama `get_physiology_zones(discipline)` dove discipline è il sport della sessione.
- Se il response ha `zones: []` o `note: "Nessuna zona..."`: NON prescrivere. Proponi test fitness.
- Se `age_days > 42`: segnala che le zone potrebbero essere obsolete e suggerisci test.
- Estrai i valori precisi: `ftp_w`, `threshold_pace_s_per_km`, o `css_pace_s_per_100m`.
- Tutti i target numerici nella prescrizione DEVONO venire da questi valori.

**NON procedere con la prescrizione finché non hai ricevuto il response di `get_physiology_zones`.**

### Step 1 — Sessione pianificata
Chiama `get_planned_session(today)` per leggere la sessione del giorno.

### Step 2 — Contesto settimanale + vincoli medici
Chiama `get_weekly_context()`. Estrai:
- `active_constraints` (solo resolved_at IS NULL): **QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md**. La fonte di verità è il DB — non prescrivere sessioni in contrasto con nessun vincolo attivo.
- `active_mesocycle` + `current_progression_step`: passo corrente della progressione qualità.
- `daily_metrics`: TSB, HRV z-score, readiness score.
- `daily_wellness`: sleep score, temperatura prevista (weather).

### Step 3 — Storico disciplina (ultime 3 sessioni, 14gg)
Chiama `get_activity_history(sport=<disciplina>, days=14)`.
- Leggi RPE delle ultime 3 sessioni e le `session_analyses` corrispondenti per pattern fatica.
- **Se RPE medio >= 8.0 o pattern "fatica neuromuscolare" (HR drift > 15bpm nelle ultime 20min di intensità):** riduci il volume del main set di 1 step (es. 5×6min → 4×6min) e aggiungi nota esplicita: "Volume ridotto: RPE medio ultimi 14gg = X.X/10."

### Step 4 — Adatta a readiness e condizioni
Logica readiness a 3 livelli:
- Readiness >= 75 e nessun flag → sessione come da piano
- Readiness 50-74 → riduci intensità di 1 step (es. soglia → tempo, VO2 → soglia). **Se applichi questa riduzione, NON applicare anche il blocco "Condizioni avverse" — una sola riduzione per sessione.**
- Readiness < 50 → proponi recovery o riposo (richiede `propose_plan_change`)

**Contestualizzazione zone (condizioni avverse):** Applicare SOLO se readiness >= 75 (nessuna riduzione di intensità già applicata). Se >= 2 fattori avversi tra { temperatura prevista >25°C, TSB <-10, sleep score <65 } sono presenti, esprimi il target come **PERCEIVED EFFORT** (non pace/watt assoluti) con nota esplicita: "Condizioni avverse: [condizione]. Corri a sensazione Z4 — pace di riferimento ~[pace adattata] invece di [pace nominale]." `[source: Périard 2015]`

### Step 5 — Race-pace Lavarone (solo per sessioni race-specific)
Per sessioni di tipo race-pace, chiama `race_prediction` + `get_race_context` (dati Lavarone: distanza, dislivello, tipo fondo cross) **PRIMA** di prescrivere. Calibra i target sulla fitness corrente — non hardcodare. I target si aggiornano automaticamente con la fitness misurata.

---

## Drill tecnici Nicolo

I drill tecnici sono parte **INTEGRANTE** della sessione (nel warmup o nel main set), mai aggiunta opzionale. Ogni sessione include almeno 1-2 drill rilevanti per la disciplina.

### Nuoto (shoulder-safe)
- Pull drill con pull buoy (scarica la spalla destra)
- DPS count (conteggio bracciate per vasca per efficienza tecnica)
- Kick lavoro con pinne (shoulder relief — spalla dx attiva parzialmente)
- Fingertip drag (fase catch — attivazione propriocettiva)

### Bici
- Big gear intervals (50-55rpm per 3-5min): muscular endurance (cedimento muscolare — non cardio)
- Cadenza drill (100rpm+ per 3×30sec): efficienza neuro-muscolare
- Climbing position: stabilità core e postura salita (rilevante per Lavarone cross)

### Corsa (post-fascite precauzione)
- Strides (8×80m a 5km pace): attivazione neuromuscolare e meccanica post-fascite. **GUARD: includi SOLO se `injury_flag = false` E readiness >= 65. Se `active_constraints` include fascite con severity='high', sostituisci con cadenza drill** (RPE muscolare > 6 in zona fascite viola CLAUDE.md §5.2 injury_flag).
- Marcia di attivazione tibiali (ankle dorsiflexion drill): profilassi fascite plantare
- Cadenza drill (incrementa di 5spm per 30sec): riduzione impatto per fascite sx

---

## Template output (OBBLIGATORIO — mai deviare da questa struttura)

```
[Sport emoji] [Sport] — [tipo sessione] — [durata totale]min

Contesto mesociclo
Settimana [N]/3 del blocco [fase]
TSS accumulato: [X] / ~[Y] (target settimana)
Sessioni qualita questa settimana: [n] ([dettaglio])
Ruolo di oggi: [descrizione specifica — es. "Z2 obbligatorio pre-interval run domani"]

Vincoli attivi: [da active_constraints — se vuoto: "nessun vincolo attivo"]

Warm-up: [durata]min [zona] ([descrizione progressiva]). [Source tag]
Drill block: [drill specifici per disciplina/fase — 1-2 drill dalla sezione Drill tecnici]
Main set: [N×Xmin @ zona/target numerico preciso, rec Ymin zona]
Cool-down: [durata]min [zona]

Target TSS: ~[X]
Zone di riferimento: [valori da physiology_zones — watt/pace/s100m]
[Condizioni avverse se >=2 fattori: perceived effort Z4, ~[pace adattata]]
```

**Committa con `commit_plan_change`** includendo:
- `target_tss`: valore numerico stimato
- `structured`: flat steps list nel formato `[{name, duration_s, zone, target_value, reps?, notes?}]`
  - Almeno un step `warmup`, uno o piu `main_set` (con intervalli espliciti), un `cooldown`
  - `target_value` deve contenere il valore numerico preciso da `physiology_zones` (watt / s-km / s-100m)
  - Per il nuoto, includi `notes` leggibile (es. `"CSS-5: 1:35/100m"`) oltre al `target_value` numerico in s/100m

Esempio JSONB canonical:
```json
{
  "structured": [
    {"name": "warmup",   "duration_s": 900,  "zone": "Z1-Z2", "notes": "progressivo"},
    {"name": "drill",    "reps": 4, "duration_s": 50, "zone": "Z1", "target_value": "fingertip drag"},
    {"name": "main_set", "reps": 6, "duration_s": 360, "zone": "Z4", "target_value": 210, "notes": "@ 105% FTP"},
    {"name": "cooldown", "duration_s": 600,  "zone": "Z1"}
  ]
}
```

---

## Zone reference (versionate in DB)
Sempre lette da `physiology_zones` corrente via Step 0. Non hardcodare valori.

## Citation obbligatoria (Fase 2.4)

Quando giustifichi la scelta di intensità/zone/struttura della sessione, cita la base scientifica con tag inline:

`[source: <autore> <anno>]`

Esempi:
- Z2 lungo → `[source: Seiler 2010]`
- Soglia → `[source: Coggan 2003]`
- Recovery <50% readiness → `[source: Halson 2014 recovery monitoring]`

Quando applichi una belief: `[athlete-belief: <descrizione>]`.

## Cosa NON fare
- Mai prescrivere intensità/zone se le `physiology_zones` per quella disciplina
  sono `NULL` o oltre 12 settimane vecchie. Suggerisci test fitness invece.
- Mai ignorare flag attivi. Se `illness_flag` o `injury_flag` → recovery, fine.
- Mai inventare riferimenti scientifici. Se incerto, usa `[source: principio generale endurance]`.
- Mai leggere vincoli medici da CLAUDE.md statico — usa `get_weekly_context.active_constraints` (D-16).
- Mai prescrivere "X min Z2" come unica riga — ogni sessione ha warmup/main set/cooldown espliciti (D-03).
