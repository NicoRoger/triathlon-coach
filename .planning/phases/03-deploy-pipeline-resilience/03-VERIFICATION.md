---
phase: 03-deploy-pipeline-resilience
verified: 2026-06-07T00:00:00Z
status: human_needed
score: 4/6 success criteria verified (2 richiedono osservazione live nei log)
requirements_covered: [DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, PIPELINE-01, PIPELINE-02, PIPELINE-03, PIPELINE-04]
requirements_missing: []
human_verification:
  - test: "Osservare un GitHub Actions run ingest reale che fallisce dopo 3 tentativi Garmin e mostra il job rosso nel log"
    expected: "Il run Actions termina con exit 1 propagato, il job e' rosso (non verde silenzioso)"
    why_human: "Non e' possibile forzare deterministicamente un fallimento Garmin da codice locale; richiede un run CI reale con Garmin irraggiungibile"
  - test: "Osservare nel log Actions (o in Supabase) la transizione accepted->applied per una modulazione reale dopo un run ingest post-deploy"
    expected: "Una riga plan_modulations con status='accepted' transisce a status='applied' nel ciclo ingest successivo all'accettazione"
    why_human: "DEPLOY-04 SC3 richiede log del primo run post-deploy con modulazione reale; nessuna modulazione accepted era presente al momento del deploy (confermato dal SUMMARY 03-04)"
---

# Phase 03: Deploy & Pipeline Resilience — Verification Report

**Phase Goal:** Tutte le migrazioni pending sono live su Supabase, il Telegram bot e' ridistribuito con i fix K2-K5, e la pipeline ingest e' resiliente con exit codes corretti, DR funzionante e idempotency sul brief
**Verified:** 2026-06-07
**Status:** human_needed
**Re-verification:** No — verifica iniziale

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Success Criterion | Status | Evidenza |
|---|-------------------|--------|---------|
| SC1 | Migrazioni live in Supabase — CHECK, UNIQUE, FK, expires_at confermati | VERIFIED | `scripts/verify_migrations.py` esce 0 con 9 PASS (SUMMARY 03-01 + esecuzione attestata dall'atleta); commit `5ac0c91` presente in git |
| SC2 | `wrangler deploy` eseguito; K2/K3/K4/K5 attivi nel worker live | VERIFIED | Commit `680ff3c` presente; K4/K5/K2/K3 marker in `index.ts` righe 112/270/803/909/1215 confermati; deploy Version ID `604ae1fc` nel SUMMARY 03-04; K4 no-500 confermato da Nicolò via Telegram |
| SC3 | `apply_accepted_modulations` in `ingest.yml` + transizione `accepted→applied` in un log reale | PARTIAL | Wiring in ingest.yml VERIFIED (riga 101: `python -m coach.coaching.modulation --apply-accepted`; nessun `if: always()`); 2 test passano (`test_k1_accepted_modulation_gets_applied`, `test_d2_full_apply_accepted`). La parte "log del primo run post-deploy" e' DEFERRED a Phase 4 per assenza di modulazione accepted al momento del deploy |
| SC4 | Ingest Garmin propaga exit 1 su fallimento nei GitHub Actions log | PARTIAL | Codice exit-1 presente e intatto in ingest.yml righe 61-64 (`if [ "$ok" -ne 1 ]; then exit 1; fi`). Conferma via log Actions reale DEFERRED a Phase 4 — non verificabile deterministicamente da locale |
| SC5 | DR snapshot aborta su tabelle critiche vuote; watchdog rileva health row mancante | VERIFIED | `scripts/dr_snapshot.py`: `EmptySnapshotError` (riga 38), `assert_snapshot_sane` (riga 42), chiamata riga 84. `scripts/watchdog.py`: `compute_alerts` itera `THRESHOLDS_HOURS.items()` (riga 34). 3 test passano: `test_l3_empty_snapshot_aborts`, `test_l4_watchdog_alerts_missing_component`, `test_l4_watchdog_stale_component` |
| SC6 | Brief mattutino non inviato due volte — idempotency verificata nei log Telegram | PARTIAL | `_brief_already_sent_today()` presente in `briefing.py` (riga 679); chiamata in `main()` riga 711 con early-return; 3 unit test passano (`test_pipeline04_brief_idempotency_*`). Conferma "nei log Telegram" (doppio trigger reale) DEFERRED a Phase 4 |

**Score:** 4/6 success criteria completamente verificati da codice; 2 parzialmente verificati (codice ok, conferma live demandata a Phase 4)

---

### Required Artifacts

| Artifact | Atteso | Status | Dettagli |
|----------|--------|--------|---------|
| `scripts/verify_migrations.py` | Verifier con 4 costanti EXPECTED_*, exit-code 0/1 | VERIFIED | 153 righe; `EXPECTED_UNIQUE_CONSTRAINTS`, `EXPECTED_FK_CONSTRAINTS`, `EXPECTED_CHECK_CONSTRAINTS`, `EXPECTED_COLUMNS` presenti; `sb.rpc()` fallback presente; `sys.exit(1)` presente; `if __name__ == "__main__"` presente; syntax-ok confermato |
| `.github/workflows/ingest.yml` | Step apply-accepted senza `if: always()`, con `continue-on-error: true` | VERIFIED | Riga 95-101: step presente, `if: always()` assente, `continue-on-error: true` presente (riga 100), `--apply-accepted` presente (riga 101); Garmin retry con `exit 1` intatto (righe 55-64) |
| `tests/test_audit_resilience.py` | 3 test espliciti per `_brief_already_sent_today` (Wave 0 gap) | VERIFIED | `test_pipeline04_brief_idempotency_skips_when_already_sent`, `_sends_when_none`, `_filters_on_morning_brief_purpose` — tutti e 3 passano |
| `workers/telegram-bot/src/index.ts` | Marker audit K2/K3/K4/K5 presenti | VERIFIED | Riga 112: K4; riga 270: `pattern_correction` (K3); riga 803: K5 (inizio); riga 909: K2; riga 1215: K5 (guard `if (!resp.ok)`) |
| `workers/telegram-bot/package-lock.json` | Generato da npm install (commit `484ca52`) | VERIFIED | Commit presente in git log con 787 righe aggiunte |

---

### Key Link Verification

| From | To | Via | Status | Dettagli |
|------|----|-----|--------|---------|
| `scripts/verify_migrations.py` | `information_schema` (primary) + `sb.rpc()` (fallback) | `sb.schema("information_schema")` con except + `sb.rpc("get_public_constraints")` | VERIFIED | Entrambi i path presenti (righe 51-71 per constraints, 80-99 per columns) |
| `scripts/verify_migrations.py` | `coach.utils.supabase_client.get_supabase` | `from coach.utils.supabase_client import get_supabase` | VERIFIED | Riga 13 |
| `.github/workflows/ingest.yml` | `coach.coaching.modulation.apply_accepted_modulations` | `python -m coach.coaching.modulation --apply-accepted` step | VERIFIED | Riga 101; step defaults a `if: success()` (no `if: always()`) |
| `.github/workflows/ingest.yml` Garmin step | GitHub Actions step result (exit 1) | `if [ "$ok" -ne 1 ]; then exit 1; fi` | VERIFIED (code) / DEFERRED (live log) | Righe 61-64 — code path presente; conferma live in Phase 4 |
| `tests/test_audit_resilience.py` | `coach.planning.briefing._brief_already_sent_today` | `from coach.planning.briefing import _brief_already_sent_today` | VERIFIED | Riga 1057 (e 1073, 1088) |

---

### Behavioral Spot-Checks

| Behavior | Comando | Risultato | Status |
|----------|---------|-----------|--------|
| `verify_migrations.py` parse pulito | `python -c "import ast; ast.parse(...)"` | "syntax-ok" | PASS |
| Test DEPLOY-04 accepted→applied | `pytest test_k1_accepted_modulation_gets_applied test_d2_full_apply_accepted` | 2 passed in 5.79s | PASS |
| Test PIPELINE-02 watchdog missing | `pytest test_l4_watchdog_alerts_missing_component test_l4_watchdog_stale_component` | 2 passed | PASS |
| Test PIPELINE-03 DR abort | `pytest test_l3_empty_snapshot_aborts` | 1 passed | PASS |
| Test PIPELINE-04 idempotency | `pytest -k "pipeline04_brief_idempotency"` | 3 passed in 3.74s | PASS |
| Test migration file content | `pytest test_o4_o6_migration_present test_o7_e4_o8_o9_migration_present` | 2 passed | PASS |

---

### Requirements Coverage

| Requirement | Plan | Descrizione | Status | Evidenza |
|-------------|------|-------------|--------|---------|
| DEPLOY-01 | 03-01 | Tutte le migrazioni pending in OPEN_ISSUES.md eseguite in Supabase e verificate | VERIFIED | 11 migration eseguite (human-action); `verify_migrations.py` esce 0 con 9 PASS confermato dall'atleta |
| DEPLOY-02 | 03-01 | `2026-06-01-resilience-audit.sql` eseguita e contenuto live sul DB | VERIFIED | Constraints `races_name_date_unique`, `physiology_zones_disc_validfrom_method_unique`, `unique_planned_date_sport_type`, `mesocycles_target_race_fk`, `plan_modulations_status_check`, `subjective_log_kind_check`, `plan_modulations.expires_at` confermati da exit 0 |
| DEPLOY-03 | 03-04 | Bot Telegram ridistribuito con wrangler e fix K2/K3/K4/K5 attivi | VERIFIED | Commit `680ff3c`; Version ID `604ae1fc`; K4 no-500 confermato via Telegram; tsc --noEmit exit 0 |
| DEPLOY-04 | 03-02 | `apply_accepted_modulations` chiamato da ingest.yml; transizione accepted→applied in run reale | PARTIAL | Wiring in ingest.yml VERIFIED (riga 101); 2 test passano; la transizione in un run reale e' demandata a Phase 4 (nessuna modulazione accepted disponibile al momento del deploy) |
| PIPELINE-01 | 03-02 | Ingest Garmin propaga exit 1 su fallimento; nessun retry silenzioso | PARTIAL | Code path exit-1 presente e intatto (ingest.yml righe 61-64); conferma via log Actions reale demandata a Phase 4 |
| PIPELINE-02 | 03-03 | Watchdog rileva componenti con health row mancante, non solo righe stantie | VERIFIED | `compute_alerts` itera `THRESHOLDS_HOURS.items()` (riga 34 watchdog.py); 2 test passano |
| PIPELINE-03 | 03-03 | DR snapshot aborta su tabelle critiche vuote invece di committare backup corrotto | VERIFIED | `EmptySnapshotError` + `assert_snapshot_sane` + chiamata riga 84 in dr_snapshot.py; 1 test passa |
| PIPELINE-04 | 03-03 | Brief mattutino inviato una sola volta (idempotency); nessun doppio invio | VERIFIED (code) / DEFERRED (Telegram log) | `_brief_already_sent_today` in briefing.py main() riga 711; 3 unit test passano; conferma "nei log Telegram" demandata a Phase 4 |

**Nota:** REQUIREMENTS.md (traceability table) segna DEPLOY-04 e PIPELINE-01/02/03/04 come "Pending" ma ROADMAP.md (coverage table) li segna "Complete". Questa discrepanza riflette il fatto che i piani hanno deliberatamente separato la verifica del codice (Phase 3) dalla conferma live (Phase 4), con ROADMAP.md aggiornato post-esecuzione a riflettere il completamento dei piani. Per Phase 3, il target dichiarato dai piani era "fix presenti e provati unit-test"; la conferma live e' esplicitamente assegnata a Phase 4.

---

### Anti-Patterns Found

| File | Riga | Pattern | Severita | Impatto |
|------|------|---------|----------|--------|
| Nessuno | - | - | - | - |

Nessun anti-pattern bloccante trovato nei file modificati in Phase 3. I commit introdotti sono puliti.

---

### Human Verification Required

#### 1. PIPELINE-01 — Exit 1 propagato nei GitHub Actions log

**Test:** Attendere (o forzare) un fallimento del sync Garmin e osservare il log del workflow `ingest.yml` su GitHub Actions.
**Expected:** Il job `sync` risulta rosso (failed); il log mostra "Garmin sync fallito dopo 3 tentativi" e lo step "Garmin sync (with retries)" e' in stato failure.
**Why human:** Non e' possibile forzare deterministicamente un fallimento Garmin da locale senza un mock del servizio Garmin Connect. Richiede attendere un run reale con Garmin irraggiungibile, oppure iniettare temporaneamente credenziali errate in Actions.

#### 2. DEPLOY-04 (parziale) — Transizione accepted→applied in un log Actions reale

**Test:** Proporre una modulazione via il sistema (o simulare una riga con `status='accepted'` in `plan_modulations`), quindi attendere il ciclo ingest successivo e verificare che il log Actions mostri la transizione e che la riga in DB abbia `status='applied'`.
**Expected:** Nel log del run ingest successivo appare l'applicazione della modulazione; la riga in `plan_modulations` transisce da `accepted` ad `applied`.
**Why human:** Al momento del deploy non era disponibile nessuna modulazione con `status='accepted'`; la transizione live richiede un ciclo completo proposta-accettazione-applicazione.

**Nota:** K5 accept-tap (DEPLOY-03 partial) e' gia' registrato come VERIFY-05 in Phase 4 — non e' un gap di Phase 3.

---

### Gaps Summary

**Nessun BLOCKER identificato.** Tutti i must-have dei piani (artifacts, key links, test) sono presenti e verificati dal codice.

I 2 human_verification items riguardano la conferma live di comportamenti end-to-end (exit 1 in CI reale; transizione accepted→applied in un run reale) che i piani di Phase 3 hanno esplicitamente e documentatamente deferrato a Phase 4. Questi non sono gap di implementazione ma osservazioni di comportamento runtime che richiedono l'ambiente live.

**Discrepanza REQUIREMENTS.md vs ROADMAP.md:** Il file REQUIREMENTS.md non e' stato aggiornato con le checkbox `[x]` per DEPLOY-04 e PIPELINE-01/02/03/04, mentre ROADMAP.md li segna "Complete". Questa e' una inconsistenza documentale da correggere in Phase 4 (o all'inizio del prossimo piano) ma non e' un gap funzionale.

---

_Verificato: 2026-06-07_
_Verifier: Claude (gsd-verifier)_
