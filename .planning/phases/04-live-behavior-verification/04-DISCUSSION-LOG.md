# Phase 4: Live Behavior Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-07
**Phase:** 4-live-behavior-verification
**Areas discussed:** Fix scope, Modulation test setup, Brief zone display (FITNESS-04), Verification evidence format

---

## Fix scope

| Option | Description | Selected |
|--------|-------------|----------|
| Fix in Phase 4 | Phase 4 risolve il problema e lo verifica — completa solo quando il comportamento live corrisponde ai success criteria | ✓ |
| Documenta e defer | Phase 4 certifica solo cosa funziona, i fix vanno nelle fasi successive | |
| Fix solo se banale | Fix solo per configurazione/dati, codice rimandato | |

**User's choice:** Fix in Phase 4

| Option | Description | Selected |
|--------|-------------|----------|
| Sì, confine giusto | Phase 4 = zone numeriche; Phase 5 = struttura avanzata sessione | ✓ |
| Phase 4 fa anche struttura base | Già in Phase 4 se il brief mostra solo "60 min Z2" | |

**User's choice:** Confine netto Phase 4/Phase 5

| Option | Description | Selected |
|--------|-------------|----------|
| Fix il wiring in Phase 4 | Aggiunge step post_session_analysis in ingest.yml se mancante | ✓ |
| Solo documentare | Nota il problema per fasi successive | |

**User's choice:** Fix il wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Ispezione codice + api_usage | Verifica budget.py e tabella api_usage, nessun test live | ✓ |
| Test end-to-end completo | Trigger chiamata Anthropic reale | |

**User's choice:** Ispezione codice + api_usage

---

## Modulation test setup

| Option | Description | Selected |
|--------|-------------|----------|
| Trigger post-session analysis | python -m coach.coaching.post_session_analysis --recent su attività recente | ✓ |
| Riga sintetica SQL | INSERT diretto in plan_modulations | |

**User's choice:** Trigger post-session analysis (con fallback SQL)

| Option | Description | Selected |
|--------|-------------|----------|
| Fallback: riga sintetica SQL | Se trigger naturale non produce modulazione | ✓ |
| Solo via trigger naturale | VERIFY-05 marcato come non testabile | |
| Aspettare prossimo run ingest | Attendere 3h per modulazione naturale | |

**User's choice:** Fallback riga sintetica SQL

| Option | Description | Selected |
|--------|-------------|----------|
| Trigger ingest manuale | python -m coach.ingest.garmin subito dopo il tap | ✓ |
| Attesa ciclo automatico | Aspettare il prossimo ingest da 3h | |

**User's choice:** Trigger ingest manuale

| Option | Description | Selected |
|--------|-------------|----------|
| Stesso test verifica entrambi | Un tap ✅ copre VERIFY-05 + DEPLOY-04 | ✓ |
| Piani separati | DEPLOY-04 e VERIFY-05 in piani distinti | |

**User's choice:** Bundled in un unico scenario

---

## Brief zone display (FITNESS-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Non lo so — da verificare | Phase 4 inizia leggendo briefing.py e bot_messages | ✓ |
| Zone mai nel brief | Serve codice nuovo | |
| Hard-coded / placeholder | Fix: leggere physiology_zones dal DB | |

**User's choice:** Verifica stato attuale prima di decidere il fix

| Option | Description | Selected |
|--------|-------------|----------|
| Inline nella sessione: 'Z2: 142-178W / 4:36-5:20 min/km' | Compatto, mobile-friendly | ✓ |
| Blocco separato in fondo | Sezione === Zone riferimento === | |
| Solo zona target sessione | Solo la zona del giorno | |

**User's choice:** Inline nella sessione

| Option | Description | Selected |
|--------|-------------|----------|
| Se FTP mancante, mostra placeholder | [FTP non misurato — zone bici TBD] | ✓ |
| FTP c'è — ho fatto il test | Il test FTP è in DB | |

**User's choice:** Placeholder se FTP mancante

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 5 (FTP test scheduling) | Phase 4 verifica zone esistenti; test FTP → Phase 5 | ✓ |
| Phase 4 propone già il test FTP | Schedula FTP test come parte di Phase 4 | |

**User's choice:** Phase 5

---

## Verification evidence format

| Option | Description | Selected |
|--------|-------------|----------|
| Script di verifica (verify_live_behavior.py) | Unico script read-only, output pass/fail per ogni check | ✓ |
| Ispezione manuale documentata | Query DB + log GitHub Actions, risultati nel plan summary | |
| Mix: script DB + manuale Telegram | Script per DB, manuale per Telegram | |

**User's choice:** Script di verifica

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only informativo, nessun exit 1 | Come verify_analytics.py | ✓ |
| Exit 1 su failure | Per uso CI | |

**User's choice:** Read-only informativo

| Option | Description | Selected |
|--------|-------------|----------|
| Sì, include staleness check | Mostra ultima analisi/modulazione con età dei dati | ✓ |
| No, solo check binario | Solo esiste/non esiste | |

**User's choice:** Include staleness check

---

## Claude's Discretion

- Struttura interna verify_live_behavior.py (sezioni, stile output) — seguire pattern verify_analytics.py
- Threshold staleness (7 giorni come default ragionevole)
- Gestione errori in briefing.py per physiology_zones mancante

## Deferred Ideas

- FTP test bici scheduling → Phase 5
- Struttura sessione avanzata nel brief → Phase 5
- Exit 1 su failure in verify_live_behavior.py per CI → non in scope Phase 4
