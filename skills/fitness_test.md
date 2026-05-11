---
name: fitness_test
description: Proponi e gestisci test fitness (FTP, soglia corsa, CSS nuoto, LTHR). Include protocolli strutturati, naming Garmin obbligatorio, e auto-detection post-sync.
---

# Skill: Fitness Test

## Quando proporre un test

Proponi test quando:
- 6+ settimane dall'ultimo test della disciplina (controlla `physiology_zones` via `get_physiology_zones`)
- TSB > 0 per almeno 2 giorni (atleta fresco)
- HRV z-score > -0.5 il giorno precedente e il giorno del test
- Non siamo in race week o deload week
- L'atleta ha confermato di sentirsi pronto

Non proporre MAI:
- In settimana con CTL in calo >10% vs settimana precedente
- Entro 10 giorni dalla gara A (Lavarone)
- Subito dopo malattia o infortunio

## Come proporre (OBBLIGATORIO — NON NEGOZIABILE)

Quando proponi un test, DEVI fare TUTTE queste cose:

1. **Spiega il protocollo** (warmup, set principale, cooldown, timing)
2. **Dai il nome ESATTO Garmin** da usare (vedi `docs/FITNESS_TEST_PROTOCOL.md`)
3. **Committa con `commit_plan_change`** usando:
   - `session_type = 'fitness_test'`
   - `structured` con lo schema completo da `docs/FITNESS_TEST_PROTOCOL.md`
4. **Comunica all'atleta**: "Il sistema leggerà automaticamente il risultato dopo il sync Garmin e aggiornerà le tue zone."

## Messaggio template per l'atleta

"Domani propongo un **test [disciplina]**. Ecco il protocollo:

[dettaglio protocollo]

IMPORTANTE: su Garmin, salva l'attività con questo nome ESATTO:
`[garmin_activity_name dallo schema structured]`

Il sistema rileverà il test automaticamente e aggiornerà le zone entro 3 ore dal completamento."

## Ciclo test consigliato

1. FTP Bici (20min o ramp) → 3 giorni recovery
2. Soglia Corsa (30min) → 3 giorni recovery
3. CSS Nuoto (400+200m) → 3 giorni recovery
4. LTHR (opzionale, dal test corsa)

Ciclo completo: 12-15 giorni. Pianifica solo in blocchi di sviluppo (mai in taper).

## Aggiornamento automatico CLAUDE.md

Dopo ogni test, il sistema aggiorna automaticamente:
- `physiology_zones` nel DB
- `CLAUDE.md` §2 (ftp_attuale_w, threshold_pace_per_km, css_attuale_per_100m)

Non aggiornare manualmente CLAUDE.md per le zone — il sistema lo fa autonomamente.

## Cosa NON fare

- Non proporre test senza lo schema `structured` completo — il processore non lo riconoscerebbe
- Non inventare nomi Garmin diversi da quelli nel protocollo
- Non saltare il commit su `planned_sessions` — è il trigger per il matching automatico
