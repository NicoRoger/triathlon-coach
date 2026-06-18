---
phase: 1
slug: test-suite-analytics-correctness
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4 |
| **Config file** | `pytest.ini` (testpaths = tests) |
| **Quick run command** | `python -m pytest tests/test_audit_resilience.py -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_audit_resilience.py -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | ANALYTICS-04 | — | N/A | unit | `python -m pytest tests/test_audit_resilience.py::test_b3_readiness_label_not_null -v` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | ANALYTICS-01,03,04,05 | — | Script non loga credenziali DB | manual | `python scripts/verify_analytics.py` | ❌ W0 | ⬜ pending |
| 1-gate | — | gate | VERIFY-01,ANALYTICS-01,02,03,05 | — | N/A | suite | `python -m pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_audit_resilience.py` — aggiungere `test_b3_readiness_label_not_null` per ANALYTICS-04
- [ ] `scripts/verify_analytics.py` — nuovo script operativo live (non test pytest)

*Infrastruttura pytest e suite esistente già presenti e funzionanti (172 test verdi).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HRV baseline esclude oggi per data — verifica live su DB reale | ANALYTICS-01 | Richiede connessione Supabase produzione con `.env` reale | `python scripts/verify_analytics.py` → sezione HRV mostra "media=Xms, SD=Yms (N giorni, oggi escluso)" |
| PMC mostra None (non 0) su cold-start — verifica live | ANALYTICS-03 | DB di produzione, physiology_zones non ancora disponibili | `python scripts/verify_analytics.py` → sezione PMC mostra CTL/ATL/TSB come None o valori reali |
| Readiness score + label su dati reali | ANALYTICS-04 | Verifica integrazione end-to-end con dati Supabase | `python scripts/verify_analytics.py` → sezione Readiness mostra Score: X/100 \| Label: ready/caution/rest |
| Risk volume bucketing con data Rome — verifica live | ANALYTICS-05 | Richiede attività reali in DB con `started_at` come datetime | `python scripts/verify_analytics.py` → sezione Risk mostra volumi per disciplina con "(date: Europe/Rome)" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
