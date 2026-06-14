---
phase: 5
slug: workout-prescription-quality
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-07
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4 |
| **Config file** | `pytest.ini` (`testpaths = tests`) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green + `scripts/verify_prescription_quality.py` read-only check
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| 05-?-01 | migration | 0 | WORKOUT-03 | active_constraints accesso solo via service_role | integration | `pytest tests/test_active_constraints.py -v` | ❌ Wave 0 | ⬜ pending |
| 05-?-02 | MCP extension | 0 | WORKOUT-03 | update_constraint valida UUID prima query | integration | `pytest tests/test_active_constraints.py -v` | ❌ Wave 0 | ⬜ pending |
| 05-?-03 | propose_session.md | 1 | WORKOUT-01, WORKOUT-02 | N/A — skill prompt | manual | Verifica output Claude.ai: warmup/main/cooldown presenti + zone numeriche | N/A | ⬜ pending |
| 05-?-04 | generate_mesocycle.md | 1 | WORKOUT-04, WORKOUT-05 | N/A — skill prompt | manual | Verifica output Claude.ai: TSS documentato + 80/20 mix | N/A | ⬜ pending |
| 05-?-05 | fitness_test.md | 1 | WORKOUT-02 | N/A — skill prompt | manual | Verifica: FTP null o >42gg → coach propone test | N/A | ⬜ pending |
| 05-?-06 | verify script | 2 | WORKOUT-03 | N/A — read-only script | integration | `python scripts/verify_prescription_quality.py` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_active_constraints.py` — stubs per WORKOUT-03: verifica tabella esiste con 2 seed rows, `get_weekly_context` include `active_constraints`
- [ ] `migrations/2026-06-07-workout-prescription-quality.sql` — deve esistere prima di ogni altro task (Wave 0)
- [ ] `scripts/verify_prescription_quality.py` — script read-only phase gate: WORKOUT-03 automatico + checklist manuale WORKOUT-01/02/04/05

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sessione con warmup/main/cooldown strutturati | WORKOUT-01 | Output LLM — dipende da skill prompt | Proponi sessione in Claude.ai; verifica che output contenga tutte e 3 le sezioni con durata e intensità specifica |
| Zone da physiology_zones — nessun hard-code | WORKOUT-02 | Output LLM — dipende da lettura MCP tool | Cambia FTP in DB e richiedi prescrizione; verifica che watt cambino coerentemente |
| TSS documentato e coerente col mesociclo | WORKOUT-04 | Output LLM — dipende da get_weekly_context | Verifica che sezione "Contesto mesociclo" mostri TSS accumulato vs target e che il TSS sessione sia coerente |
| 80/20 distribuzione Z1-Z2 | WORKOUT-05 | Output LLM — dipende da generate_mesocycle | Genera piano settimanale; conta sessioni Z1-Z2 vs Z4-Z5; Z4-Z5 non consecutivi |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
