---
phase: 6
slug: physiological-adaptation-intelligence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-08
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4 |
| **Config file** | `pytest.ini` (root) |
| **Quick run command** | `python -m pytest tests/test_fatigue_classification.py tests/test_physio_adaptation.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_fatigue_classification.py tests/test_physio_adaptation.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | ADAPT-01 | — | N/A | unit | `pytest tests/test_fatigue_classification.py -v` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 0 | ADAPT-02 | — | N/A | static | `pytest tests/test_physio_adaptation.py -v` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | ADAPT-01 | T-06-01 | CHECK constraint su `fatigue_type` values | unit | `pytest tests/test_fatigue_classification.py::test_cardiovascular_signal -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | ADAPT-01 | — | N/A | unit | `pytest tests/test_fatigue_classification.py::test_muscular_signal -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | ADAPT-01 | — | N/A | unit | `pytest tests/test_fatigue_classification.py::test_fallback_rpe_only_no_splits -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 1 | ADAPT-01 | — | N/A | unit | `pytest tests/test_fatigue_classification.py::test_insufficient_data_short_session -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | ADAPT-02 | — | ON CONFLICT DO NOTHING idempotency | static | `pytest tests/test_physio_adaptation.py::test_migration_belief_seed_idempotent -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | ADAPT-02 | — | N/A | static | `pytest tests/test_physio_adaptation.py::test_migration_session_analyses_columns -x` | ❌ W0 | ⬜ pending |
| 06-03-03 | 03 | 2 | ADAPT-02 | — | N/A | static | `pytest tests/test_physio_adaptation.py::test_skill_active_beliefs_step -x` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 3 | ADAPT-03 | — | N/A | unit | `pytest tests/test_fatigue_classification.py::test_belief_update_minimum_sessions -x` | ❌ W0 | ⬜ pending |
| 06-04-02 | 04 | 3 | ADAPT-03 | — | N/A | unit | `pytest tests/test_fatigue_classification.py::test_belief_update_skips_null_session_type -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_fatigue_classification.py` — unit test `classify_fatigue_type()` + belief update job; coprire ADAPT-01 + ADAPT-03
- [ ] `tests/test_physio_adaptation.py` — static test migration SQL + skill file; coprire ADAPT-02

*Existing infrastructure covers all phase requirements (pytest.ini + tests/ directory already exist).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `last_fatigue_by_sport` nel Worker TypeScript ritorna dati reali da `session_analyses` | ADAPT-01 | Richiede Worker deployato + attività con splits reali in DB | Deploy Worker, chiamare `get_weekly_context` via MCP, verificare campo `last_fatigue_by_sport` non null per sport con sessioni recenti |
| Tag `[athlete-belief: ...]` appare inline nelle prescrizioni Gemini | ADAPT-02 | Output LLM non deterministico — dipende dal contesto della sessione | Eseguire `propose_session` con `active_beliefs` non vuoto, verificare presenza tag nel testo generato |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
