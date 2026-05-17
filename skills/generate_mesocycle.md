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
1. Leggi `CLAUDE.md` §Profilo, §Stato corrente
2. Leggi `docs/elite_training_reference.md` per volume/HR/struttura target elite
3. Leggi `docs/training_journal.md` ultime 4-6 settimane
4. Leggi `docs/athlete_beliefs.md` per beliefs strutturali + bias correction su predizioni
5. Leggi `docs/coaching_observations.md` per pattern prescrittivi attivi
6. Leggi `get_recent_metrics(28)` per CTL trend
7. Leggi `physiology_zones` per zone correnti
8. **Multi-race awareness**: chiama `get_weekly_context` e leggi `upcoming_races` — pianifica picchi per TUTTE le gare A/B della stagione, non solo la prossima
9. Calcola CTL target per ogni settimana:
   - Carico: +3-7 TSS/d/settimana sopra CTL corrente
   - Scarico: -30/-40% volume, intensità preservata in micro-dosi
6. Distribuisci sessioni con regola 80/20:
   - 80% Z1-Z2 (volume)
   - 20% Z4-Z5 (qualità)
   - Z3 minimizzato
8. Inserisci 1 test schedulato a fine settimana 3 o 4 se non c'è da almeno 6 settimane

## Output template
```
🎯 Mesociclo {n}: {phase} — settimane {start_date} → {end_date}

CTL target: {ctl_start} → {ctl_end}
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
Gio: 6×3min Z4 (richiamo intensità)
Ven: Off
Sab: TEST CSS 400+200
Dom: Lungo Z2 60min

NOTE:
- Test settimana 4 → aggiorna `physiology_zones`
- Sessioni serali se {vincoli lavoro}
- Riconferma alla domenica della settimana 2
```

## Commit in DB
Dopo approvazione dell'atleta:
1. Chiama `commit_mesocycle` con `name`, `phase`, `start_date`, `end_date` (e `target_race_id` se applicabile)
   - Restituisce `mesocycle_id`
2. Chiama `commit_plan_change` per ogni sessione, passando il `mesocycle_id` ricevuto
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

Dopo aver definito CTL target per ogni settimana, registra una prediction in DB via il modulo Python:

```python
from coach.coaching.outcome_verification import record_prediction
# Per ogni settimana del mesociclo:
record_prediction(
    prediction_type="ctl_weekly",
    target_date="2026-XX-XX",  # ultimo giorno della settimana
    predicted_value=42.5,
    confidence=0.7,
    model_version="mesocycle_planner_v1",
    reasoning_summary="Settimana di build: +5 TSS/d → CTL +3",
    source="generate_mesocycle",
)
```

Questo permette al sistema di calibrare automaticamente le predizioni future con `outcome_verification` ogni domenica.

## Cosa NON fare
- Non committare il YAML senza approvazione dell'atleta
- Non ignorare consistency: se atleta è sotto 6h/settimana di media, propone meso più conservativo
- Non inventare riferimenti scientifici (autori inesistenti, anni fuori range). Se incerto, scrivi `[source: principio generale endurance]`.
