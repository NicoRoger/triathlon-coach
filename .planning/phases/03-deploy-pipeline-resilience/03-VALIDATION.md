---
phase: 3
slug: deploy-pipeline-resilience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-06
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4 |
| **Config file** | `pytest.ini` |
| **Quick run command** | `pytest tests/test_audit_resilience.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_audit_resilience.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite green + `python scripts/verify_migrations.py` PASS + manual Telegram bot test

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | DEPLOY-01, DEPLOY-02 | T-DB-Tampering | Constraint violations rejected at DB level | integration (manual) | `python scripts/verify_migrations.py` | ❌ Wave 0 | ⬜ pending |
| 03-02-01 | 02 | 1 | DEPLOY-04 | — | Modulations applied only on fresh Garmin data | unit | `pytest tests/test_audit_resilience.py::test_k1_accepted_modulation_gets_applied -xvs` | ✅ | ⬜ pending |
| 03-03-01 | 03 | 2 | DEPLOY-03 | T-Spoofing | K4: malformed JSON returns 200 not 500 | manual smoke | Telegram chat test (send accept callback, check resp.ok guard) | N/A | ⬜ pending |
| 03-04-01 | 04 | 2 | PIPELINE-01 | — | Exit 1 propagates on Garmin failure | manual (log inspection) | Trigger failed ingest run, inspect Actions log | N/A | ⬜ pending |
| 03-05-01 | 05 | 2 | PIPELINE-02 | — | Watchdog alerts on missing health row | unit | `pytest tests/test_audit_resilience.py::test_l4_watchdog_alerts_missing_component -xvs` | ✅ | ⬜ pending |
| 03-05-02 | 05 | 2 | PIPELINE-03 | T-Tampering | DR aborts on empty critical table | unit | `pytest tests/test_audit_resilience.py::test_l3_empty_snapshot_aborts -xvs` | ✅ | ⬜ pending |
| 03-06-01 | 06 | 3 | PIPELINE-04 | — | Brief not sent twice same day | unit + manual | `pytest tests/test_audit_resilience.py -k brief -xvs` + log inspection | ✅ (partial) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `scripts/verify_migrations.py` — covers DEPLOY-01, DEPLOY-02 (create in Wave 1 Task 1 before running manual migration)
- [ ] Explicit `test_brief_idempotency` unit test in `tests/test_audit_resilience.py` — explicit coverage for `_brief_already_sent_today()` (PIPELINE-04)
