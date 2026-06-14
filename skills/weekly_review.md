---
name: weekly_review
description: Protocollo per la review settimanale di domenica. Analizza la settimana appena conclusa e propone la settimana successiva. Da invocare ogni domenica sera quando l'atleta digita "fai la weekly review" o equivalente.
---

# Weekly Review

## Quando usare

Trigger primario: ogni domenica sera, quando l'atleta digita "fai la weekly review", "rivedi la settimana", "pianifica la prossima settimana".

Trigger secondari (replanning mid-week): "ho saltato la sessione di ieri, ripianifica", "domani non posso allenarmi, sposta", "sono in trasferta da mercoledì".

## Procedura — 7 fasi

### Fase 0 — Sync dati attuali

Prima di analizzare la settimana, garantisci che i dati siano aggiornati.

1. Chiama `get_weekly_context(days=7)` (è anche la Fase 1) e ispeziona `health`:
   il componente `garmin_sync` ha `last_success_at`.
2. Se l'ultimo sync Garmin è > 1 ora fa, chiama `force_garmin_sync` e poi
   richiama `get_weekly_context` una volta sola quando il sync è visibile.
3. Se `force_garmin_sync` restituisce `status: completed`, attendi che il sync sia visibile e procedi.
4. Se restituisce `skipped`, procedi direttamente (sync già recente).
5. Se restituisce `timeout`, avvisa l'utente: "Sync forzato ma non ancora visibile, procedo con i dati che ho ma considera che potrebbe mancare l'ultima attività. Vuoi aspettare?"

> Nota: NON ri-chiamare `get_weekly_context` ad ogni fase. Caricalo una volta
> qui/in Fase 1 e lavora su quell'oggetto per tutta la review.

### Fase 1 — Raccolta dati

**Usa UNA sola chiamata aggregata: `get_weekly_context(days=7)`.**

Questo singolo tool ritorna già tutto il necessario in un unico oggetto coerente:
`health`, `metrics` (daily_metrics 14gg), `wellness`, `activities`,
`planned_sessions`, `subjective_log`, `session_analyses`, `plan_modulations`,
`upcoming_races`. **Non** chiamare anche i tool granulari
(`get_activity_history`, `get_recent_metrics`, `query_subjective_log`,
`get_planned_session` giorno-per-giorno): caricherebbero gli stessi dati una
seconda volta in forma diversa, raddoppiando il contesto e creando incongruenze
(è la causa principale del "mi tocca correggerlo"). Tratta l'output di
`get_weekly_context` come la **singola fonte di verità** della Fase 1.

Solo se serve uno specifico approfondimento non incluso:
- `get_technique_history(sport='all', days=7)` — video tecnici (non in get_weekly_context)
- `get_session_review_context(activity_id)` — solo per UNA sessione anomala da sezionare

Leggi inoltre (file di memoria, non duplicano i dati DB):
- `CLAUDE.md` §3 (stato corrente) e §8.5 (calendario gare)
- `docs/training_journal.md` (ultime decisioni)
- `docs/injury_log.md` (stato infortuni in corso)
- `docs/coaching_observations.md` (pattern longitudinali con prescription/confidence — leggi SEMPRE)
- `docs/athlete_beliefs.md` (calibrazione predizioni + beliefs strutturali — leggi SEMPRE)
- `docs/progress_tracker.md` (compliance e trend)
- `docs/elite_training_reference.md` (volume/HR/struttura target dal periodo elite — per calibrare i volumi proposti)

**Multi-race awareness**: `get_weekly_context` ritorna `upcoming_races` (tutte le gare future). Considera il calendario completo, non solo la prossima gara. Pianifica picchi multipli quando ci sono gare A successive.

**Confronto pianificato vs eseguito**: incrocia `planned_sessions` e `activities`
(entrambi già in `get_weekly_context`) per data+sport. Una sessione pianificata
con `completed_activity_id` valorizzato (o un'attività nella stessa data/sport) =
eseguita; altrimenti = saltata. Non servono chiamate aggiuntive.

### Fase 2 — Analisi della settimana conclusa e Diagnosi (via AI)

Esegui lo script Python per generare l'analisi narrativa approfondita della settimana tramite Claude AI:
`python -m coach.coaching.weekly_analysis`

Questo script consoliderà le metriche, i debrief, le risposte proattive e le analisi post-sessione in un'analisi di 15-20 righe.
Leggi attentamente l'output e usalo come base per la tua comunicazione con l'atleta. Evidenzia cosa ha funzionato bene e il "costo" fisiologico pagato. Non essere compiacente.

### Fase 3 — Lezione della settimana (via AI)

Genera una pillola formativa o "lezione della settimana" eseguendo lo script:
`python -c "from coach.coaching.weekly_analysis import generate_weekly_lesson; print(generate_weekly_lesson())"`

Includila nel tuo messaggio all'atleta per aumentare la consapevolezza su nutrizione, recupero, o gestione fatica.

### Fase 4 — Proposta settimana successiva

Struttura ibrida (proposta C):

**Schema settimanale (sport per giorno)**: solido, sai già che lunedì faremo X sport, mercoledì Y, ecc.

**Parametri precisi (durata, intensità, target)**: definiti per i primi 2-3 giorni con dettaglio, indicativi per i giorni successivi (verranno raffinati 1-2 giorni prima sulla base dei dati che arriveranno).

**Esempio output**:
SETTIMANA DEL 11-17 MAGGIO 2026
Schema settimana:
Lun: Nuoto tecnica (giorno fisso)
Mar: Z2 corsa (volume aerobico)
Mer: Recovery o off
Gio: Soglia bici (qualità della settimana)
Ven: Off
Sab: Lungo (brick o lungo bici)
Dom: Z2 corsa lunga
Dettaglio prossimi 3 giorni:
LUNEDÌ 11/05 — Nuoto tecnica 60 min

Warm-up: 400m mix
Main: 6×100m drill bracciata + 4×50m gambata + 4×50m sprint sciolti
Cool-down: 200m easy
Razionale fisiologico: focus tecnica, no carico CV
Razionale strategico: prima sessione settimana, riprendiamo dopo recovery weekend
Successo: gomito alto in tutto il drill, niente dolore spalla. Se RPE spalla > 5 → stop.

MARTEDÌ 12/05 — Z2 corsa 50 min

10 min warm-up Z1
35 min Z2 (HR 145-155 per te)
5 min cool-down
TSS target ~45
Razionale fisiologico: volume aerobico polarizzato (Seiler)
Razionale strategico: aerobic base, low impact su fascite (terreno pianeggiante)
Successo: HR sotto 160 per tutto il blocco Z2. Pace si assesta a sentimento, non spingere.

MERCOLEDÌ 13/05 — Recovery o off

Decisione ultima ora basata su HRV mattutina + sensazioni
Se HRV nella norma e gambe ok: 30 min Z1 facile
Se HRV bassa o dolori: off completo

Prossimi giorni (gio-dom): definirò i parametri precisi mercoledì sera
sulla base dei tuoi dati reali.
Volume settimanale target: ~6h
TSS settimanale target: ~280
ACWR proiettato: 1.2 (zona allenante ottimale)

### Fase 4.5 — Citation obbligatoria (Fase 2.4 Cognitive MVP)

**Ogni proposta strutturale DEVE citare almeno 1 principio scientifico** con tag inline. Formato:

`[source: <autore> <anno>]` — esempio: `[source: Seiler 2010]`, `[source: Gabbett 2016]`

Principi attesi (consulta dalla tua training knowledge, non da file curati):
- **Polarizzato 80/20** → Seiler 2010, 2019
- **ACWR injury risk** → Gabbett 2016
- **Tendinopatia isometric** → Cook & Purdam 2009
- **Block periodization** → Issurin 2008
- **Tapering response** → Mujika & Padilla 2003
- **Heat acclimatization** → Périard 2015
- **Cross-discipline interference** → Häkkinen 2003

Le citazioni rendono auditabile la proposta. Non inventare riferimenti (anno > anno corrente, autore non esistente). Se non sei sicuro, scrivi `[source: principio generale endurance training]`.

**Esempio applicato:**
> "Mantengo Z2 al 75% del volume settimanale [source: Seiler 2010] e ACWR a 1.2 [source: Gabbett 2016] per limitare rischio infortunio dato l'aumento progressivo del CTL."

Le citazioni vengono salvate automaticamente in `docs/training_journal.md` come parte del log decisionale.

### Fase 4.6 — Beliefs awareness

Quando proponi, **cita anche le beliefs dell'atleta** che hai usato (da `docs/athlete_beliefs.md` o pattern_extraction). Formato:

`[athlete-belief: <descrizione> (n=X, conf=Y)]`

Esempio:
> "Evito sessione qualità sabato [athlete-belief: HRV basso sabato n=12, conf 0.85] e propongo invece per venerdì."

Se `athlete_beliefs.md` è vuoto (sistema appena partito), nessun obbligo di citation belief — solo scientifica.

### Fase 5 — Conferma e commit ⚠️ STEP CRITICO

Presenta la proposta. Aspetta riscontro:

- "ok" / "va bene" / "approvato" → procedi al commit
- "modifica X" → ridiscussione, poi commit
- "no" / "rifaccio" → ripeti dalla Fase 4 con feedback

**Protocollo di commit obbligatorio dopo "ok":**

Appena ricevi conferma, **devi** eseguire questi 3 step nell'ordine, **senza chiedere ulteriori conferme intermedie**:

**Step 5.A — Commit DB (BLOCCANTE)**

Per ogni giorno della settimana (TUTTI i 7 giorni, anche quelli "TBD") chiama:

```
commit_plan_change(
    planned_date="2026-05-11",
    sport="swim",
    session_type="technique",
    duration_s=3600,
    target_zones={"z1": 0.8, "z2": 0.2},
    description="..."
)
```

Per i giorni con parametri ancora indefiniti, scrivi una sessione con `description="TBD — dettagli a metà settimana"` e `duration_s` placeholder. Verrà aggiornata via re-commit.

**Step 5.B — Verifica post-commit (BLOCCANTE)**

Subito dopo aver chiamato tutti i `commit_plan_change`, **chiama `get_upcoming_plan(days=7)`** per verificare che le sessioni siano effettivamente nel DB.

- Se ricevi N sessioni == numero di giorni committati → ✅ tutto OK, prosegui a 5.C
- Se ricevi 0 o meno del previsto → ❌ qualcosa non è andato: re-chiama `commit_plan_change` per i giorni mancanti, poi ri-verifica con `get_upcoming_plan`. Se persiste, segnala all'atleta: "⚠️ Commit DB fallito per [giorni]. Riprova manualmente o controlla il MCP server."

**Step 5.C — Conferma all'atleta**

Dopo verifica positiva, manda 1 messaggio di chiusura: `"✅ N sessioni committate nel DB per la settimana del [start]. Procedo con Google Calendar."`

Poi prosegui automaticamente a Fase 6 (Google Calendar export).

**Anti-pattern da evitare:**
- ❌ Chiamare commit_plan_change ma poi non verificare → la sessione potrebbe non essere stata salvata davvero (race condition MCP)
- ❌ Aspettare ulteriore conferma "vuoi che committi?" dopo che l'atleta ha già detto "ok" → genera workflow stallato. "ok" è la conferma finale.
- ❌ Committare solo i primi 3 giorni perché "i parametri sono indefiniti" → committa anche TBD con placeholder, l'atleta può sempre vedere lo schema completo nel calendar.

### Fase 6 — Esportazione su Google Calendar

Per ogni sessione committata in `planned_sessions`, crea l'evento corrispondente
nel Google Calendar di Nicolò. Calendario: "primary" (calendario principale).

Mapping sessione → evento:

- **title**: "🏊 [sport] — [session_type]" (emoji: 🏊 swim, 🚴 bike, 🏃 run, 🏊🚴🏃 brick, 💪 strength)
- **start**: `planned_date` alle 06:30 di default (l'utente si allena di mattina presto)
  - Se l'utente preferisce orario diverso, lo specifica nel debrief o lo dichiara
- **end**: start + `duration_s`
- **description**: testo completo della sessione (con razionale fisiologico, strategico, parametri di successo)
- **location**: vuota di default
- **reminders**: 1 reminder a -30min

Workflow:
1. Per ogni sessione appena committata, chiama `gcal:list_events` con time_min=start-1h, time_max=start+1h, q="[sport]"
2. Se esiste già un evento con titolo simile in quella finestra → chiama `gcal:update_event`
3. Altrimenti → chiama `gcal:create_event`
4. Dopo la creazione/update, ricevi il `calendar_event_id` e aggiorna la sessione in DB con `commit_plan_change` includendo il campo `calendar_event_id`

Se la chiamata gcal fallisce, NON bloccare il commit della sessione — la sessione
è comunque salvata in DB. Riporta il problema all'utente con messaggio chiaro.

## Vincoli di sicurezza

- **Spalla dx attiva** (env SHOULDER_ACTIVE=true): nessuna sessione nuoto a Z4+. Solo Z1-Z2 con focus tecnica.
- **Fascite sx attiva** (env PLANTAR_ACTIVE=true): incremento volume corsa max +10% rispetto a settimana scorsa. Mai 2 settimane consecutive di incremento.
- **Test fitness pianificati settimana 6-7**: la prima settimana di settimana 6 deve essere strutturata come carico moderato (per non arrivare ai test affaticati).
- **Rispetta polarized 80/20**: 80% Z1-Z2 (volume), 20% Z4-Z5 (qualità), Z3 minimizzato (Seiler 2010).

## Cosa NON fare

- Non scrivere su DB senza conferma esplicita. Se l'atleta dice "ok per la struttura ma vediamo le sessioni man mano", non chiamare commit_plan_change ancora.
- Non proporre carichi che superano +10% del volume settimanale precedente (regola fascite).
- Non ignorare i flag attivi della settimana scorsa nel pianificare.
- Non saltare la fase 1 (raccolta dati): ogni proposta deve essere fondata su dati reali, non su pattern teorici.

## Lezione del giorno (opzionale)

Quando le condizioni sono buone (settimana andata bene, niente flag), la weekly review è il posto giusto per inserire una lezione metodologica di 5-8 righe. Vedi CLAUDE.md §7.3 per la rotation di topic suggeriti. Esempio:

> 📚 Lezione del giorno
> Hai notato che lunedì hai chiuso il debrief con "gambe scariche dopo lungo di domenica"? È normale e si chiama supercompensazione: dopo uno stimolo intenso il corpo entra in fase catabolica per 24-48h, poi rimbalza con adattamento positivo. La sessione di lunedì doveva essere recovery proprio per permetterlo. Se avessi forzato Z3 lunedì avresti tagliato il rebound. Friel definisce "respect the recovery" come uno dei 7 principi cardine del Triathlete's Training Bible.

## Riferimenti scientifici per giustificare scelte

Cita sempre la fonte quando proponi qualcosa basato su letteratura. Vedi CLAUDE.md §4 per il riepilogo delle fonti core (Seiler, Coggan, Friel, Gabbett, Cook & Purdam).