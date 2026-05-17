---
name: brick_design
description: Progetta sessioni brick (bike→run o swim→bike) basate su principi scientifici e fase del mesociclo. Usa quando l'atleta chiede "dammi un brick" o quando weekly_review sta pianificando il weekend.
---

# Brick Design

## Quando usare

- L'atleta chiede "preparami un brick" o "che brick faccio sabato?"
- `weekly_review.md` deve pianificare il weekend e c'è una sessione brick programmata
- `generate_mesocycle.md` sta strutturando un mesociclo specific/peak (i brick salgono in volume e specificità)

## Principi scientifici di base

Le sessioni brick simulano la transizione gara → impongono un carico fisiologico unico per:
1. **Adattamento neuromuscolare** alla transizione: i muscoli posteriori (hamstring, glutei) lavorano diversamente in bici (estensione anca prevalente) vs corsa (flessione/estensione alternata). [source: Bonacci 2011 — neuromuscular cross-over]
2. **Glicogeno depletion e gestione fuel**: l'allenamento brick allena la capacità di mantenere pace running con riserve già parzialmente consumate. [source: Burke 2017 — fuel periodization]
3. **Lattato shuttle**: la bici elevata lascia residui di lattato che la corsa deve gestire — adattamento metabolico race-specific. [source: Brooks 2009 — lactate shuttle]
4. **Cognitive readiness**: gestione del "leg lock" iniziale (primi 1-2 km a passo strano) — abituazione protocollare. [source: Millet 2011 — perceptual response]

## Procedura

1. Leggi `get_planned_session(target_date)` e verifica che sia brick
2. Leggi `physiology_zones` per bike + run
3. Leggi `get_recent_metrics(7)` per readiness corrente
4. Leggi `CLAUDE.md` §infortuni — se fascite attiva, modifica run portion (vedi sotto)
5. Determina **scopo** del brick dalla fase del mesociclo corrente:
   - **base** → adattamento, volume basso, intensità Z2
   - **build** → resistenza muscolare, intensità Z2/Z3 alternata
   - **specific** → race-pace simulation, brick lungo con run a passo gara
   - **peak** → activation brick (corto + intenso)
   - **taper** → mini-brick di richiamo (10+5 min al ritmo)
6. Costruisci con template (vedi sotto) e adatta a vincoli atleta

## Template per fase

### Base (settimana 1-2 ramp-up)
```
🚴+🏃 Brick adattamento — 75min totali

Bike: 60min @ Z2 (HR 130-150 per te), terreno mosso ma non collinare
Transizione: T1 simulata <2min — togli scarpe, butta calze pronte, scarpe corsa
Run: 15min @ Z2 (HR <155), pace conversazionale, focus cadenza alta (>85spm)

Target TSS: ~80
Razionale: primo adattamento neuromuscolare bike→run [source: Bonacci 2011].
Volume basso, intensità contenuta. Focus su cadenza corsa per ridurre dominanza
muscolare quadricipiti (tipica dei principianti brick).

Successo: corsa fluida dal min 4-5 in poi, HR drift <10bpm, no fastidio
fascite. Cadence ≥85spm.
```

### Build (settimana 3-5)
```
🚴+🏃 Brick build endurance — 105min totali

Bike: 75min con struttura:
  - 10min warm-up Z1
  - 4×8min @ Z3 (sweet spot, HR 155-165), recupero 4min Z2
  - 10min cool-down Z2
Transizione: T1 simulata <90s
Run: 30min:
  - 5min easy (Z1, "trovata la pace dopo bici")
  - 20min @ Z2-Z3 progressivo (HR target 150-160, no sopra 165)
  - 5min easy cool-down

Target TSS: ~125
Razionale: stimolo sweet-spot bici + corsa Z2-Z3 sviluppa resistenza muscolare
e tolleranza lattato cross-discipline [source: Seiler 2010 polarized].

Successo: ultimi 5min run @ pace target con HR stabile (no cardiac drift >5bpm
nel blocco finale). RPE corsa ≤7.
```

### Specific (settimana 6-8 pre-gara A/B)
```
🚴+🏃 Brick race-specific — 90min totali (sprint cross simulation)

Bike: 50min con struttura:
  - 10min warm-up Z1-Z2
  - 30min @ race-pace cross (target potenza/HR — usa zone bike race-pace)
  - 10min cool-down Z2
Transizione: T1 reale <60s (cambio scarpe + bib se trail)
Run: 30min @ race-pace cross (target pace dalla race_prediction)

Target TSS: ~110
Razionale: simulazione race-pace completa, allena lattato shuttle e gestione
fuel race-day [source: Brooks 2009]. Calibra la nutrition strategy.

Successo: pace race target rispettato in entrambi i blocchi, RPE 7-8 (sostenibile
in gara), no problemi GI. Splits run consistenti km 1-2 ≈ km 4-5.
```

## Vincoli specifici

- **Fascite plantare**: max +10% volume corsa rispetto a settimana scorsa. Se brick supera quota, suddividi (es. 20+15 anziché 25min unici).
- **Spalla destra**: i brick swim-bike sono OFF per ora (riprendere quando borsite risolta)
- **Cross/MTB**: brick su terreno tecnico aumenta TSS effettivo del 15-20% — sottrai da target
- **Caldo (>28°C)**: riduci target potenza/pace del 5-8% e idrata 700-800ml/h [source: Périard 2015 heat acclim]

## Citation obbligatoria (Fase 2.4)

Ogni brick proposto DEVE citare almeno 1 principio scientifico con `[source: ...]`. Se applichi una athlete belief: `[athlete-belief: ...]`.

## Cosa NON fare

- Non proporre brick con run > 50% durata bici nelle prime 4-6 settimane (cardiovascular asymmetry)
- Non testare nuova nutrition durante un brick race-specific
- Non programmare 2 brick consecutivi (richiede 48h+ recupero in fase build/specific)
- Non ignorare la transizione T1: anche solo simulata, è parte dell'adattamento
