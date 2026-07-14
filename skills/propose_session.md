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

### Step 2 — Contesto settimanale + vincoli medici + beliefs fisiologici
Chiama `get_weekly_context()`. Estrai:
- `active_constraints` (solo resolved_at IS NULL): **QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md**. La fonte di verità è il DB — non prescrivere sessioni in contrasto con nessun vincolo attivo.
- `active_mesocycle` + `current_progression_step`: passo corrente della progressione qualità.
- `daily_metrics`: TSB, HRV z-score, readiness score.
- `daily_wellness`: sleep score, temperatura prevista (weather).
- `active_beliefs` (confidence >= 0.55): beliefs fisiologici attivi dell'atleta. Per ogni belief rilevante alla disciplina del giorno, applicalo e citalo inline con tag `[athlete-belief: <belief_key>] — <motivazione specifica applicata alla sessione>`. Il tag appare nella riga del main set o del razionale dove il belief ha influenzato la scelta, non in sezione separata. La citazione `[athlete-belief: ...]` è **obbligatoria** quando `active_beliefs` contiene un belief pertinente alla disciplina prescritta.
- `last_fatigue_by_sport`: ultima classificazione del cedimento per la disciplina del giorno. Se `type == 'muscular'` e `confidence >= 0.6`: verifica che il main set non superi la soglia neuromuscolare, citando il belief `endurance_failure_type`.

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

## Costruzione professionale del main set (OBBLIGATORIO)

### Regola anti-fotocopia
**MAI committare una sessione con main set identico all'ultima sessione dello stesso `session_type`** (verifica con `get_upcoming_plan`/storico). Ad ogni occorrenza: o VARI la struttura (variante diversa dalla libreria sotto) o PROGREDISCI un parametro esplicito (reps, durata rep, densità recuperi, passo target) — e dichiari nel razionale COSA progredisce rispetto alla volta scorsa. Tre sessioni identiche in tre settimane = zero sovraccarico progressivo = stimolo sprecato.

### Nuoto — set professionali
- **Send-off obbligatori derivati dal CSS**, mai riposi fissi generici: "4×200 partenza 3:20" insegna la gestione del passo, "R20"" no. Target PER RIPETUTA numerico (es. Z2 = CSS+5-8s/100m → "2:50-2:55 sul 200").
- Progressioni aerobiche tipo (ruota tra): `4×200` → `3×300` → `2×400+200` → `400+300+200+100 descending`.
- Tecnica: ruota TUTTI i drill della libreria (mai gli stessi 2 di fila), progredisci il rapporto drill:nuotata integrale nelle settimane (es. 60:40 → 40:60), dai un **target stroke count NUMERICO** (baseline dall'ultima sessione, es. "17→16 bracciate/25m"), non "riducilo".
- Open water: **nella finestra 8 settimane pre-gara A estiva, 1 sessione OW a settimana** (CLAUDE.md §3): sighting ogni 6-8 bracciate, partenze/boe simulate, nuoto in acqua mossa. Se OW impossibile, simula in vasca (sighting drill, partenze dal bordo).

### Bici — qualità per il cross
- **Fase specific: la variabilità è obbligatoria** — le note del mesociclo la prescrivono ("sforzi variabili e ripetuti, non solo blocchi lineari"). Almeno 1 sessione di qualità su 2 usa formati variabili: `30/30` o `40/20` (Z4-Z5/Z1), over-under (2' sotto soglia + 1' sopra), strappi `8-10×1'` con recupero incompleto, sali-scendi simulati.
- **Muscular endurance** (debolezza #1 dell'atleta): big-gear intervals 50-55rpm in Z2-Z3 (`3-5×5'`) — almeno 1×/settimana dentro una sessione bici, progressione su durata rep.
- Warm-up delle sessioni di qualità CON attivazione: progressivo + `2-3×30"` spin-up/allunghi prima del main set.

### Corsa — con vincolo fascite
- Gli allunghi PROGREDISCONO (n° reps, poi durata 20"→30", poi pendenza) — non restano `5×20"` per tre settimane.
- Quando la fascite regge (asintomatica, cap km rispettato): introduci variabilità cross a basso impatto (saliscendi continui Z2-Z3 a sensazione, cambi di ritmo brevi in salita) prima di ripetute classiche su piano.

### Forza (sport=strength)
- **1 sessione/settimana** di forza/core (30-40'): profilo "primo cedimento muscolare" — è il gap n°1. Bodyweight/elastici: affondi, split squat, calf raise eccentrici (protezione fascite), core anti-rotazione, scapolari (protezione spalla). Committala come `sport=strength` con steps.

### Aritmetica (ripetuto perché è il difetto storico)
Prima di scrivere la prosa: somma gli step. Durata dichiarata = somma step. Distanza dichiarata = somma distance_m. Il guardrail rifiuta il commit se non torna — ma la PROSA deve essere coerente anche dove il guardrail non vede (etichette "MAIN (1400m)" con item che sommano 1100m = inaccettabile).

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
- `structured`: **OBBLIGATORIO**, formato canonico `{"steps": [{name, duration_s, zone, reps?, distance_m?, target?, notes?}]}`
  - `duration_s` è PER RIPETIZIONE, **send-off/riposo INCLUSO** (nuoto: 4×200m partenza 3:20 → `reps:4, duration_s:200, distance_m:200`)
  - Almeno un step `warmup`, uno o più `main_set` (intervalli espliciti), un `cooldown`
  - `target` contiene il valore preciso da `physiology_zones` (es. `"2:50 sul 200 (CSS+5)"`, `"HR 151-162"`)
  - ⚠️ **Il commit viene RIFIUTATO se** somma(duration_s×reps) ≠ duration_s totale (±5%) — fai l'aritmetica PRIMA di scrivere la descrizione, e la prosa DEVE citare gli stessi numeri degli step (distanza totale = somma dei distance_m, mai "~2.3km" se gli step sommano 2000m)
- `target_tss`: **OMETTILO** — viene calcolato automaticamente dagli step (h × IF² × 100 per zona) e salvato in `structured.computed.tss`. Se lo fornisci e devia >25% dal calcolato, il commit viene rifiutato.

Esempio JSONB canonical (nuoto aerobico 45' = 2700s, somma step 2700 ✓):
```json
{
  "structured": {
    "steps": [
      {"name": "warmup",   "duration_s": 480, "zone": "Z1", "distance_m": 400, "notes": "200 sciolto + 4×50 progressivi part. 1:10"},
      {"name": "main_set", "reps": 4, "duration_s": 200, "zone": "Z2", "distance_m": 200, "target": "2:50-2:55 sul 200 (CSS+5/8), partenza 3:20"},
      {"name": "main_set", "reps": 3, "duration_s": 260, "zone": "Z2", "distance_m": 250, "target": "pull, 1:28/100m, partenza 4:20"},
      {"name": "cooldown", "duration_s": 640, "zone": "Z1", "distance_m": 400, "notes": "sciolto misto"}
    ]
  }
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
- Mai leggere vincoli medici da CLAUDE.md statico — usa `get_weekly_context.active_constraints` (D-16).
- Mai prescrivere "X min Z2" come unica riga — ogni sessione ha warmup/main set/cooldown espliciti (D-03).
