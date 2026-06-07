---
phase: 03-deploy-pipeline-resilience
fixed_at: 2026-06-07T00:00:00Z
review_path: .planning/phases/03-deploy-pipeline-resilience/03-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-06-07
**Source review:** `.planning/phases/03-deploy-pipeline-resilience/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (CR-01, WR-01, WR-02, WR-03)
- Fixed: 4
- Skipped: 0

---

## Fixed Issues

### CR-01: verify_migrations.py — verifica constraint per nome senza validare la tabella

**Files modified:** `scripts/verify_migrations.py`
**Commit:** `609963d`
**Applied fix:**
`_fetch_constraints` ora restituisce `set[tuple[str, str]]` di coppie `(table_name, constraint_name)` invece di un flat set di soli nomi. Entrambi i path (primario `information_schema` e fallback RPC) usano la tuple comprehension `{(row["table_name"], row["constraint_name"]) ...}`. Tutti i call site in `main()` sono stati aggiornati: le variabili `_table` rinominate in `table`, la label cambiata in `f"{table}.{name}"`, il check aggiornato a `(table, name) in live_constraints`. Il fix copre UNIQUE, FK e CHECK constraints.

**Note:** CR-01 e WR-03 sono stati committati insieme nello stesso commit atomico perché entrambi modificano `scripts/verify_migrations.py` e il fix WR-03 (`from supabase import Client` + annotazioni `sb: Client`) è prerequisito per il return type `set[tuple[str, str]]` di CR-01.

---

### WR-01: ingest.yml — "Compute daily metrics" gira con dati stantii quando Garmin sync fallisce

**Files modified:** `.github/workflows/ingest.yml`
**Commit:** `face9ae`
**Applied fix:**
Rimossa la riga `if: always()` dallo step "Compute daily metrics" (riga 71). Lo step eredita ora il comportamento predefinito `success()` di GitHub Actions e non viene eseguito se Garmin sync fallisce dopo 3 tentativi. Gli altri step con `if: always()` intenzionali (`ETL health check` a riga 103) non sono stati toccati.

---

### WR-02: tests/test_audit_resilience.py — test idempotency PIPELINE-04 non verifica la finestra temporale

**Files modified:** `tests/test_audit_resilience.py`
**Commit:** `18383c3`
**Applied fix:**
Due modifiche nel file di test:

1. `_IdempotencyFakeQuery.gte(self, field: str, value: str)` ora filtra davvero `self._rows` mantenendo solo le righe con `row.get(field, "") >= value` (confronto lessicografico ISO 8601 UTC). Prima il metodo ignorava i propri argomenti e restituiva `self` incondizionatamente.

2. Aggiunto `test_pipeline04_brief_idempotency_old_brief_does_not_block()`: inietta una riga con `sent_at` = 8h prima di un `frozen_now` fisso (`2026-06-07T09:00:00Z`), patcha `coach.planning.briefing.datetime` con `unittest.mock.patch` per congelare il `now`, e verifica che `_brief_already_sent_today` restituisca `False` — confermando che la finestra di 6h è rispettata in entrambe le direzioni.

---

### WR-03: scripts/verify_migrations.py — funzioni `_fetch_constraints` / `_fetch_columns` prive di type annotation su `sb`

**Files modified:** `scripts/verify_migrations.py`
**Commit:** `609963d` (stesso commit di CR-01 — stesso file)
**Applied fix:**
Aggiunto `from supabase import Client` agli import. Le firme delle due helper private aggiornate:
- `def _fetch_constraints(sb: Client) -> set[tuple[str, str]]:`
- `def _fetch_columns(sb: Client) -> set[tuple[str, str]]:`

Il return type `set[tuple[str, str]]` (coerente con CR-01) è più preciso rispetto al precedente `set` non tipizzato, allineando entrambe le annotazioni alle convenzioni CLAUDE.md.

---

_Fixed: 2026-06-07_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
