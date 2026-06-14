# Phase 6: Physiological Adaptation Intelligence - Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 6 new/modified files + 1 migration + 2 test files
**Analogs found:** 8 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `coach/analytics/readiness.py` (extend) | analytics utility | transform | `coach/analytics/readiness.py` itself | exact (self-extension) |
| `coach/coaching/post_session_analysis.py` (extend) | service | request-response | `coach/coaching/post_session_analysis.py` itself | exact (self-extension) |
| `coach/coaching/pattern_extraction.py` (extend) | service | batch | `coach/coaching/pattern_extraction.py` itself | exact (self-extension) |
| `workers/mcp-server/src/index.ts` (extend) | controller | request-response | `workers/mcp-server/src/index.ts` `getWeeklyContext()` | exact (self-extension) |
| `skills/propose_session.md` (extend) | config/prompt | — | `skills/propose_session.md` itself | exact (self-extension) |
| `migrations/2026-06-08-physiological-adaptation.sql` | migration | batch | `migrations/2026-06-07-workout-prescription-quality.sql` | exact |
| `tests/test_fatigue_classification.py` | test | — | `tests/test_readiness.py` | exact |
| `tests/test_physio_adaptation.py` | test | — | `tests/test_active_constraints.py` (inferred) | role-match |

---

## Pattern Assignments

### `coach/analytics/readiness.py` — add `FatigueResult` + `classify_fatigue_type()`

**Analog:** `coach/analytics/readiness.py` (existing file, self-extension)

**Imports pattern** (lines 1-17):
```python
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
```

**Dataclass output pattern** (lines 27-64, `ReadinessReport` as model):
```python
@dataclass
class ReadinessReport:
    score: int                       # 0-100
    label: str                       # ready / caution / rest
    factors: dict[str, int]          # contributo per fattore
    flags: list[str]
    rationale: str                   # spiegazione human-readable per brief
```
New `FatigueResult` follows identical `@dataclass` convention. Add after line 64:
```python
@dataclass
class FatigueResult:
    failure_type: Optional[str]   # 'muscular' | 'cardiovascular' | 'mixed' | None
    confidence: float             # 0.0–1.0
    signal_used: str              # 'hr_drift+pace' | 'rpe_only' | 'insufficient'
    notes: Optional[str] = None
```

**Section divider pattern** (line 66):
```python
# ============================================================================
# HRV z-score
# ============================================================================
```
Each new logical block (HR drift helpers, classify_fatigue_type) gets its own `# ===` divider section.

**Deterministic helper pattern** (lines 69-80 `hrv_z_score`):
```python
def hrv_z_score(hrv_today: float, history: list[float]) -> Optional[float]:
    if len(history) < 7 or hrv_today is None:
        return None
    mean = statistics.fmean(history)
    sd = statistics.pstdev(history) if len(history) > 1 else 0.0
    if sd == 0:
        return 0.0
    return (hrv_today - mean) / sd
```
Private helpers `_compute_hr_drift()` and `_compute_pace_drop()` follow this same pattern: typed signature, guard clause returning `None` on insufficient data, `statistics.fmean()` for averages.

**Early-return guard pattern** (line 99, `compute_flags`):
```python
if z <= HRV_CRITICAL_Z:
    flags.append("fatigue_critical")
elif z <= HRV_WARNING_Z:
    ...
```
`classify_fatigue_type()` mirrors this: guard on `duration_s < 1800` → return immediately with `failure_type=None`, then guard on missing splits → fallback.

---

### `coach/coaching/post_session_analysis.py` — inject `classify_fatigue_type()` before Gemini call

**Analog:** `coach/coaching/post_session_analysis.py` (self-extension)

**Injection point** — after `zone_compliance` computation (line 150) and before `context_parts` assembly (line 153). Insert:
```python
# ADAPT-01: classificazione deterministica cedimento (zero LLM)
from coach.analytics.readiness import classify_fatigue_type
splits = activity.get("splits") or None
debrief_rpe = next((int(d["rpe"]) for d in debrief if d.get("rpe") is not None), None)
fatigue_result = classify_fatigue_type(activity, splits, debrief_rpe)
```

**DB record pattern** (lines 203-210 — current record dict):
```python
record = {
    "activity_id": activity_id,
    "analysis_text": analysis_text,
    "suggested_actions": actions,
    "model_used": result.get("model"),
    "cost_usd": result.get("cost_usd"),
}
sb.table("session_analyses").insert(record).execute()
```
Extend with two new keys (aligned with migration D-04):
```python
record = {
    "activity_id": activity_id,
    "analysis_text": analysis_text,
    "fatigue_type": fatigue_result.failure_type or "insufficient_data",
    "fatigue_confidence": fatigue_result.confidence,
    "sport": sport,   # add sport column per Pitfall 2 fix (Open Question 2)
    "suggested_actions": actions,
    "model_used": result.get("model"),
    "cost_usd": result.get("cost_usd"),
}
```

**Error guard pattern** (lines 185-195):
```python
except BudgetExceededError:
    logger.warning("Budget exceeded, skipping session analysis for %s", activity_id)
    return None
except Exception:
    logger.exception("LLM call failed for session analysis %s", activity_id)
    return None
```
The fatigue classification runs BEFORE this try/except block and never raises — it returns a `FatigueResult` with `failure_type=None` and low confidence on any failure path.

---

### `coach/coaching/pattern_extraction.py` — add `update_beliefs_from_session_patterns()`

**Analog:** `coach/coaching/pattern_extraction.py` (self-extension, specifically `extract_biometric_patterns()` as direct model)

**Imports already present** (lines 1-25) — reuse all; no new imports needed.

**Rule-based section pattern** (lines 46-49):
```python
# ============================================================================
# Blocco 3.1 — Biometric pattern extraction (rule-based, zero LLM cost)
# ============================================================================

def extract_biometric_patterns(days: int = 28) -> dict:
```
New function follows same structure:
```python
# ============================================================================
# ADAPT-03 — Belief update from session patterns (rule-based, zero LLM cost)
# ============================================================================

def update_beliefs_from_session_patterns(days: int = 14) -> dict:
    """Legge session_analyses ultimi N giorni, raggruppa per session_type,
    chiama reinforce/contradict belief. Zero LLM.

    Returns: {'updated': int, 'created': int, 'skipped': int, 'errors': int}
    """
```

**Supabase fetch pattern** (lines 64-78):
```python
sb = get_supabase()
today = today_rome()
since = (today - timedelta(days=days)).isoformat()

activities = sb.table("activities").select(
    "started_at,sport,tss,duration_s,avg_hr,max_hr"
).gte("started_at", since).order("started_at").execute().data or []
```

**groupby + statistics pattern** (lines 82-94):
```python
rpe_by_sport: dict[str, list[int]] = defaultdict(list)
for d in debrief:
    if d.get("rpe") is not None:
        rpe_by_sport[sport].append(int(d["rpe"]))

if rpe_by_sport:
    for sport, rpes in rpe_by_sport.items():
        avg = statistics.fmean(rpes)
```
New function uses same `defaultdict(list)`, grouping by `session_type` instead of sport.

**Guard for empty groups** (lines 130-138 pattern in biometric function):
```python
if len(sleep_perf_pairs) >= 7:
    high_sleep = [...]
    if high_sleep and low_sleep:
        patterns["sleep_tss_correlation"] = {...}
```
New function: `if not session_type: continue` (guard against null session_type from unplanned activities — Pitfall 4).

**Call site** — add at end of `extract_patterns()` (line 196), after biometric extraction and before LLM call:
```python
biometric = extract_biometric_patterns(days)
belief_update_result = update_beliefs_from_session_patterns(days=14)
logger.info("Belief update: %s", belief_update_result)
```

**BudgetExceededError guard** (lines 261-266): the new deterministic function never touches LLM, so it runs even inside the `except BudgetExceededError` fallback path — call it unconditionally before the try block.

**Belief engine API** — import at top of function (not at module level, matching pattern in `post_session_analysis.py` lines 218-222 lazy import):
```python
from coach.analytics.belief_engine import reinforce_belief, contradict_belief, create_belief, list_beliefs
```

---

### `workers/mcp-server/src/index.ts` — extend `getWeeklyContext()`

**Analog:** `workers/mcp-server/src/index.ts` `getWeeklyContext()` lines 613-664

**Promise.all pattern** (lines 622-636):
```typescript
const [health, metrics, wellness, ..., constraints] =
  await Promise.all([
    getHealth(env),
    sb(env, `daily_metrics?date=gte.${metricsSince}&...`),
    ...
    sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`).catch(() => []),
  ]);
```
Add two new entries to the destructuring array and the `Promise.all()` call:
```typescript
const [health, metrics, ..., constraints, beliefs, fatigueBySport] =
  await Promise.all([
    ...existing12queries...,
    sb(env, `beliefs?status=neq.retired&confidence=gte.0.55&order=confidence.desc&select=belief_key,belief_text,status,confidence`).catch(() => []),
    getLastFatigueBySport(env, since),
  ]);
```

**Return object extension** (lines 638-663):
```typescript
return {
  ...existingFields,
  active_constraints: constraints || [],
  active_beliefs: (beliefs || []),
  last_fatigue_by_sport: fatigueBySport,
  current_progression_step: ...,
};
```

**Helper function pattern** — model after existing `async function getHealth(env: Env)` (line 752) and `async function getRaceContext(...)` (line 666). New helper:
```typescript
async function getLastFatigueBySport(env: Env, since: string): Promise<Record<string, any>> {
  const sports = ["run", "swim", "bike"];
  const result: Record<string, any> = { run: null, swim: null, bike: null };
  for (const sport of sports) {
    const rows = await sb(env,
      `session_analyses?sport=eq.${sport}&fatigue_type=not.is.null&order=created_at.desc&limit=1&select=fatigue_type,fatigue_confidence,created_at`
    ).catch(() => []);
    if (rows?.[0]) {
      result[sport] = {
        type: rows[0].fatigue_type,
        confidence: rows[0].fatigue_confidence,
        date: rows[0].created_at?.split("T")[0],
      };
    }
  }
  return result;
}
```
Note: this relies on the `sport` column being added to `session_analyses` in the migration (Open Question 2 resolution — avoids the problematic JOIN).

**`sb()` helper** — already present in the worker. No new fetch utility needed.

---

### `skills/propose_session.md` — extend Step 2 with `active_beliefs` reading

**Analog:** `skills/propose_session.md` Step 2 (lines 28-33)

**Current Step 2** (lines 28-33):
```markdown
### Step 2 — Contesto settimanale + vincoli medici
Chiama `get_weekly_context()`. Estrai:
- `active_constraints` (solo resolved_at IS NULL): **QUESTI SOSTITUISCONO i vincoli hardcoded in CLAUDE.md**. La fonte di verità è il DB — non prescrivere sessioni in contrasto con nessun vincolo attivo.
- `active_mesocycle` + `current_progression_step`: passo corrente della progressione qualità.
- `daily_metrics`: TSB, HRV z-score, readiness score.
- `daily_wellness`: sleep score, temperatura prevista (weather).
```
Extend by adding after `active_constraints` bullet (per Pitfall 6 — no second tool call):
```markdown
- `active_beliefs` (confidence >= 0.55): leggi i beliefs fisiologici attivi. Per ogni belief rilevante alla disciplina del giorno, applica inline con tag `[athlete-belief: <belief_key>] — <motivazione specifica>`. Il tag appare nella riga del main set o del razionale dove il belief ha influenzato la scelta (non in sezione separata).
- `last_fatigue_by_sport`: fatica dell'ultima sessione per la disciplina. Se `type == 'muscular'` e `confidence >= 0.6`: verifica che il main set non superi la soglia neuromuscolare (referenza belief `endurance_failure_type`).
```

**Citation tag pattern** — already present in `propose_session.md` lines 131-133:
```markdown
Quando applichi una belief: `[athlete-belief: <descrizione>]`.
```
The tag format is already defined in the skill. Phase 6 only makes its application mandatory when `active_beliefs` contains relevant entries.

---

### `migrations/2026-06-08-physiological-adaptation.sql` (new file)

**Analog:** `migrations/2026-06-07-workout-prescription-quality.sql` (exact pattern)

**Header comment pattern** (lines 1-9):
```sql
-- Migration: Workout Prescription Quality 2026-06-07
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   Phase 5 — ...
```

**ALTER TABLE IF NOT EXISTS pattern** (line 38-39):
```sql
ALTER TABLE mesocycles
    ADD COLUMN IF NOT EXISTS progression_plan JSONB;
```

**INSERT with WHERE NOT EXISTS guard** (lines 53-60):
```sql
INSERT INTO active_constraints (type, discipline, description, severity)
SELECT 'injury', 'swim', '...', 'high'
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints
    WHERE type = 'injury' AND discipline = 'swim' AND resolved_at IS NULL
);
```

**New migration uses ON CONFLICT pattern** for belief seed (per Pitfall 5):
```sql
-- ADAPT-01: nuove colonne session_analyses
ALTER TABLE session_analyses
    ADD COLUMN IF NOT EXISTS fatigue_type TEXT CHECK (
        fatigue_type IN ('muscular', 'cardiovascular', 'mixed', 'insufficient_data')
    ),
    ADD COLUMN IF NOT EXISTS fatigue_confidence FLOAT CHECK (
        fatigue_confidence IS NULL OR (fatigue_confidence >= 0 AND fatigue_confidence <= 1)
    ),
    ADD COLUMN IF NOT EXISTS sport TEXT;   -- per last_fatigue_by_sport query (Open Q2)

-- ADAPT-02: seed belief "endurance puro, cedimento muscolare first"
-- beliefs schema from migrations/2026-05-14-cognitive-mvp.sql:
--   belief_key (UNIQUE), belief_text, confidence, evidence_n, status,
--   source, source_metadata JSONB, last_reinforced_at, first_observed_at
INSERT INTO beliefs (
    belief_key, belief_text, confidence, evidence_n, status,
    source, source_metadata, last_reinforced_at, first_observed_at
)
VALUES (
    'endurance_failure_type',
    'Nicolò è atleta endurance puro: primo cedimento muscolare, non cardiovascolare. HR rimane stabile anche ad alta intensità; il cedimento è al tono muscolare.',
    0.75, 8, 'validated_belief',
    'manual_seed',
    '{"evidence_note": "Basato su CLAUDE.md §2: profilo atleta, confermato da storico élite 2021-2022 (114 sessioni)"}',
    NOW(), NOW()
) ON CONFLICT (belief_key) DO NOTHING;
```

---

### `tests/test_fatigue_classification.py` (new file)

**Analog:** `tests/test_readiness.py` (exact pattern)

**Import pattern** (lines 1-9 of test_readiness.py):
```python
from coach.analytics.readiness import (
    SubjectiveState, TrainingState, WellnessHistory,
    compute_flags, compute_readiness, hrv_z_score,
)
```
New file imports:
```python
from coach.analytics.readiness import classify_fatigue_type
```

**Factory helper pattern** (lines 12-15):
```python
def make_default_subj(**kw) -> SubjectiveState:
    base = dict(motivation=7, soreness=2, illness_flag=False, injury_flag=False, illness_recent_days=0)
    base.update(kw)
    return SubjectiveState(**base)
```
New file uses analogous `make_splits_run(hr_first, hr_second, pace_first, pace_second, n=5)` factory.

**Assert pattern** (lines 18-60):
```python
def test_hrv_z_score_returns_none_with_short_history():
    assert hrv_z_score(50.0, [50.0, 51.0]) is None

def test_compute_flags_critical_hrv():
    ...
    flags = compute_flags(wellness, training, subj)
    assert "fatigue_critical" in flags
```

---

### `tests/test_physio_adaptation.py` (new file)

**Analog:** Static text inspection tests (pattern inferred from RESEARCH.md §Validation Architecture).

**Pattern:** Read the migration file and skill file as text strings, then assert on expected substrings — no DB connection required. Follow same `assert "..." in content` pattern used for static checks in other test files.

```python
from pathlib import Path

MIGRATION = Path("migrations/2026-06-08-physiological-adaptation.sql").read_text()
SKILL = Path("skills/propose_session.md").read_text()

def test_migration_session_analyses_columns():
    assert "fatigue_type" in MIGRATION
    assert "fatigue_confidence" in MIGRATION
    assert "IF NOT EXISTS" in MIGRATION

def test_migration_belief_seed_idempotent():
    assert "ON CONFLICT (belief_key) DO NOTHING" in MIGRATION
    assert "endurance_failure_type" in MIGRATION

def test_skill_active_beliefs_step():
    assert "active_beliefs" in SKILL
    assert "[athlete-belief:" in SKILL
```

---

## Shared Patterns

### Supabase client singleton
**Source:** `coach/utils/supabase_client.py` (used in all Python files)
**Apply to:** `classify_fatigue_type()` does NOT call Supabase — pure function. `update_beliefs_from_session_patterns()` uses it.
```python
from coach.utils.supabase_client import get_supabase
sb = get_supabase()
```

### Deterministic analytics — zero LLM rule
**Source:** `coach/analytics/readiness.py` module docstring lines 1-10
**Apply to:** `classify_fatigue_type()`, `update_beliefs_from_session_patterns()`
- No `from coach.utils.llm_client import ...` anywhere in these functions
- Output is always a typed dataclass or dict, never a string to be parsed
- Fallback: return low-confidence result, never raise

### `statistics.fmean()` for averages
**Source:** `coach/analytics/readiness.py` line 77; `coach/coaching/pattern_extraction.py` line 93
**Apply to:** HR drift calculation (`_compute_hr_drift`), pace drop calculation (`_compute_pace_drop`), RPE averaging in belief update job

### `today_rome()` for date computations
**Source:** `coach/coaching/pattern_extraction.py` line 21, 29
**Apply to:** `update_beliefs_from_session_patterns()` — use `today_rome()` for `since` computation, not `date.today()`

### BudgetExceededError guard
**Source:** `coach/coaching/post_session_analysis.py` lines 185-195; `coach/coaching/pattern_extraction.py` lines 261-266
**Apply to:** LLM-calling paths only. `classify_fatigue_type()` and `update_beliefs_from_session_patterns()` are zero-LLM and must not be gated behind this guard.

### Lazy import of coaching modules
**Source:** `coach/coaching/post_session_analysis.py` lines 218-222
```python
from coach.coaching.modulation import (
    should_trigger_modulation, propose_modulation, generate_modulation_proposal,
)
```
**Apply to:** `from coach.analytics.belief_engine import ...` inside `update_beliefs_from_session_patterns()` body, not at module top level.

### TypeScript `sb()` helper + `.catch(() => [])` pattern
**Source:** `workers/mcp-server/src/index.ts` line 635
```typescript
sb(env, `active_constraints?resolved_at=is.null&order=created_at.asc`).catch(() => []),
```
**Apply to:** Both new queries in `getWeeklyContext()` Promise.all — `beliefs` query and `getLastFatigueBySport()` internal queries all use `.catch(() => [])` to degrade gracefully.

---

## No Analog Found

All files have analogs. No entirely new architectural patterns are introduced.

| File | Note |
|------|------|
| `tests/test_physio_adaptation.py` | Static file-inspection tests — pattern inferred from RESEARCH.md, no existing example of this exact pattern in `tests/` found, but structure is trivial (`read_text` + `assert ... in content`) |

---

## Metadata

**Analog search scope:** `coach/analytics/`, `coach/coaching/`, `workers/mcp-server/src/`, `skills/`, `migrations/`, `tests/`
**Files scanned:** 8 files read directly
**Pattern extraction date:** 2026-06-08
