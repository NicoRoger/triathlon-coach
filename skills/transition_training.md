---
name: transition_training
description: Allena le transizioni T1 (swim→bike) e T2 (bike→run) per minimizzare tempo perso in gara. Usa quando l'atleta chiede "voglio migliorare le transizioni", in race week per richiamo procedurale, o quando weekly_review pianifica una sessione tecnica gara-specifica.
---

# Transition Training

## Quando usare

- L'atleta digita "preparami una sessione transizioni" o "voglio lavorare su T1/T2"
- `race_week_protocol.md`: richiamo procedurale T-3 / T-2
- `weekly_review.md`: sessione tecnica race-week o pre-stagione
- Atleta ha registrato tempo transizione lento in gara passata (data da `docs/race_history.md`)

## Perché allenarle

In una gara cross sprint, T1 + T2 sommate possono pesare 1-3 minuti — quanto la differenza tra arrivare top-10 e top-30. [source: Cejuela 2013 — transition time impact in sprint triathlon]

Le transizioni richiedono:
1. **Memoria procedurale**: sequenza fissa di gesti senza pensare
2. **Skill specifici**: scarpe veloci, casco veloce, bike-handling out-of-saddle ai primi metri
3. **Gestione cognitiva sotto fatica**: dopo swim/bike il cervello è ipoperfuso → procedure semplici, automatiche
4. **Setup pre-gara**: posizione zaino in transizione zona, ordine elementi

## Procedura

1. Leggi `get_planned_session(date)` — verifica che ci sia spazio per transition drills
2. Leggi `docs/race_history.md` — controlla se l'atleta ha transition time documentati (se sì, target = -15%)
3. Verifica `physiology_zones` — la sessione transition ha carico CV basso, può inserirsi in giornata di recovery o tecnica
4. Costruisci sessione (vedi template) e logga `decision_audit` con tipo `session_proposal`

## Template — T1 simulation (swim→bike)

```
🏊→🚴 T1 transition drill — 45min

Setup zona transizione (in casa o al campo):
  - Telo asciugamano
  - Casco aperto, occhiali aperti
  - Bike pronta su rastrelliera, scarpe già clipped (se test) o accanto
  - Numeri/bib già montati

Warm-up: 10min mobility (spalla, anche, caviglie)

Main — 5 ripetute T1:
  1. Sprint 30m (simula uscita dall'acqua)
  2. Togli wetsuit (top half — porta in zona transizione)
  3. Togli wetsuit (bottom half — sequenza: piedi liberi)
  4. Casco (1° gesto sempre — regola FITri)
  5. Occhiali da sole / via maschera nuoto
  6. Scarpe bici — se clipped: skip; se da indossare: rapido
  7. Bike grab + 20m run con bike
  8. Mount line — flying mount (se skill già consolidato) o standard
  9. Pedala 30s
  10. Riposo 90s → ripeti

Cool-down: 10min easy walk

Target TSS: ~25 (carico basso, focus tecnica)

Razionale: memoria procedurale T1 [source: Cejuela 2013].
Sequenza gestuale automatica sotto stress simulato.

Successo: T1 sotto 90s in 4/5 ripetute. Sequenza identica ogni volta (no
ordine random). No oggetti dimenticati. Wetsuit removed in <30s.
```

## Template — T2 simulation (bike→run)

```
🚴→🏃 T2 transition drill — 35min

Setup zona transizione:
  - Scarpe da corsa con elastici (calzata rapida)
  - Cappellino + visiera + race belt pronti
  - Telo per controllo bike

Warm-up: 10min bike Z2

Main — 4 ripetute T2:
  1. Bike 5min @ Z2-Z3 (simula approccio T2 con HR elevato)
  2. Dismount line — flying dismount con scarpe già clipped (se skill consolidato)
     o normale (clipout + dismount classico)
  3. 20m run con bike (rack la bike correttamente — testa indietro)
  4. Casco off
  5. Scarpe corsa (elastici → calzata 5s)
  6. Cappellino + race belt
  7. Sprint 50m + 20m a passo gara
  8. Riposo 2min → ripeti

Cool-down: 10min easy run

Target TSS: ~35

Razionale: T2 critica perché dopo bici i muscoli posteriori sono attivati
diversamente — i primi 30-60s di corsa hanno pattern motorio "strano".
Allenarli con frequenza riduce drift di pace iniziale [source: Bonacci 2011].

Successo: T2 sotto 60s in 3/4 ripetute. Calzata scarpe <8s. Sprint primi 50m
con pace coerente (RPE giusto, no "starto" anomalo). Bike racked correttamente.
```

## Template — Brick + transition reali (race-week T-7)

```
🚴+T2+🏃 Race rehearsal — 90min

Bike: 45min con ultimi 5min @ race-pace (simula approccio T2)
T2 reale: cronometro avviato, sequenza completa (target < 60s)
Run: 25min @ race-pace cross sprint
Cool-down: 10min easy

Target TSS: ~95
Setup ESATTO come gara (stesso bag transizione, stessi numeri, stesso ordine).

Razionale: prove generali integrate. Il tempo T2 misurato qui è la baseline
per la race-day strategy [source: Cejuela 2013].

Successo: T2 misurato — è il TUO tempo. Niente sorprese di setup.
```

## Audit del transition time

Dopo ogni gara, l'atleta logga (manualmente o via skill) tempo T1 + T2.
Salvati in `docs/race_history.md` come:

```markdown
### Lavarone Cross Sprint 2026-08-29
- T1: 1:42 (target era 1:30 — slack su rimozione wetsuit)
- T2: 0:58 (target raggiunto — scarpe elastici hanno funzionato)
```

In `weekly_review.md`, se l'atleta ha gara A futura entro 8 settimane, propone
1 sessione transition/settimana fino a T-2.

## Vincoli specifici

- **Spalla destra**: niente movimenti aggressivi removal wetsuit braccio dx, usa la tecnica "bottom-up"
- **Fascite plantare**: scarpe da corsa con plantare ortotico già inserito (no test plantari nuovi)
- **Setup zona transizione**: l'atleta è ex-elite — protocolli consolidati, ma la skill richiede refresh dopo 2+ anni di stop

## Citation obbligatoria (Fase 2.4)

Cita con `[source: Cejuela 2013]`, `[source: Bonacci 2011]`. Quando applichi belief:
`[athlete-belief: ...]`.

## Cosa NON fare

- Non cambiare scarpe / wetsuit / casco nei 14gg prima di una gara A
- Non testare flying mount/dismount in race-week (se non già consolidato)
- Non saltare transition drills in race-week — i pochi minuti di drill T-3/T-2 valgono molto in race-day
- Non ignorare il setup zona transizione: visualizzazione mentale pre-gara aumenta fluidità
