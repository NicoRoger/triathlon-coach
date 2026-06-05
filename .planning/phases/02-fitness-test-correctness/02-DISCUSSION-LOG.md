# Phase 2: Fitness Test Correctness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 02-fitness-test-correctness
**Areas discussed:** Verifica live DB physiology_zones, Cleanup dati corrotti E1/E2, Migrazione E4 (UNIQUE constraint), Status test fitness giugno 2026

---

## Verifica live DB physiology_zones

### Q1: Output dello script verify_physiology.py

| Option | Description | Selected |
|--------|-------------|----------|
| Solo print delle righe esistenti | Stampa disciplina, metodo, data, valori + bounds check visivo. Se vuota → messaggio esplicito | ✓ |
| Print + controllo bounds automatico | Aggiunge exit 1 se righe fuori range, per uso come health check | |
| Print + query anche activity_id | Include riferimento all'attività sorgente (test_activity_id) | |

**User's choice:** Solo print delle righe esistenti (Recommended)
**Notes:** Script informativo puro, nessun exit 1 automatico.

### Q2: Verifica codice sorgente E1/E2

| Option | Description | Selected |
|--------|-------------|----------|
| Solo query DB — il codice parla da sé | I test e1/e2 già passano. Script si concentra su dati live | ✓ |
| Script verifica anche il codice | Cerca stringhe 'averageSpeed' e 'averagePace' come fallback nel sorgente | |
| Tu decidi | Lascia a Claude la scelta | |

**User's choice:** Solo query DB (Recommended)
**Notes:** I test E1/E2 già coprono la verifica codice.

### Q3: Scope dello script oltre physiology_zones

| Option | Description | Selected |
|--------|-------------|----------|
| Solo physiology_zones | Scope minimo: stampa le zone di ogni disciplina con bounds check visivo | |
| physiology_zones + planned_sessions fitness_test | Mostra anche le sessioni fitness_test pianificate | |
| physiology_zones + CLAUDE.md fields | Verifica anche che ftp_attuale_w/threshold_pace_per_km/css_attuale_per_100m in CLAUDE.md corrispondano ai valori in DB | ✓ |

**User's choice:** physiology_zones + CLAUDE.md fields
**Notes:** Il confronto DB vs CLAUDE.md è critico per sapere se il processore ha aggiornato CLAUDE.md correttamente.

---

## Cleanup dati corrotti E1/E2

### Q1: Azione su righe out-of-bounds

| Option | Description | Selected |
|--------|-------------|----------|
| DELETE righe out-of-bounds + log | Script individua le righe fuori PLAUSIBLE_BOUNDS e le cancella. Irreversibile. | ✓ |
| Solo segnala, non cancella | Mostra le righe sospette ma non tocca il DB. Nicolò decide via SQL editor. | |
| Lascia tutto, bounds check nel processore basta | I nuovi test non sovrascrivono corrotti (idempotency E4). Vecchi rimangono ma inutilizzati. | |

**User's choice:** DELETE righe out-of-bounds + log (Recommended)

### Q2: Script separato vs flag su verify_physiology.py

| Option | Description | Selected |
|--------|-------------|----------|
| Script separato scripts/cleanup_physiology_zones.py | Separare read-only da distruttivo. Con --confirm per eseguire DELETE | ✓ |
| Stesso script verify_physiology.py con flag --cleanup | Un solo file: --cleanup esegue DELETE; senza flag è solo print | |
| SQL diretto nel verify_physiology.py | Lo script stampa le DELETE SQL ma non le esegue | |

**User's choice:** Script separato (Recommended)
**Notes:** Chiarezza sulla natura distruttiva del cleanup. Dry run senza flag, DELETE con --confirm.

---

## Migrazione E4 (UNIQUE constraint)

### Q1: Scope della migrazione

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 3 — insieme alle altre migrazioni | Phase 3 è "Deploy & Pipeline Resilience" e include tutte le migrazioni pending. Coerente. | ✓ |
| Phase 2 — anticipiamo solo questa | Sblocca il processore. Nicolò può testare subito dopo Phase 2 senza aspettare Phase 3. | |
| Phase 2 la documenta come prerequisito | verify_physiology.py verifica che il constraint esista e avvisa se manca. | |

**User's choice:** Phase 3 (Recommended)
**Notes:** Accettato il rischio che se Nicolò runna il processore tra Phase 2 e Phase 3 con una riga già in DB, l'upsert potrebbe fallire. Risk basso con tabella vuota/pulita.

---

## Status test fitness giugno 2026

### Q1: I test sono stati eseguiti?

| Option | Description | Selected |
|--------|-------------|----------|
| No — non ancora eseguiti | physiology_zones vuota. Phase 2 verifica readiness + crea script. | |
| Sì — almeno uno già eseguito | Dati in physiology_zones da verificare adesso. | ✓ |
| Non lo so — da verificare con lo script | Lo script decide. | |

**User's choice:** Sì — li ha già eseguiti tutti (FTP bici, soglia corsa, CSS nuoto)
**Notes:** Risposta libera dell'atleta: "Si li ho già eseguiti tutti, bisogna prendere quei valori li"

### Q2: Il processore li ha già elaborati?

| Option | Description | Selected |
|--------|-------------|----------|
| Non lo so — da verificare con lo script | verify_physiology.py mostra lo stato del DB. | ✓ |
| Sì, elaborati automaticamente | Il ciclo ingest ha creato le righe. Solo da verificare. | |
| No, mai runnato | Bisogna triggerare manualmente. | |

**User's choice:** Non lo so (da verificare con lo script)

### Q3: Conosce i valori attesi?

| Option | Description | Selected |
|--------|-------------|----------|
| Sì, li dico dopo | Li confrontiamo con l'output dello script. | |
| No, non li ricordo — lo script dà i numeri | Confronto solo bounds-check (plausibili?), non valore atteso. | ✓ |
| Li ho su Garmin Connect | Consultabili su Garmin. Includibili come riferimento. | |

**User's choice:** No, non li ricordo
**Notes:** Verifica solo per plausibilità (nei bounds), non confronto con valore esatto.

### Q4: Se physiology_zones vuota, Phase 2 triggera il processore?

| Option | Description | Selected |
|--------|-------------|----------|
| Sì — Phase 2 include anche il trigger | Se DB vuoto, runnare il processore con finestra ampliata per coprire i test di giugno. | ✓ |
| No — Phase 2 solo verifica, non triggera | Se vuoto, documenta il gap. Phase 4 include il trigger. | |
| Tu decidi | Lascia a Claude la scelta. | |

**User's choice:** Sì (Recommended)
**Notes:** Finestra temporale ampliata oltre le 6h standard per coprire tutti i test di giugno 2026.

---

## Claude's Discretion

Nessuna area delegata a Claude — tutte le decisioni prese dall'atleta.

## Deferred Ideas

- Migrazione E4 → Phase 3
- LTHR test processing → non in scope Phase 2
- Bounds-check CI con exit 1 → potenzialmente Phase 4
- Confronto con FTP stimato Garmin → non affidabile, non in scope
