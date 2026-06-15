---
status: testing
phase: 03-deploy-pipeline-resilience
source: [03-VERIFICATION.md]
started: 2026-06-07T11:30:00Z
updated: 2026-06-07T11:30:00Z
---

## Current Tests

### Test 1

number: 1
name: PIPELINE-01 — Exit 1 propagato nei GitHub Actions log (run reale Garmin failure)
expected: |
  Il workflow ingest.yml termina con il job "sync" in stato failed; il log mostra
  "Garmin sync fallito dopo 3 tentativi" e lo step "Garmin sync (with retries)" è rosso.
  Nessun retry silenzioso (job verde con fallimento swallowed).
awaiting: osservazione di un run CI reale con Garmin irraggiungibile, o iniezione temporanea di credenziali errate
why_deferred: Non è possibile forzare deterministicamente un fallimento Garmin Connect da locale — richiede ambiente live CI
deferred_to: Phase 4

---

### Test 2

number: 2
name: DEPLOY-04 — Transizione accepted→applied in log Actions reale
expected: |
  Nel log del run ingest successivo a un'accettazione, il modulo
  `coach.coaching.modulation --apply-accepted` mostra la transizione;
  la riga `plan_modulations` transisce da status='accepted' a status='applied'.
awaiting: modulazione proposta + accettata + ciclo ingest successivo
why_deferred: Al momento del deploy non era disponibile nessuna modulazione con status='accepted'
deferred_to: Phase 4 (verrà coperto insieme a VERIFY-05 K5 accept-tap)

---

## Context

Tutti i must-have della Phase 3 sono verificati da codice e test automatici.
I 2 item sopra sono osservazioni di comportamento runtime che i piani di Phase 3
hanno esplicitamente deferrato a Phase 4.

**Non sono gap di implementazione.** Il codice è corretto e testato.

Riferimento Phase 4: VERIFY-05 (K5 accept-tap), DEPLOY-04 live, PIPELINE-01 live.
