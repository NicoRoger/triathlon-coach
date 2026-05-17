---
name: ows_strategy
description: Strategia open-water swim per allenamento e gara. Usa quando l'atleta chiede "preparami una sessione OWS", in race week per gare con frazione swim in acque libere, o quando affronta condizioni specifiche (corrente, mareggiata, lago freddo).
---

# Open-Water Swim Strategy

## Quando usare

- L'atleta digita "preparami sessione OWS", "ho un OWS sabato"
- `race_week_protocol.md` race con swim in acque libere
- L'atleta segnala condizioni difficili previste (vento, mareggiata, temperatura)
- `weekly_review.md` sta strutturando la transizione da piscina → OWS (~6 settimane pre-stagione)

## Differenze chiave piscina → OWS (vincoli)

| Aspetto | Piscina | Open-water |
|---------|---------|-----------|
| Pace effettivo | CSS misurato | CSS +5-10% [source: Friel triathlon training bible] |
| Sighting | Non necessario | 1 sighting ogni 6-10 bracciate |
| Drafting | Non utilizzabile | -3-7% energia con buon drafting [source: Chatard 2003] |
| Temperatura | 26-28°C controllata | Variabile (può essere 14-22°C anche lago) |
| Distanza percepita | Lunghezze contate | Boe come riferimenti, drift laterale |
| Visibilità | Massima | Limitata, possibile turbolenza |

## Procedura

1. Leggi `physiology_zones` swim (CSS, lthr_swim se presente)
2. Leggi `get_recent_metrics(7)` per readiness
3. Leggi `get_activity_history(sport='swim', days=30)` per check storico volumi OWS
4. Verifica `CLAUDE.md` §infortuni — spalla destra → niente sprint anche in OWS
5. Determina scopo della sessione (vedi sotto)
6. Costruisci con template + adatta a condizioni (temperatura, location)

## Sessioni tipo per scopo

### Adattamento OWS (transizione da piscina, prime 2-3 sessioni stagione)
```
🏊 OWS adattamento — 40-50min

Warm-up: 200m in piscina pre-ingresso (mobility spalla, attivazione)
Main:
  - 200m breaststroke easy (acclimatazione temperatura, controllo respirazione)
  - 4×100m freestyle Z1-Z2 con sighting ogni 6 bracciate
  - 200m focus tecnica (lunghezza bracciata, rolling)
  - 3×200m a CSS+8% (pace OWS) con sighting ogni 8 bracciate
  - 200m cool-down

Target TSS: ~35
Razionale: prima sessione OWS della stagione. Focus su acclimatazione mentale,
sighting frequente per costruire automatismo, controllo della respirazione
nei primi 200m (panic-zone tipica).

Successo: nessun panic attack iniziale, sighting fluido (no riduzione cadenza),
HR controllato (non sopra Z2-Z3).
```

### Specific race-pace (3-6 settimane pre-gara)
```
🏊 OWS race-pace — 60min

Warm-up: 200m easy + 100m attivazione + 50m sprint sciolti
Main race-simulation:
  - 800m @ race-pace cross sprint (CSS+5%, sighting ogni 8 bracciate)
  - 60s riposo galleggiamento
  - 400m @ race-pace (target intensità più alta, simula final push)
  - 100m easy
  - 200m sprint cross (target finish 750m sprint = ultimi 200m gara)
Cool-down: 200m easy

Target TSS: ~50
Razionale: prepara il sistema bioenergetico alla durata e intensità specifica
gara cross sprint (750m). Lavoro sui transizioni ritmo (steady → finale).
Sighting integrato come automatismo.

Successo: pace race target rispettato in 800m e 400m, sighting non degrada pace,
ultimi 200m sprint con HR/RPE 9 sostenibile.
```

### Mass start simulation (pre-gara A/B)
```
🏊 OWS mass-start sim — 45-60min

Warm-up: 400m mix easy + tecnica
Main:
  - 5×50m sprint da fermo (simula partenza) con 30s recovery, includi contatto fisico controllato se possibile
  - 200m easy "esci dal gruppo"
  - 4×200m a race-pace con sighting ogni 6 bracciate (più frequente per evitare collisioni)
  - 200m breve "draft" su nuotatore davanti (se sessione con compagni)
Cool-down: 200m easy

Target TSS: ~45
Razionale: simulazione adrenalina + caos partenza. Tecnica sighting più
aggressiva in gruppo. Drafting controllato per testarne il vantaggio.

Successo: gestione contatto senza panic, sighting frequente, gestione respirazione
sotto stress (no apnea forzata).
```

## Condizioni ambientali — protocolli

### Acqua fredda (< 18°C)
- Wetsuit obbligatorio (regola FITri: <22°C wetsuit consentito)
- Riscaldamento più lungo: 15min in acqua pre-sessione
- Primi 200-300m con respirazione controllata (gasping reflex)
- Idratazione termica pre-sessione (bevanda calda 30min prima)

### Corrente / mareggiata
- Sighting più frequente (4-6 bracciate)
- Linee di gara: nuotare a "compensazione" rispetto alla corrente (mira più a monte)
- Skill drill: nuotare per 50m lungo riva con corrente parallela per testare drift

### Visibilità ridotta
- Sighting frontale + laterale per riferimenti costa
- Lap conscious in alternativa alle boe (conta bracciate per stimare distanza)

## Vincoli specifici atleta

- **Spalla destra (borsite)**: max Z2 in OWS, niente sprint > 50m
- **Storia elite**: ex-azzurro cross, atleta conosce mass-start. Skill OWS già consolidate.
- **Lago di prossimità**: identifica il lago/spot di allenamento OWS più vicino — fattore logistico

## Citation obbligatoria (Fase 2.4)

Cita principi con `[source: Chatard 2003]` (drafting), `[source: Bonacci 2011]` (transitions),
`[source: Friel triathlon training bible]` (OWS pace conversion). Quando applichi belief atleta:
`[athlete-belief: ...]`.

## Cosa NON fare

- Non programmare OWS in solitaria senza safety boat / compagno
- Non testare wetsuit nuovo in race-pace sim (test prima a Z1-Z2)
- Non sostituire >50% volume swim totale settimana con OWS (perde il volume tecnica piscina)
- Non ignorare la temperatura: hypothermia threshold 16°C anche con wetsuit per sessioni >45min
