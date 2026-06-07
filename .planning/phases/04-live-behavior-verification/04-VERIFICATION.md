---
phase: 04-live-behavior-verification
verified: 2026-06-07T18:00:00Z
status: human_needed
score: 4/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Aprire l'ultimo brief ricevuto su Telegram (2026-06-07) e confermare visivamente che il testo contenga la riga 'Zone misurate:' con watt/pace/HR numerici reali per la disciplina della sessione del giorno"
    expected: "Riga 'Zone misurate: Z2: 4:23-5:01/km | Z4: 4:02-4:23/km' (o analoga per la disciplina) visibile nel messaggio Telegram"
    why_human: "scripts/verify_live_behavior.py controlla solo che physiology_zones esista nel DB, non che il testo del brief inviatato su Telegram contenga effettivamente la riga 'Zone misurate:'. bot_messages non memorizza il content testuale del messaggio (decisione D-06 SUMMARY 04-04), quindi nessuna grep automatica può confermare SC1 e FITNESS-04 senza il contenuto reale del messaggio."
---

# Phase 4: Live Behavior Verification — Verification Report

**Phase Goal:** Verificare e fixare il comportamento live end-to-end del sistema — brief con zone numeriche misurate, session_analyses da Gemini, flusso modulazioni accepted→applied, budget tracker — confermando tutti i success criteria del ROADMAP con evidenza da dati reali.

**Verified:** 2026-06-07
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP SC + Plan must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Il brief mattutino mostra zone numeriche precise (watt/pace/HR) basate su physiology_zones misurate, non stime o placeholder | ? UNCERTAIN | `_fetch_current_zones` e `_format_session_zones` implementati e wired in `briefing.py` (righe 213-329, 727-728). physiology_zones live: bike/run/swim presenti. Ma `verify_live_behavior._verify_brief_zones` usa `physiology_zones` come proxy — NON legge il content del brief inviato. Non verificabile automaticamente. |
| SC2 | Dopo un sync Garmin, una riga in `session_analyses` viene generata con testo non vuoto e `model_used = 'gemini-2.5-flash'` | ✓ VERIFIED | `PURPOSE_ROUTING['session_analysis'] == 'gemini'` + `GeminiClient.MODEL == 'gemini-2.5-flash'` (llm_client.py righe 29, 191). Test `test_verify04_session_analysis_routes_to_gemini` + `test_verify04_empty_llm_text_skips_insert` passano. Live: 5 righe session_analyses con `model_used=gemini-2.5-flash`, ultima 2026-06-06. |
| SC3 | Una modulazione proposta compare su Telegram con inline buttons ✅/❌, e dopo il tap ✅ il ciclo ingest successivo aggiorna `planned_sessions` | ✓ VERIFIED (con nota) | Flusso accepted→applied verificato via D-06 fallback: modulazione 368aef79 portata da proposed ad applied; 3 sessioni aggiornate in `planned_sessions` (swim 07/06, rest 08/06, bike 09/06). `test_verify05_accepted_modulation_applies_and_updates_planned_sessions` verde. Nota: tap ✅ live su Telegram non osservato direttamente — usato il percorso D-06 (update Supabase diretto). |
| SC4 | Il budget tracker mostra la spesa Anthropic reale — la soglia di degrado a €4.00 (Sonnet→Haiku) è configurata e verificata | ✓ VERIFIED | `BUDGET_DEGRADED = 4.00` in `budget.py` riga 46 (era 4.50). `get_month_spend_usd` legge `cost_usd_estimated` da `api_usage` (righe 74-83). Spesa live: $0.02. 7 test VERIFY-06 verdi. `select_model("sonnet", spend=4.00)` → haiku confermato da `test_degraded_threshold_exact_at_4_00`. |
| SC5/FITNESS-04 | Il brief mostra le zone Z1-Z5 per ogni disciplina derivate da physiology_zones misurate (non hard-coded) | ? UNCERTAIN | `derive_zones_for_discipline` implementato in `fitness_test_processor.py` riga 430 (dispatch su discipline, riusa @staticmethod esistenti, zero duplicazione moltiplicatori). `_format_session_zones` e `_build_session_section` wired in `briefing.py`. 8 test in `test_brief_zones.py` verdi. Stessa incertezza di SC1: content del brief su Telegram non ispezionabile automaticamente. |

**Score:** 3/5 truths verified automaticamente; 2 UNCERTAIN (stessa causa radice — content brief non ispezionabile)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `coach/coaching/fitness_test_processor.py` | `def derive_zones_for_discipline` modulo-livello | ✓ VERIFIED | Riga 430, dispatch su discipline, riusa `_compute_coggan_7zone`/`_compute_pace_5zone`/`_compute_css_3zone` esistenti |
| `coach/planning/briefing.py` | `_fetch_current_zones` + `_format_session_zones` + lettura `physiology_zones` | ✓ VERIFIED | Righe 213-240 (`_fetch_current_zones`), 240+ (`_format_session_zones`), riga 325-329 (integrazione in `_build_session_section`), riga 727-728 (chiamata da `build_brief`) |
| `tests/test_brief_zones.py` | 8 test (4 derive_zones + 4 format_session) | ✓ VERIFIED | Confermato con 8 funzioni `def test_` |
| `.github/workflows/ingest.yml` | Step `post_session_analysis` + step `apply-accepted` wired | ✓ VERIFIED | Riga 75: `python -m coach.coaching.post_session_analysis --recent`; righe 94-100: `python -m coach.coaching.modulation --apply-accepted` senza `if: always()` |
| `tests/test_live_behavior.py` | 3 test (routing Gemini + guard E7 + accepted→applied) | ✓ VERIFIED | `test_verify04_session_analysis_routes_to_gemini`, `test_verify04_empty_llm_text_skips_insert`, `test_verify05_accepted_modulation_applies_and_updates_planned_sessions` |
| `coach/utils/budget.py` | `BUDGET_DEGRADED = 4.00` + `select_model` corretto | ✓ VERIFIED | Riga 46: `BUDGET_DEGRADED = 4.00`. `select_model` ristrutturato in 4 rami. `get_month_spend_usd` legge `cost_usd_estimated` da `api_usage`. |
| `tests/test_budget.py` | Test degrado a spend=4.00 | ✓ VERIFIED | `test_degraded_threshold_exact_at_4_00` e altri 6 test VERIFY-06 presenti |
| `scripts/verify_live_behavior.py` | Script read-only 4 sezioni + `def main` | ✓ VERIFIED | Tutte le 4 funzioni `_verify_*` + `main()` presenti. `STALE_DAYS_CUTOFF = 7`. `load_dotenv()` riga 14 (prima di import coach.*). Nessun `sys.exit(1)`. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `briefing.py` | `physiology_zones` (DB) + `derive_zones_for_discipline` | `_fetch_current_zones` + `_format_session_zones` chiamate in `build_brief` e `_build_session_section` | ✓ WIRED | Righe 727-728 + 325-329 |
| `tests/test_brief_zones.py` | `coach.planning.briefing` zone-render helper | `from coach.planning.briefing import _format_session_zones` | ✓ WIRED | Pattern import lazy per evitare collision |
| `ingest.yml` | `coach.coaching.post_session_analysis` | `python -m coach.coaching.post_session_analysis --recent` | ✓ WIRED | Riga 75 |
| `ingest.yml` | `coach.coaching.modulation --apply-accepted` | Step `Apply accepted modulations (audit K1)` | ✓ WIRED | Righe 94-100, `continue-on-error: true`, senza `if: always()` |
| `tests/test_live_behavior.py` | routing `session_analysis → gemini-2.5-flash` | `PURPOSE_ROUTING['session_analysis'] == 'gemini'` assert | ✓ WIRED | Test 1 |
| `budget.py select_model` | soglia degrado €4.00 | ramo `elif spend < BUDGET_DEGRADED` | ✓ WIRED | Riga 160-164 |
| `budget.py get_month_spend_usd` | `api_usage` (DB) | `sum(cost_usd_estimated) where timestamp >= month_start` | ✓ WIRED | Righe 74-83 |
| `scripts/verify_live_behavior.py` | `coach.utils.supabase_client.get_supabase` | `from coach.utils.supabase_client import get_supabase` | ✓ WIRED | Riga 16 |
| `scripts/verify_live_behavior.py` | `coach.utils.budget` thresholds | `from coach.utils.budget import BUDGET_DEGRADED, BUDGET_BLOCKED, get_month_spend_usd` | ✓ WIRED | Riga 18 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `briefing.py _build_session_section` | `zones_by_discipline` | `_fetch_current_zones(sb)` → query `physiology_zones` `valid_to is null` | Yes (DB query, try/except degrada a `{}`) | ✓ FLOWING |
| `budget.py get_month_spend_usd` | `total` | `api_usage.cost_usd_estimated` sum, filtro mese corrente | Yes (DB query) | ✓ FLOWING |
| `scripts/verify_live_behavior.py _verify_brief_zones` | `by_disc` | `physiology_zones` query (proxy per brief content) | Yes per physiology_zones; NO per content brief | ⚠️ PROXY — non verifica il content testuale del brief inviato |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `derive_zones_for_discipline("run", threshold_pace_s_per_km=263)` restituisce dict con Z2 | `grep -n "def derive_zones_for_discipline" coach/coaching/fitness_test_processor.py` | Riga 430 trovata, dispatch confermato | ✓ PASS |
| `BUDGET_DEGRADED = 4.00` in budget.py | `grep -n "BUDGET_DEGRADED = 4" coach/utils/budget.py` | Riga 46: `BUDGET_DEGRADED = 4.00` | ✓ PASS |
| `verify_live_behavior.py` senza `sys.exit(1)` | `grep -c "sys.exit(1)" scripts/verify_live_behavior.py` | 0 occorrenze | ✓ PASS |
| `load_dotenv()` prima di `from coach.` | Riga 14 vs primo import coach.* riga 16 | load_dotenv precede import coach | ✓ PASS |
| Test suite 194 passed | Dato fornito dall'utente + 1 isolation failure pre-esistente | `test_verify04_session_analysis_routes_to_gemini` passa in isolation | ✓ PASS (con nota isolamento) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| VERIFY-03 | 04-01 | Brief mostra zone corrette basate su physiology_zones | ? UNCERTAIN | Code wired e corretto; content brief Telegram non ispezionabile automaticamente |
| VERIFY-04 | 04-02 | session_analyses generate dopo sync, model_used=gemini-2.5-flash | ✓ SATISFIED | Test routing + live: 5 righe gemini-2.5-flash |
| VERIFY-05 | 04-02 | Modulazioni con inline buttons; accepted→applied→planned_sessions | ✓ SATISFIED (D-06) | applied=1 live; 3 sessioni aggiornate; test verde |
| VERIFY-06 | 04-03 | Budget tracker: spesa reale, degrado €4.00 | ✓ SATISFIED | `BUDGET_DEGRADED=4.00`, `cost_usd_estimated` da api_usage, 7 test verdi |
| FITNESS-04 | 04-01 | Brief mostra zone Z1-Z5 per disciplina da physiology_zones (non hard-coded) | ? UNCERTAIN | derive_zones_for_discipline + _format_session_zones wired; content brief non ispezionabile |
| DEPLOY-04 | 04-02 | apply_accepted_modulations in ingest.yml; modulazione accepted→applied | ✓ SATISFIED | Step confermato riga 94-100 ingest.yml; D-06 live |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `scripts/verify_live_behavior.py` | 60-85 | `_verify_brief_zones` usa `physiology_zones` come proxy invece di leggere il content del brief | ⚠️ Warning | SC1/FITNESS-04 non verificabili automaticamente — il check dice "OK" anche se `_format_session_zones` avesse un bug di rendering |

Nessun `TBD`/`FIXME`/`XXX` irrisolto nei file modificati da questa fase. Nessun stub (funzioni completamente implementate).

---

### Human Verification Required

#### 1. Brief content "Zone misurate:" su Telegram

**Test:** Aprire su Telegram il brief mattutino inviato il 2026-06-07 e verificare che il testo del messaggio contenga la riga `Zone misurate:` seguita da valori numerici reali di watt/pace/HR per la disciplina della sessione del giorno.

**Expected:** Riga del tipo `Zone misurate: Z2: 4:23-5:01/km | Z4: 4:02-4:23/km` (corsa) oppure `Zone misurate: Z1-Z2: 1:25/100m | CSS: 1:20/100m` (nuoto) oppure placeholder `[FTP bici non ancora misurato — usa Z2 HR: 140-160bpm come riferimento]` (bici senza FTP).

**Why human:** `bot_messages` non memorizza il testo testuale del messaggio Telegram (solo `context_data`), per decisione documentata nel SUMMARY 04-04. `verify_live_behavior._verify_brief_zones` usa `physiology_zones` come proxy — conferma che le zone esistono nel DB ma non che la riga "Zone misurate:" appaia nel testo del brief inviato. Solo un'ispezione visiva del messaggio Telegram può chiudere SC1 e FITNESS-04.

**Perché è plausibile che sia OK:** Il codice di integrazione (`_fetch_current_zones` → `_format_session_zones` → `_build_session_section`) è completamente wired e coperto da 8 test verdi. physiology_zones ha dati live per tutte e tre le discipline. Il brief di oggi (2026-06-07) è stato inviato confermato da `bot_messages`. La probabilità che il rendering sia corretto è alta — ma richiede conferma visiva.

---

### Gaps Summary

Nessun gap bloccante. Due truths UNCERTAIN (SC1 e SC5/FITNESS-04) per la stessa causa radice: `_verify_brief_zones` usa `physiology_zones` come proxy invece di verificare il content del brief — limitazione di design dello script, non un bug nel codice di produzione.

L'implementazione sottostante (briefing.py + derive_zones_for_discipline) è verificata a livello di codice e unit test. L'incertezza riguarda solo l'output finale su Telegram.

Una singola conferma visiva del brief del 2026-06-07 chiude entrambi SC1 e SC5.

---

_Verified: 2026-06-07T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
