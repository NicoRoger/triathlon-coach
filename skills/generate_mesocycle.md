---
name: generate_mesocycle
description: Pianifica un blocco di 4 settimane (3 carico + 1 scarico) con sessioni dettagliate giorno per giorno. Usa per nuovo mesociclo o dopo gara importante.
---

# Generate Mesocycle

## Quando usare
- Inizio nuovo mesociclo (la domenica precedente)
- Dopo gara A: pianificare ripresa
- Cambio fase (es. base → build)

## Input richiesto
1. Fase target (`base`, `build`, `specific`, `peak`, `taper`, `recovery`)
2. Gara A più vicina e settimane mancanti
3. Stato attuale: CTL, settimane di consistency, infortuni recenti
4. Vincoli atleta: ore disponibili per settimana, vincoli (lavoro, viaggi)

## Procedura

### Step 0 — GATE FISIOLOGICO (obbligatorio)
Chiama `get_physiology_zones(discipline)` per ogni disciplina coinvolta nel mesociclo (swim, bike, run).
- Se zones è vuoto o `age_days > 42`: segnala obsolescenza e proponi test prima di pianificare.
- Tutti i target numerici del mesociclo DEVONO derivare da questi valori (ftp_w, threshold_pace_s_per_km, css_pace_s_per_100m).

**NON procedere con la pianificazione finché non hai ricevuto i response di `get_physiology_zones`.**

1. Leggi `CLAUDE.md` §Profilo, §Stato corrente
2. Leggi `docs/elite_training_reference.md` per volume/HR/struttura target elite
3. Leggi `docs/training_journal.md` ultime 4-6 settimane
4. Leggi `docs/athlete_beliefs.md` per beliefs strutturali + bias correction su predizioni
5. Leggi `docs/coaching_observations.md` per pattern prescrittivi attivi
6. Leggi `get_recent_metrics(28)` per CTL trend
7. (già fatto in Step 0) physiology_zones per zone correnti
8. **Multi-race awareness + vincoli medici + progressione**: chiama `get_weekly_context` e leggi:
   - `upcoming_races` — pianifica picchi per TUTTE le gare A/B della stagione, non solo la prossima
   - `active_constraints` (solo resolved_at IS NULL): **QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md**. Non prescrivere sessioni in contrasto con nessun vincolo attivo.
   - `current_progression_step`: passo corrente della progressione qualità.
     - **Regola avanzamento (D-28):** avanza al passo successivo SOLO se RPE medio delle ultime 3 sessioni di quella tipologia <= 7.5; altrimenti CONSOLIDA il passo corrente.
     - **Fallback null:** se `current_progression_step` è null (nessun mesociclo attivo), usa progressione conservativa (volume < media storica).
9. Calcola CTL target per ogni settimana:
   - Carico: +3-7 TSS/d/settimana sopra CTL corrente
   - Scarico: -30/-40% volume, intensità preservata in micro-dosi
10. Distribuisci sessioni con regola 80/20:
   - 80% Z1-Z2 (volume)
   - 20% Z4-Z5 (qualità)
   - Z3 minimizzato
11. Inserisci 1 test schedulato a fine settimana 3 o 4 se non c'è da almeno 6 settimane

## Output template
```
Mesociclo {n}: {phase} — settimane {start_date} -> {end_date}

CTL target: {ctl_start} -> {ctl_end}
Distribuzione: {hours/wk medie} ore/sett

SETTIMANA 1 (carico, target TSS 480)
Lun: Z2 corsa 60min
Mar: Soglia bici 75min — 4×8min Z4
Mer: Tecnica nuoto 45min
Gio: Z2 bici lungo 120min
Ven: Off
Sab: Brick (60min Z3 bici + 20min Z2 corsa)
Dom: Lungo corsa 90min

SETTIMANA 2 (carico, target TSS 510)
[...]

SETTIMANA 3 (carico, target TSS 540)
[...]

SETTIMANA 4 (scarico, target TSS 320)
Lun: Off
Mar: Z2 30min
Mer: Tecnica nuoto 30min
Gio: 6×3min Z4 (richiamo intensita)
Ven: Off
Sab: TEST CSS 400+200
Dom: Lungo Z2 60min

NOTE:
- Test settimana 4 → aggiorna `physiology_zones`
- Sessioni serali se {vincoli lavoro}
- Riconferma alla domenica della settimana 2
```

Ogni riga sessione (es. "Z2 corsa 60min") sara espansa con warmup/main set/cooldown nel `structured` JSONB via `commit_plan_change` — la sintesi nel template e solo per l'overview settimanale.

## Commit in DB
Dopo approvazione dell'atleta:
1. Chiama `commit_mesocycle` con `name`, `phase`, `start_date`, `end_date` (e `target_race_id` se applicabile) e **`progression_plan`** JSONB (D-27) nel formato:
   ```json
   {
     "run_threshold": {"week1": "4x6min", "week2": "5x6min", "week3": "6x6min"},
     "bike_threshold": {"week1": "3x8min", "week2": "4x8min", "week3": "5x8min"}
   }
   ```
   Un'entry per ogni tipo di sessione di qualità con il volume previsto per settimana.
   - Restituisce `mesocycle_id`
2. Chiama `commit_plan_change` per ogni sessione, passando il `mesocycle_id` ricevuto. Ogni sessione **DEVE** includere il campo `structured` come flat steps list (D-09):
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
   Almeno un step `warmup`, uno o piu `main_set` (con intervalli), un `cooldown`. Il campo `target_value` deve contenere il valore numerico preciso da `physiology_zones`.
3. Conferma: "Mesociclo {name} salvato — {n} sessioni pianificate fino al {end_date}"

## Output strutturato
Genera anche `plans/{start_date}_{phase}.yaml` per commit in repo. Format:
```yaml
mesocycle:
  name: "..."
  phase: build
  start_date: 2025-XX-XX
  end_date: 2025-XX-XX
  weeks:
    - week: 1
      days:
        - date: 2025-XX-XX
          sport: run
          session_type: Z2_endurance
          duration_s: 3600
          target_tss: 50
          target_zones: {z1: 0.2, z2: 0.8}
          description: "..."
```

## Vincoli
- Mai > 2 settimane consecutive con +6 TSS/d (soglia overreach)
- Sempre 1 settimana scarico ogni 3-4 di carico
- Test fitness max 1 per disciplina per mesociclo
- Domenica: review della settimana, lunedì: nuovo carico

## Citation obbligatoria (Fase 2.4 Cognitive MVP)

Ogni decisione strutturale (volume, intensità, distribuzione, taper) DEVE citare almeno 1 principio scientifico:

`[source: <autore> <anno>]`

Principi attesi (consulta dalla tua training knowledge):
- **Polarizzato 80/20** → Seiler 2010, 2019
- **ACWR injury risk** → Gabbett 2016
- **Block periodization** → Issurin 2008
- **Tapering response** → Mujika & Padilla 2003
- **Tendinopatia isometric** → Cook & Purdam 2009 (rilevante per fascite plantare)
- **Heat acclimatization** → Périard 2015
- **Cross-discipline interference** → Häkkinen 2003

Quando applichi una belief dell'atleta da `athlete_beliefs.md`:

`[athlete-belief: <descrizione> (n=X, conf=Y)]`

Le citazioni rendono auditabile la pianificazione e si auto-loggano in `training_journal.md`.

## Output prediction (Fase 2.1)

**NOTA: la registrazione delle predizioni CTL avviene SOLO quando il mesociclo viene generato
via CLI Python (es. `python -m coach.coaching.generate_mesocycle`). Non è eseguibile da Claude.ai
via MCP — non esiste un tool `record_prediction` nel server MCP.**

Quando operi come Claude.ai via MCP: **logga la predizione come nota testuale in `training_journal.md`**
usando il formato seguente (includi nel tuo output scritto, non come tool call):

```
[PREDIZIONE CTL] Settimana X: CTL target ~42.5 (confidence 0.70)
Rationale: Settimana di build: +5 TSS/d -> CTL +3
```

Quando il mesociclo viene generato via CLI Python, il modulo registra la predizione in DB:

```python
# CLI-only — NON eseguire come tool call via MCP
from coach.coaching.outcome_verification import record_prediction
# Per ogni settimana del mesociclo:
record_prediction(
    prediction_type="ctl_weekly",
    target_date="2026-XX-XX",  # ultimo giorno della settimana
    predicted_value=42.5,
    confidence=0.7,
    model_version="mesocycle_planner_v1",
    reasoning_summary="Settimana di build: +5 TSS/d -> CTL +3",
    source="generate_mesocycle",
)
```

Questo permette al sistema di calibrare automaticamente le predizioni future con `outcome_verification` ogni domenica.

## Cosa NON fare
- Non committare il YAML senza approvazione dell'atleta
- Non ignorare consistency: se atleta è sotto 6h/settimana di media, propone meso più conservativo
- Non inventare riferimenti scientifici (autori inesistenti, anni fuori range). Se incerto, scrivi `[source: principio generale endurance]`.
- Mai leggere vincoli medici da CLAUDE.md statico — usa `get_weekly_context.active_constraints` (D-16).
- Mai committare un mesociclo senza `progression_plan` e senza `structured` JSONB per ogni sessione (D-27/D-09).
