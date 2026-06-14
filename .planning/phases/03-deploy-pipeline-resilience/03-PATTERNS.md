# Phase 3: Deploy & Pipeline Resilience - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 3 (1 new, 2 modified)
**Analogs found:** 3 / 3

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `scripts/verify_migrations.py` | utility/script | request-response (DB read) | `scripts/db_cleanup.py` | role-match |
| `.github/workflows/ingest.yml` | config | batch (pipeline step) | self (existing file, line edit) | exact |
| `coach/planning/briefing.py` | service | request-response | self (already implemented — verify only) | exact |

> **Key finding from RESEARCH.md:** All code fixes are already committed. The only genuinely
> new file is `scripts/verify_migrations.py`. The `ingest.yml` change (remove `if: always()`)
> is a one-line edit. `briefing.py` idempotency is already implemented and needs no change.

---

## Pattern Assignments

### `scripts/verify_migrations.py` (utility, request-response)

**Analog:** `scripts/db_cleanup.py`

**Imports pattern** (`db_cleanup.py` lines 1-6):
```python
import logging
import sys
from datetime import datetime, timedelta, timezone
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)
```

**Core pattern — main() structure** (`db_cleanup.py` lines 8-32):
```python
def main():
    logging.basicConfig(level=logging.INFO)
    sb = get_supabase()

    try:
        # ... perform work ...
        logger.info("Cleaned up old bot_messages. Count: %s", ...)
    except Exception:
        logger.exception("Failed during DB cleanup")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Logging format with structured status** (`scripts/watchdog.py` lines 56-57):
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
```

**Module-level docstring style** (`scripts/dr_snapshot.py` lines 1-8):
```python
"""Snapshot DB cifrato → Supabase Storage bucket dr-snapshots.

Esporta tutte le tabelle in JSON, cifra con AES-256-GCM, upload con timestamp.
...
"""
from __future__ import annotations
```

**verify_migrations.py specific core pattern** (from RESEARCH.md code examples):
```python
# information_schema access — primary approach
res = (
    sb.schema("information_schema")
    .table("table_constraints")
    .select("constraint_name,table_name,constraint_type")
    .eq("table_schema", "public")
    .execute()
)
constraints = {row["constraint_name"] for row in (res.data or [])}
```

**Exit code contract** (mirrors `db_cleanup.py` lines 24-29 and RESEARCH.md pattern):
```python
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    failures = []
    # ... run checks, append to failures on miss ...
    for name, ok in results:
        if not ok:
            failures.append(name)
            logger.error("FAIL: %s", name)
        else:
            logger.info("PASS: %s", name)
    if failures:
        logger.error("%d constraint(s) missing — migrations may not be applied", len(failures))
        sys.exit(1)
    logger.info("All %d constraints verified OK", len(results))
```

**Column existence check** (RESEARCH.md pattern):
```python
res = (
    sb.schema("information_schema")
    .table("columns")
    .select("column_name")
    .eq("table_schema", "public")
    .eq("table_name", "plan_modulations")
    .eq("column_name", "expires_at")
    .execute()
)
exists = bool(res.data)
```

**Fallback if `sb.schema("information_schema")` is unavailable (Pitfall 4):**
```python
try:
    res = sb.schema("information_schema").table("table_constraints") ...
except Exception:
    # Fallback: call a SECURITY DEFINER RPC created in Supabase SQL Editor
    res = sb.rpc("get_public_constraints").execute()
    constraints = {row["constraint_name"] for row in (res.data or [])}
```

**Constraints to verify** (from migration file `migrations/2026-06-01-resilience-audit.sql`):
```python
EXPECTED_UNIQUE_CONSTRAINTS = [
    ("races", "races_name_date_unique"),
    ("physiology_zones", "physiology_zones_disc_validfrom_method_unique"),
    ("planned_sessions", "unique_planned_date_sport_type"),
]
EXPECTED_FK_CONSTRAINTS = [
    ("mesocycles", "mesocycles_target_race_fk"),
    ("planned_sessions", "planned_sessions_completed_activity_id_fkey"),
    ("physiology_zones", "physiology_zones_test_activity_id_fkey"),
]
EXPECTED_CHECK_CONSTRAINTS = [
    ("plan_modulations", "plan_modulations_status_check"),
    ("subjective_log", "subjective_log_kind_check"),
]
EXPECTED_COLUMNS = [
    ("plan_modulations", "expires_at"),
]
```

---

### `.github/workflows/ingest.yml` (config, batch pipeline)

**Analog:** self (existing file — one-line edit at line 98)

**Current state that must change** (`ingest.yml` lines 95-100):
```yaml
- name: Apply accepted modulations (audit K1)
  if: always()           # <-- BUG vs D-06: runs even when Garmin sync failed
  continue-on-error: true
  run: python -m coach.coaching.modulation --apply-accepted
```

**Target state per D-06** (remove `if: always()` to default to `if: success()`):
```yaml
- name: Apply accepted modulations (audit K1)
  continue-on-error: true   # failure doesn't block ingest
  run: python -m coach.coaching.modulation --apply-accepted
```

**Pattern reference for other steps with same structure** (`ingest.yml` lines 85-93):
```yaml
- name: Pre-test prediction (Phase 2.6)
  if: success()
  continue-on-error: true
  run: python -m coach.coaching.test_prediction
  env:
    TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

---

### `coach/planning/briefing.py` — idempotency (already implemented, verify only)

**No code changes needed.** Implementation already present.

**Idempotency function** (`coach/planning/briefing.py` lines 679-695):
```python
def _brief_already_sent_today(sb, *, window_hours: int = 6) -> bool:
    """Idempotenza: True se un morning_brief è stato inviato negli ultimi N ore."""
    from datetime import timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    try:
        res = (
            sb.table("bot_messages")
            .select("id,sent_at")
            .eq("purpose", "morning_brief")
            .gte("sent_at", cutoff)
            .limit(1)
            .execute()
        )
        return bool(res.data)
```

**Guard in main()** (`coach/planning/briefing.py` lines 706-713):
```python
force_send = os.environ.get("FORCE_SEND", "").lower() in ("true", "1", "yes")
if not force_send:
    sb = get_supabase()
    if _brief_already_sent_today(sb):
        logger.info("Morning brief already sent in last 6h — skipping duplicate run")
        return
```

---

## Shared Patterns

### Supabase client acquisition
**Source:** `scripts/db_cleanup.py` line 4, `scripts/watchdog.py` line 11
**Apply to:** `scripts/verify_migrations.py`
```python
from coach.utils.supabase_client import get_supabase
sb = get_supabase()
```

### Error handling — re-raise with exit(1)
**Source:** `scripts/db_cleanup.py` lines 24-29
**Apply to:** `scripts/verify_migrations.py`
```python
except Exception:
    logger.exception("Failed during <operation>")
    sys.exit(1)
```

### Health recording after script completion
**Source:** `scripts/dr_snapshot.py` lines 108, 112
**Apply to:** `scripts/verify_migrations.py` (optional — adds visibility in health table)
```python
from coach.utils.health import record_health
record_health("verify_migrations", success=True, metadata={...})
# or on failure:
record_health("verify_migrations", success=False, error=str(e))
```

### Logging initialization
**Source:** `scripts/watchdog.py` line 56, `scripts/dr_snapshot.py` line 81
**Apply to:** `scripts/verify_migrations.py` — use the format with timestamp:
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
```

---

## No Analog Found

None. All files have close analogs or are self-referential edits.

---

## Metadata

**Analog search scope:** `scripts/`, `coach/planning/`, `.github/workflows/`
**Files scanned:** 5 (db_cleanup.py, watchdog.py, dr_snapshot.py, briefing.py, ingest.yml)
**Pattern extraction date:** 2026-06-06

**Implementation notes for planner:**
- `scripts/verify_migrations.py` is the only file to CREATE — all others are edits or verifications
- `ingest.yml` requires exactly one line deletion (remove `if: always()` at line 98)
- `briefing.py` requires zero code changes — planner should include a verification task only
- The `sb.schema("information_schema")` approach is marked [ASSUMED] in RESEARCH.md — include try/except fallback
