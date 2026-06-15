# Phase 6: Physiological Adaptation Intelligence - Research

**Researched:** 2026-06-08
**Domain:** Sports physiology analytics, Bayesian belief engine, MCP Worker extension, skill prompt engineering
**Confidence:** HIGH (all findings grounded in existing codebase inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Classificazione muscolare vs cardiovascolare in Python analytics deterministico (`coach/analytics/`) — zero LLM, testabile in pytest.

**D-02:** Output funzione: `{'failure_type': 'muscular'|'cardiovascular'|'mixed'|None, 'confidence': float}`. `None` quando dati insufficienti (sessione < 30min, splits mancanti).

**D-03:** Soglie discipline-specifiche:
- Cardiovascular signal: HR drift >10bpm nel secondo 50% della sessione
- Muscular signal: HR stabile + RPE ≥8 + pace/power drop > 5%
- Corsa: pace degradation per km da `splits`; bici: power vs HR curve; nuoto: pace vs HR ultimi 2×100m
- Fallback (no splits): solo RPE con `confidence = 0.4`

**D-04:** `session_analyses` — due nuove colonne: `fatigue_type TEXT CHECK (IN ('muscular', 'cardiovascular', 'mixed', 'insufficient_data'))` + `fatigue_confidence FLOAT`. Migration necessaria.

**D-05:** `get_weekly_context` espone `last_fatigue_by_sport`: oggetto per disciplina con `{type, confidence, date}` o `null`.

**D-06:** Belief seedato via migration/script: `key='endurance_failure_type'`, `value='muscular-first'`, `n=8`, `confidence=0.75`, `status='validated_belief'`.

**D-07:** Solo il belief ADAPT-02 viene seedato — gli altri emergono dall'evidenza.

**D-08:** Il belief seedato viene aggiornato da `reinforce_belief` / `contradict_belief` come ogni altro — non è immutabile.

**D-09:** `get_weekly_context` esteso con:
1. `active_beliefs`: beliefs con `confidence >= 0.55`, formato `[{key, value, status, confidence}]`
2. `last_fatigue_by_sport`: per disciplina

**D-10:** `propose_session.md` aggiunge step lettura `active_beliefs` da `get_weekly_context` e cita beliefs pertinenti con tag `[athlete-belief: key]`.

**D-11:** Tag format: `[athlete-belief: endurance-failure-muscular-first] — [motivazione specifica]`. Inline nel testo prescrizione, non in sezione separata.

**D-12:** Job settimanale: estensione di `pattern_extraction.py`, legge `session_analyses` ultimi 14gg, raggruppa per `session_type` via JOIN con `planned_sessions`, se n≥3 sessioni calcola pattern.

**D-13:** Job deterministico (zero LLM): `avg_rpe`, `avg_hr_drift`, tendenza `fatigue_type` → `reinforce_belief()` se positivo (RPE ≤ 7.5, no degradazione) o `contradict_belief()` se negativo.

**D-14:** Naming convention beliefs generati dal job: `responds_well_{session_type}` o `struggles_with_{session_type}`.

**D-15:** Quando belief `responds_well_*` raggiunge `validated_belief` (n≥8, conf>0.7), job aggiorna `mesocycles.progression_plan` incrementando il passo per quella tipologia.

### Claude's Discretion

- Soglia esatta per pace degradation su bici (5% o 8% power drop)
- Quante settimane storico nel job beliefs (14gg default — può scendere a 10 se pochi dati)
- Formato esatto `evidence_note` per beliefs generati dal job
- Naming convention esatta beliefs di risposta (prefisso `responds_well_` vs `adapts_to_`)

### Deferred Ideas (OUT OF SCOPE)

- Qualità LLM analisi post-sessione → Phase 9
- Brief mattutino con beliefs → Phase 8
- Weekly review narrativa con beliefs → Phase 10
- Belief decay automatico su infortuni → Phase 7 o Phase 10
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADAPT-01 | Il sistema distingue cedimento muscolare da cardiovascolare dai dati Garmin (HR drift, decoupling aerobico, RPE vs pace) — distinzione usata nelle prescrizioni e nell'analisi post-sessione | `classify_fatigue_type()` in `coach/analytics/readiness.py` (estensione), output scritto in `session_analyses.fatigue_type`, esposto via `get_weekly_context.last_fatigue_by_sport` |
| ADAPT-02 | I beliefs sull'adattamento di Nicolò sono integrati esplicitamente in ogni proposta di sessione con tag `[athlete-belief: ...]` | Seed SQL in migration, `list_beliefs()` da `belief_engine.py`, estensione `get_weekly_context` con `active_beliefs`, aggiornamento `propose_session.md` |
| ADAPT-03 | Dopo ≥3 sessioni stessa tipologia il sistema aggiorna la stima di risposta fisiologica e aggiusta progressione | Estensione `pattern_extraction.py` (job settimanale deterministico), `reinforce_belief()` / `contradict_belief()`, aggiornamento `mesocycles.progression_plan` |
</phase_requirements>

---

## Summary

Phase 6 aggiunge intelligenza adattativa fisiologica al sistema: (1) classificazione deterministica del tipo di cedimento (muscolare vs cardiovascolare) usando dati Garmin; (2) seeding e lifecycle dei beliefs fisiologici nell'engine Bayesian già esistente; (3) esposizione dei beliefs alle prescrizioni via MCP tool. Tutte e tre le aree operano su codice esistente — nessun nuovo componente architetturale viene introdotto.

La buona notizia per il planner: il codebase è già quasi completo per questo obiettivo. `belief_engine.py` ha l'API completa (create/reinforce/contradict/list), `pattern_extraction.py` ha già la struttura biometrica rule-based come pattern, `get_weekly_context` nel Worker TypeScript ha già il pattern di estensione con nuovi campi JSONB, e `session_analyses` in Supabase ha già la struttura per due nuove colonne. Il lavoro è di connettere questi pezzi, non di costruire da zero.

Il rischio principale è la disponibilità di `splits` nelle attività — se Garmin non popola `activities.splits`, la classificazione decade a fallback RPE-only (confidence 0.4). Questo è previsto in D-03 ma va gestito con cura nei test.

**Primary recommendation:** Implementare nella sequenza logica — (1) migration DB, (2) `classify_fatigue_type()` + test pytest, (3) hook in `post_session_analysis.py`, (4) seed belief + job `pattern_extraction.py`, (5) estensione TypeScript Worker, (6) aggiornamento skill `propose_session.md`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Classificazione tipo cedimento | Analytics Python (`coach/analytics/`) | — | Logica deterministica, zero LLM, testabile. Pattern confermato da `readiness.py` e `pmc.py` |
| Storage classificazione | Database (Supabase `session_analyses`) | — | Due colonne nuove via ALTER TABLE migration |
| Seeding belief fisiologico | Database (migration SQL) | Analytics belief engine | INSERT atomico e idempotente, poi lifecycle via `belief_engine.py` |
| Job aggiornamento beliefs settimanale | Analytics Python (`coach/coaching/pattern_extraction.py`) | — | Già esiste come job settimanale, estensione deterministica |
| Aggiornamento `progression_plan` | Database via belief engine | Analytics Python | Scrittura condizionale quando belief raggiunge `validated_belief` |
| Esposizione beliefs via MCP | Cloudflare Worker TypeScript | Database | `get_weekly_context` aggiunge due campi alla response esistente |
| Citazione beliefs nelle prescrizioni | Skill Markdown (`propose_session.md`) | — | Prompt engineering — nessun codice Python o TypeScript necessario |

---

## Standard Stack

### Core (tutti esistenti nel progetto)

| Library/Tool | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `coach/analytics/belief_engine.py` | esistente | API Bayesian beliefs (create/reinforce/contradict/list/decay) | Già in produzione con lifecycle 4-stati e audit trail |
| `coach/analytics/readiness.py` | esistente | Pattern per funzioni analytics deterministiche con dataclass output | Reference architetturale per `classify_fatigue_type()` |
| `coach/coaching/pattern_extraction.py` | esistente | Job settimanale con sezione biometrica rule-based già separata | Base per estensione job belief update |
| `coach/coaching/post_session_analysis.py` | esistente | Pipeline post-sessione Gemini + salvataggio `session_analyses` | Punto di iniezione per `classify_fatigue_type()` |
| `workers/mcp-server/src/index.ts` | esistente | Worker TypeScript con `getWeeklyContext()` | Estensione con due nuovi campi JSONB |
| Supabase PostgreSQL | managed | Storage DB per `session_analyses`, `beliefs`, `mesocycles` | Single source of truth per tutto il sistema |

### Supporting

| Library/Tool | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `coach/analytics/belief_guardrails.py` | esistente | Verifica admissibility belief prima di creare/aggiornare | Chiamato automaticamente da `create_belief()` |
| `statistics` (stdlib Python) | 3.11 | `fmean`, `pstdev` per calcoli HR drift | Già usato in `pattern_extraction.py` per `extract_biometric_patterns()` |
| `pytest` | 7.4 | Test deterministici `classify_fatigue_type()` | `tests/test_readiness.py` come pattern riferimento |

### No New Packages Required

Phase 6 non richiede nessun pacchetto npm o pip aggiuntivo. Tutte le dipendenze sono già installate.

---

## Package Legitimacy Audit

Nessun nuovo pacchetto esterno viene installato in questa phase. La sezione non si applica.

---

## Architecture Patterns

### System Architecture Diagram

```
Garmin activities.splits
        |
        v
classify_fatigue_type(activity, splits, debrief)
  [coach/analytics/readiness.py — deterministico, zero LLM]
        |
        |-- failure_type: 'muscular'|'cardiovascular'|'mixed'|None
        |-- confidence: float
        v
post_session_analysis.py (prima del call Gemini)
        |
        v
session_analyses.fatigue_type + session_analyses.fatigue_confidence
        |
   (query settimanale)
        v
pattern_extraction.py — job settimanale esteso
  [groupby session_type, n>=3 → reinforce/contradict]
        |
        v
beliefs table — lifecycle Bayesian
        |
        |-- validated_belief → mesocycles.progression_plan (aggiornamento step)
        |
        v
get_weekly_context (Worker TypeScript)
  [campi nuovi: active_beliefs + last_fatigue_by_sport]
        |
        v
propose_session.md (skill)
  [Step 2.5: legge active_beliefs → cita con [athlete-belief: key]]
```

### Recommended Project Structure (modifiche)

```
coach/
├── analytics/
│   └── readiness.py         # aggiungere classify_fatigue_type() + FatigueResult dataclass
├── coaching/
│   └── pattern_extraction.py  # aggiungere update_beliefs_from_session_patterns()
migrations/
└── 2026-06-08-physiological-adaptation.sql  # ALTER TABLE + INSERT belief seed
workers/mcp-server/src/
└── index.ts                 # getWeeklyContext() + query beliefs + last_fatigue_by_sport
skills/
└── propose_session.md       # aggiungere Step 2.5 active_beliefs
tests/
└── test_fatigue_classification.py  # nuovo file pytest
```

### Pattern 1: FatigueResult Dataclass (riferimento: pattern ReadinessReport)

**What:** Dataclass tipizzata per output `classify_fatigue_type()`, coerente con `ReadinessReport` in `readiness.py`.
**When to use:** Ogni chiamata alla funzione di classificazione.
**Example:**
```python
# Source: pattern da coach/analytics/readiness.py (ReadinessReport)
from dataclasses import dataclass
from typing import Optional

@dataclass
class FatigueResult:
    failure_type: Optional[str]   # 'muscular' | 'cardiovascular' | 'mixed' | None
    confidence: float             # 0.0-1.0
    signal_used: str              # 'hr_drift+pace' | 'rpe_only' | 'insufficient'
    notes: Optional[str] = None   # spiegazione human-readable
```

### Pattern 2: classify_fatigue_type() — Logica Decision Tree

**What:** Funzione deterministica che applica D-03 in sequenza, con fallback espliciti.
**When to use:** Chiamata da `post_session_analysis.py` prima del call Gemini.

```python
# Source: D-01/D-02/D-03 da 06-CONTEXT.md
def classify_fatigue_type(
    activity: dict,
    splits: Optional[list],
    debrief_rpe: Optional[int],
) -> FatigueResult:
    duration_s = activity.get("duration_s", 0)
    if duration_s < 1800:  # < 30min: dati insufficienti
        return FatigueResult(failure_type=None, confidence=0.0, signal_used='insufficient',
                             notes='Sessione < 30min')

    sport = activity.get("sport", "other")

    # Se splits mancanti → fallback RPE-only (D-03 fallback)
    if not splits:
        if debrief_rpe is not None and debrief_rpe >= 8:
            return FatigueResult(failure_type='muscular', confidence=0.4,
                                 signal_used='rpe_only',
                                 notes='Dati insufficienti: solo RPE')
        return FatigueResult(failure_type=None, confidence=0.3,
                             signal_used='rpe_only',
                             notes='Dati insufficienti: RPE < 8, tipo non classificabile')

    # Calcolo HR drift (segnale cardiovascolare) — D-03
    hr_drift = _compute_hr_drift(activity, splits)
    # Calcolo pace/power degradation (segnale muscolare) — D-03
    pace_drop = _compute_pace_drop(sport, splits)

    cardiovascular_signal = hr_drift is not None and hr_drift > 10.0
    # D-03 muscular: HR stabile + RPE >= 8 + pace drop > 5%
    muscular_signal = (
        (hr_drift is None or hr_drift <= 10.0)
        and (debrief_rpe is not None and debrief_rpe >= 8)
        and (pace_drop is not None and pace_drop > 0.05)
    )

    if cardiovascular_signal and muscular_signal:
        return FatigueResult(failure_type='mixed', confidence=0.65,
                             signal_used='hr_drift+pace')
    elif cardiovascular_signal:
        conf = min(0.9, 0.6 + (hr_drift - 10.0) * 0.02)
        return FatigueResult(failure_type='cardiovascular', confidence=round(conf, 2),
                             signal_used='hr_drift')
    elif muscular_signal:
        conf = 0.7 if debrief_rpe >= 9 else 0.6
        return FatigueResult(failure_type='muscular', confidence=conf,
                             signal_used='hr_drift+pace')
    else:
        return FatigueResult(failure_type=None, confidence=0.3,
                             signal_used='hr_drift+pace',
                             notes='Segnali sotto soglia — tipo non classificabile')
```

### Pattern 3: Estrazione HR drift da splits

**What:** Helper `_compute_hr_drift()` che divide la sessione in due metà e confronta HR media.
**When to use:** Chiamato dentro `classify_fatigue_type()` quando splits disponibili.

Struttura `splits` in `activities.splits` (da CLAUDE.md §12 + schema.sql): array JSONB di oggetti con `avg_hr` e/o `hr` per split. La struttura varia per disciplina — verificare presenza `avg_hr` per ogni split.

```python
def _compute_hr_drift(activity: dict, splits: list) -> Optional[float]:
    """HR media seconda metà - HR media prima metà della sessione."""
    hr_vals = [s.get("avg_hr") or s.get("hr") for s in splits if s.get("avg_hr") or s.get("hr")]
    if len(hr_vals) < 4:  # minimo 4 split per avere due metà significative
        return None
    mid = len(hr_vals) // 2
    first_half_avg = statistics.fmean(hr_vals[:mid])
    second_half_avg = statistics.fmean(hr_vals[mid:])
    return second_half_avg - first_half_avg
```

### Pattern 4: _compute_pace_drop() — Discipline-specific

**What:** Calcola degradazione pace/power nella seconda metà vs prima metà. Sport-specific.
**When to use:** Chiamato dentro `classify_fatigue_type()`.

Disciplina bici: usa `avg_power_w` per split se disponibile, altrimenti `avg_pace_s_per_km` equivalente. Soglia `>0.05` (5% drop) — Claude's discretion su bici: considerare 8% power drop per essere più conservativo.

```python
def _compute_pace_drop(sport: str, splits: list) -> Optional[float]:
    """Ritorna fraction di degradazione pace/power. Positivo = degrado."""
    if sport == "run":
        key = "avg_pace_s_per_km"  # pace: higher = slower = degradazione
        first_half = statistics.fmean([s[key] for s in splits[:len(splits)//2] if s.get(key)])
        second_half = statistics.fmean([s[key] for s in splits[len(splits)//2:] if s.get(key)])
        if not first_half:
            return None
        return (second_half - first_half) / first_half  # positivo = peggioramento pace
    elif sport == "bike":
        key = "avg_power_w"
        first_half = statistics.fmean([s[key] for s in splits[:len(splits)//2] if s.get(key)])
        second_half = statistics.fmean([s[key] for s in splits[len(splits)//2:] if s.get(key)])
        if not first_half:
            return None
        return (first_half - second_half) / first_half  # positivo = power scende
    elif sport == "swim":
        key = "avg_pace_s_per_100m"
        first_half = statistics.fmean([s[key] for s in splits[:len(splits)//2] if s.get(key)])
        second_half = statistics.fmean([s[key] for s in splits[len(splits)//2:] if s.get(key)])
        if not first_half:
            return None
        return (second_half - first_half) / first_half
    return None
```

### Pattern 5: Hook in post_session_analysis.py

**What:** Chiama `classify_fatigue_type()` prima del call Gemini, scrive risultato in `session_analyses`.
**When to use:** Dentro `analyze_session()`, subito dopo `zone_compliance`.

```python
# Source: post_session_analysis.py — da aggiungere prima del call LLM
from coach.analytics.readiness import classify_fatigue_type

splits = activity.get("splits") or []
# debrief_rpe: cercare nel debrief recente per questa attività
debrief_rpe = next((d.get("rpe") for d in debrief if d.get("rpe")), None)
fatigue_result = classify_fatigue_type(activity, splits or None, debrief_rpe)

# Aggiungere al record da salvare:
record = {
    "activity_id": activity_id,
    "analysis_text": analysis_text,
    "fatigue_type": fatigue_result.failure_type or "insufficient_data",
    "fatigue_confidence": fatigue_result.confidence,
    "suggested_actions": actions,
    "model_used": result.get("model"),
    "cost_usd": result.get("cost_usd"),
}
```

### Pattern 6: Job belief update in pattern_extraction.py

**What:** Nuova funzione `update_beliefs_from_session_patterns()` — deterministica, zero LLM.
**When to use:** Chiamata alla fine di `extract_patterns()` (dopo o in parallelo al call LLM).

```python
def update_beliefs_from_session_patterns(days: int = 14) -> dict:
    """Legge session_analyses ultimi N giorni, raggruppa per session_type,
    chiama reinforce/contradict belief. Zero LLM.

    Returns: {'updated': int, 'created': int, 'errors': int}
    """
    sb = get_supabase()
    since = (today_rome() - timedelta(days=days)).isoformat()

    # JOIN session_analyses con planned_sessions via activity_id → completed_activity_id
    analyses = sb.table("session_analyses").select(
        "activity_id,fatigue_type,fatigue_confidence,created_at"
    ).gte("created_at", since).not_.is_("fatigue_type", None).execute().data or []

    # Per ogni analysis, trovare la planned_session corrispondente via completed_activity_id
    # e la subjective_log per RPE
    # Raggruppare per session_type
    ...
    # Per ogni gruppo con n >= 3:
    #   Se avg_rpe <= 7.5 e fatigue_type != 'cardiovascular' (n > n/2):
    #       reinforce_belief(f"responds_well_{session_type}", reason=f"n={n}, avg_rpe={avg_rpe}")
    #   Else:
    #       contradict_belief o create_belief (se non esiste ancora)
```

### Pattern 7: Estensione getWeeklyContext() TypeScript

**What:** Due query aggiuntive nel `Promise.all()` di `getWeeklyContext()`.
**When to use:** Aggiungere alla destructuring esistente in `getWeeklyContext()`.

```typescript
// Source: workers/mcp-server/src/index.ts — estensione
// Aggiungere al Promise.all() esistente (riga ~622):
const beliefsQuery = sb(env, `beliefs?status=neq.retired&confidence=gte.0.55&order=confidence.desc&select=belief_key,belief_text,status,confidence`).catch(() => []);
const fatigueBySport = await getLastFatigueBySport(env, since);

// Aggiungere al return:
return {
  ...existingFields,
  active_beliefs: (await beliefsQuery) || [],
  last_fatigue_by_sport: fatigueBySort,
};

// Helper function:
async function getLastFatigueBySort(env: Env, since: string): Promise<Record<string, any>> {
  const sports = ["run", "swim", "bike"];
  const result: Record<string, any> = {};
  // Query per ogni sport: ultima session_analysis con fatigue_type non null
  // per activities nelle ultime N settimane
  for (const sport of sports) {
    // JOIN activities + session_analyses via activity_id/external_id
    const rows = await sb(env,
      `session_analyses?select=activity_id,fatigue_type,fatigue_confidence,created_at&fatigue_type=not.is.null&order=created_at.desc&limit=1`
    ).catch(() => []);
    result[sport] = rows?.[0] ? {
      type: rows[0].fatigue_type,
      confidence: rows[0].fatigue_confidence,
      date: rows[0].created_at?.split("T")[0],
    } : null;
  }
  return result;
}
```

**Nota implementativa:** Questa funzione necessita un filtro per sport. Le `session_analyses` non hanno colonna `sport` direttamente — bisogna fare JOIN via `activities.external_id = session_analyses.activity_id`. Supabase PostgREST supporta la sintassi `session_analyses?select=fatigue_type,...,activities!inner(sport)&activities.sport=eq.run`. Alternativa: query Python lato analytics e esporre la tabella di supporto.

### Anti-Patterns to Avoid

- **LLM nella classificazione cedimento:** La logica `classify_fatigue_type()` deve essere zero LLM. Non aggiungere call Gemini per decidere il tipo di cedimento — le soglie sono deterministiche per design.
- **Overwrite di beliefs senza guardrail:** Non chiamare `create_belief()` bypassando `belief_guardrails.py`. `create_belief()` chiama i guardrail internamente — usare sempre l'API pubblica.
- **Modificare planned_sessions senza conferma:** Il job settimanale aggiorna solo `mesocycles.progression_plan` (metadato di progressione), non `planned_sessions`. La scrittura diretta su `planned_sessions` richiede conferma esplicita dell'atleta (CLAUDE.md §5.4 — inviolabile).
- **Usare splits mancanti come errore:** Se `activities.splits` è null o vuoto, non è un errore — è un caso normale. La funzione deve fare fallback a RPE-only (D-03 fallback) senza eccezione.
- **Belief seedato con `create_belief()` invece di SQL:** Il seed ADAPT-02 va in una migration SQL (`ON CONFLICT DO NOTHING`) per essere idempotente e replicabile. `create_belief()` skippa silenziosamente se il key esiste già, ma è meno auditabile.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bayesian belief lifecycle | Logica confidence custom | `belief_engine.py` API pubblica (`reinforce_belief`, `contradict_belief`) | Già implementato con decay esponenziale, diminishing returns, audit trail `beliefs_history` |
| Guardrail su beliefs rischiose | Check custom nel job | `belief_guardrails.check_belief_admissible()` — già chiamato da `create_belief()` | Anti-overfitting, safety override detection già codificato |
| Normalizzazione splits | Parser custom per ogni Garmin activity | Leggere `activity.splits` JSONB as-is con guard `or {}` | Il formato è già normalizzato dall'ingest Garmin in `coach/ingest/garmin.py` |
| Calcolo aritmetico medio/deviazione | Implementazione custom | `statistics.fmean()`, `statistics.pstdev()` (stdlib) | Già usato in `pattern_extraction.py` e `readiness.py` |
| Query DB storico | ORM custom | Pattern Supabase client esistente (`sb.table(...).select(...).execute()`) | `get_supabase()` singleton già disponibile |

**Key insight:** In questa phase il lavoro è connettere asset esistenti con nuove funzioni di calcolo deterministico — non costruire nuove astrazioni.

---

## Common Pitfalls

### Pitfall 1: splits JSONB — struttura variabile per disciplina

**What goes wrong:** `splits` in `activities` è un array JSONB il cui schema interno dipende dalla disciplina e dal dispositivo Garmin. Una corsa ha split per km (con `avg_pace_s_per_km`), una bici può avere split per lap o per potenza, una nuotata ha split per vasca. Il codice che assume una struttura fissa crasha silenziosamente.

**Why it happens:** `activities.splits` è popolato dall'ingest Garmin (`coach/ingest/garmin.py`) con il payload grezzo dell'API `get_activity_splits`. Il formato non è normalizzato a livello DB.

**How to avoid:** Usare `.get()` con default su ogni campo di split: `s.get("avg_hr") or s.get("hr") or None`. Testare `classify_fatigue_type()` con split None, split vuoto `[]`, e split con campi mancanti.

**Warning signs:** `KeyError` o `TypeError` in produzione sulla classificazione; `confidence = 0.0` su tutte le analisi.

### Pitfall 2: JOIN session_analyses ↔ activities per sport in TypeScript Worker

**What goes wrong:** `session_analyses` non ha una colonna `sport`. Per filtrare `last_fatigue_by_sport` per disciplina bisogna fare JOIN con `activities` via `activity_id = activities.external_id`. Se il JOIN non è corretto o il formato `external_id` differisce, la query torna zero righe.

**Why it happens:** `session_analyses.activity_id` è `TEXT` (non UUID FK), mentre `activities.external_id` è anche TEXT. Il JOIN funziona ma non è forzato da FK constraint.

**How to avoid:** Verificare con query SQL diretta in Supabase prima di scrivere il codice Worker. Alternativa più semplice: aggiungere colonna `sport TEXT` a `session_analyses` nella migration, popolata da `post_session_analysis.py` al momento dell'insert (il `sport` è già disponibile dall'`activity` object).

**Warning signs:** `last_fatigue_by_sport` torna sempre `{run: null, swim: null, bike: null}`.

### Pitfall 3: belief seed con `evidence_note` non standard

**What goes wrong:** Il campo `evidence_note` non è nella schema definition di `beliefs` (migration `2026-05-14-cognitive-mvp.sql`). Il seed SQL in D-06 usa `evidence_note` ma la colonna non esiste — l'INSERT fallisce.

**Why it happens:** `belief_engine.py` usa `source` e `source_metadata JSONB` — non `evidence_note`. Il CONTEXT.md usa il termine `evidence_note` informalmente.

**How to avoid:** Mappare `evidence_note` → `source` (TEXT) nella migration. La motivation lunga va in `source_metadata JSONB`: `{"evidence_note": "Basato su CLAUDE.md §2..."}`. Verificare con `beliefs` schema da `2026-05-14-cognitive-mvp.sql` prima di scrivere l'INSERT.

**Warning signs:** Migration fallisce con `column "evidence_note" of relation "beliefs" does not exist`.

### Pitfall 4: Pattern extraction job — nessuna planned_session corrispondente

**What goes wrong:** Il job settimanale tenta un JOIN `session_analyses` → `planned_sessions` via `activities.external_id = completed_activity_id`. Se l'attività non aveva una sessione pianificata corrispondente (sessione libera, fuori piano), il JOIN restituisce null `session_type`. Il groupby per `session_type=NULL` è inutile per aggiornare beliefs.

**Why it happens:** Non tutte le attività Garmin hanno una `planned_session` corrispondente — Nicolò può allenarsi fuori piano.

**How to avoid:** Il job deve gestire `session_type=NULL` come skip (non creare belief `responds_well_None`). Aggiungere guard esplicito: `if not session_type: continue`. Loggare il conteggio di sessioni senza piano.

**Warning signs:** Beliefs `responds_well_None` o `struggles_with_None` in `beliefs` table.

### Pitfall 5: Belief `endurance_failure_type` già esistente (run idempotente)

**What goes wrong:** Se la migration viene eseguita due volte (retry CI o rideploy), l'INSERT seed viola il UNIQUE constraint su `belief_key` e la migration fallisce.

**Why it happens:** `beliefs.belief_key` ha `UNIQUE` constraint. L'INSERT senza guard fallisce al secondo run.

**How to avoid:** Usare il pattern esistente nelle migration del progetto: `INSERT ... ON CONFLICT (belief_key) DO NOTHING`. Oppure `WHERE NOT EXISTS (SELECT 1 FROM beliefs WHERE belief_key = 'endurance_failure_type')`. Verificare che il CHECK su `status` accetti `'validated_belief'` — dalla migration `2026-05-14-cognitive-mvp.sql`: `CHECK (status IN ('hypothesis','weak_belief','validated_belief','strong_belief','retired'))` — OK.

**Warning signs:** Migration fallisce con `duplicate key value violates unique constraint "beliefs_belief_key_key"`.

### Pitfall 6: `propose_session.md` — Step 2.5 aggiunto vs Step 2 esistente

**What goes wrong:** `propose_session.md` ha già uno Step 2 ("Contesto settimanale + vincoli medici") che chiama `get_weekly_context()`. Se il nuovo Step 2.5 è aggiunto come step separato, il LLM potrebbe chiamare `get_weekly_context()` due volte (aumentando latenza e potenzialmente confondendo il flow).

**Why it happens:** La lettura di `active_beliefs` avviene già dentro `get_weekly_context()` — non è necessaria una seconda chiamata.

**How to avoid:** Aggiungere la lettura di `active_beliefs` come sotto-step dentro Step 2 esistente (non come Step 2.5 separato). La struttura naturale è: "Step 2 — Leggi `get_weekly_context()`. Estrai: `active_constraints` [...], `active_beliefs` [...]".

---

## Code Examples

### Migration SQL — ALTER TABLE + seed belief

```sql
-- Source: pattern da migrations/2026-05-14-cognitive-mvp.sql e 2026-06-07-workout-prescription-quality.sql

-- ADAPT-01: due nuove colonne su session_analyses
ALTER TABLE session_analyses
    ADD COLUMN IF NOT EXISTS fatigue_type TEXT CHECK (
        fatigue_type IN ('muscular', 'cardiovascular', 'mixed', 'insufficient_data')
    ),
    ADD COLUMN IF NOT EXISTS fatigue_confidence FLOAT CHECK (
        fatigue_confidence IS NULL OR (fatigue_confidence >= 0 AND fatigue_confidence <= 1)
    );

-- ADAPT-02: seed belief "endurance puro, cedimento muscolare first"
INSERT INTO beliefs (
    belief_key, belief_text, confidence, evidence_n, status,
    source, source_metadata, last_reinforced_at, first_observed_at
)
VALUES (
    'endurance_failure_type',
    'Nicolò è atleta endurance puro: primo cedimento muscolare, non cardiovascolare. HR rimane stabile anche ad alta intensità; il cedimento è al tono muscolare.',
    0.75,
    8,
    'validated_belief',
    'manual_seed',
    '{"evidence_note": "Basato su CLAUDE.md §2: profilo atleta, confermato da storico élite 2021-2022 (114 sessioni)"}',
    NOW(),
    NOW()
) ON CONFLICT (belief_key) DO NOTHING;
```

### Test pytest — classify_fatigue_type

```python
# Source: pattern da tests/test_readiness.py
# tests/test_fatigue_classification.py

from coach.analytics.readiness import classify_fatigue_type

def make_splits_run(hr_first: float, hr_second: float, pace_first: float, pace_second: float, n: int = 5):
    """Genera split sintetici per test: prima metà HR/pace stabili, seconda metà degradata."""
    half = n // 2
    splits = []
    for i in range(half):
        splits.append({"avg_hr": hr_first, "avg_pace_s_per_km": pace_first})
    for i in range(n - half):
        splits.append({"avg_hr": hr_second, "avg_pace_s_per_km": pace_second})
    return splits


def test_cardiovascular_signal():
    activity = {"sport": "run", "duration_s": 3600}
    splits = make_splits_run(hr_first=145, hr_second=160, pace_first=280, pace_second=282)
    result = classify_fatigue_type(activity, splits, debrief_rpe=7)
    assert result.failure_type == "cardiovascular"
    assert result.confidence >= 0.6


def test_muscular_signal():
    activity = {"sport": "run", "duration_s": 3600}
    # HR stabile, pace peggiora, RPE alto
    splits = make_splits_run(hr_first=150, hr_second=152, pace_first=263, pace_second=285)
    result = classify_fatigue_type(activity, splits, debrief_rpe=8)
    assert result.failure_type == "muscular"
    assert result.confidence >= 0.6


def test_fallback_rpe_only_no_splits():
    activity = {"sport": "run", "duration_s": 3600}
    result = classify_fatigue_type(activity, None, debrief_rpe=9)
    assert result.failure_type == "muscular"
    assert result.confidence == 0.4
    assert result.signal_used == "rpe_only"


def test_insufficient_data_short_session():
    activity = {"sport": "run", "duration_s": 1200}  # 20min
    result = classify_fatigue_type(activity, [], debrief_rpe=6)
    assert result.failure_type is None


def test_missing_splits_low_rpe():
    activity = {"sport": "bike", "duration_s": 3600}
    result = classify_fatigue_type(activity, None, debrief_rpe=5)
    assert result.failure_type is None
    assert result.signal_used == "rpe_only"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sessioni analizzate solo con LLM Gemini | Classificazione deterministica PRIMA del call LLM, arricchisce il contesto | Phase 6 | Zero costo LLM per classificazione, risultato sempre disponibile anche a budget esaurito |
| Beliefs solo da `pattern_extraction.py` (LLM-based) | Beliefs aggiornati anche da job deterministico (zero LLM) su dati strutturati | Phase 6 | Aggiornamento beliefs più affidabile, no degradazione a budget esaurito |
| Vincoli medici in `CLAUDE.md` statico | Vincoli in `active_constraints` DB (Phase 5) + beliefs fisiologici in `beliefs` DB (Phase 6) | Phase 5-6 | Prescrizioni sempre aggiornate a fitness e infortuni correnti |

**Deprecated/outdated:**
- Hard-coded assumption "Nicolò è endurance puro" come testo in CLAUDE.md: rimane per contesto umano, ma la fonte operativa per le prescrizioni diventa il `beliefs` DB. Il skill `propose_session.md` leggerà il belief da `get_weekly_context.active_beliefs`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `activities.splits` è un array JSONB con oggetti che hanno `avg_hr` come chiave. Struttura mai verificata su dati reali — solo dedotta da `_get_historical()` in `post_session_analysis.py` che seleziona `splits` | Architecture Patterns, Pitfall 1 | La funzione `classify_fatigue_type()` ritorna sempre `None` (fallback) se la chiave è diversa |
| A2 | La colonna `evidence_note` non esiste in `beliefs` — va mappata su `source_metadata JSONB` | Pitfall 3, Code Examples | Migration fallisce senza questo fix |
| A3 | Il JOIN `session_analyses.activity_id = activities.external_id` funziona per recuperare `sport` | Architecture Patterns | `last_fatigue_by_sport` in Worker non filtra per sport correttamente |
| A4 | Il power drop threshold di 5% per bici è un valore ragionevole per rilevare cedimento muscolare | Code Examples (Pattern 4) | Falsi positivi (bici in salita) o falsi negativi (cedimento lieve non rilevato) |

**Nessuna assunzione critica non verificabile:** Tutti i rischi sopra hanno fallback sicuri nel codice (confidence bassa o `None` come output).

---

## Open Questions

1. **Struttura reale di `activities.splits` su dati Garmin live**
   - What we know: la colonna esiste in schema.sql (`splits JSONB`) ed è letta da `_get_historical()` in `post_session_analysis.py`
   - What's unclear: quali chiavi sono presenti per run/bike/swim. Può essere `null` per alcune disciplina o tipi di attività
   - Recommendation: aggiungere log `logger.debug("splits keys: %s", list(splits[0].keys()) if splits else "none")` nel codice di classificazione durante i primi run in produzione. I test pytest coprono splits=None come fallback sicuro.

2. **JOIN session_analyses ↔ activities per `last_fatigue_by_sport` nel Worker TypeScript**
   - What we know: `session_analyses.activity_id` è TEXT, `activities.external_id` è TEXT — JOIN possibile
   - What's unclear: PostgREST syntax per embedded resource con filtro su tabella parent (`activities.sport`)
   - Recommendation: alternativa più robusta — aggiungere colonna `sport TEXT` a `session_analyses` nella migration Phase 6, popolata da `post_session_analysis.py`. Questo elimina il JOIN nel Worker.

3. **`pattern_extraction.py` — come ottenere `session_type` per le session_analyses**
   - What we know: `planned_sessions.session_type` contiene il tipo (es. `threshold`, `vo2max`, `LSD`). `planned_sessions.completed_activity_id` è FK verso `activities.id` (UUID). `session_analyses.activity_id` è TEXT = `activities.external_id`
   - What's unclear: il JOIN richiede `planned_sessions.completed_activity_id = activities.id` e poi `activities.external_id = session_analyses.activity_id` — due hop JOIN via Python (non via PostgREST direttamente)
   - Recommendation: fare due query separate in Python: (1) fetch analyses recenti con activity_id, (2) per ogni activity_id cercare `activities.external_id = activity_id` per ottenere `activities.id`, (3) cercare `planned_sessions.completed_activity_id = activities.id`. Oppure aggiungere `session_type` a `session_analyses` nella migration.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | `classify_fatigue_type()`, job extension | Verificato (GitHub Actions `ingest.yml`) | 3.11 | — |
| `statistics` stdlib | Calcoli HR drift, pace drop | Built-in Python 3.4+ | N/A | — |
| Supabase PostgREST | Query `beliefs`, `session_analyses` | Verificato (in produzione) | managed | — |
| pytest 7.4 | Test `test_fatigue_classification.py` | Verificato (`pytest.ini` + `tests/`) | 7.4 | — |
| Wrangler 3.50 | Deploy Worker TypeScript modificato | Verificato (`deploy-dashboard.yml`) | 3.50 | — |

**Missing dependencies:** Nessuna. Tutti i tool necessari sono già disponibili.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4 |
| Config file | `pytest.ini` (root) |
| Quick run command | `python -m pytest tests/test_fatigue_classification.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADAPT-01 | `classify_fatigue_type()` classifica cardiovascular (HR drift >10bpm) | unit | `pytest tests/test_fatigue_classification.py::test_cardiovascular_signal -x` | Wave 0 |
| ADAPT-01 | `classify_fatigue_type()` classifica muscular (HR stabile + RPE≥8 + pace drop) | unit | `pytest tests/test_fatigue_classification.py::test_muscular_signal -x` | Wave 0 |
| ADAPT-01 | `classify_fatigue_type()` fallback RPE-only quando splits assenti | unit | `pytest tests/test_fatigue_classification.py::test_fallback_rpe_only_no_splits -x` | Wave 0 |
| ADAPT-01 | `classify_fatigue_type()` ritorna None per sessioni <30min | unit | `pytest tests/test_fatigue_classification.py::test_insufficient_data_short_session -x` | Wave 0 |
| ADAPT-02 | Migration SQL contiene INSERT belief seed con `ON CONFLICT DO NOTHING` | static | `pytest tests/test_physio_adaptation.py::test_migration_belief_seed_idempotent -x` | Wave 0 |
| ADAPT-02 | Migration SQL contiene ALTER TABLE session_analyses con nuove colonne | static | `pytest tests/test_physio_adaptation.py::test_migration_session_analyses_columns -x` | Wave 0 |
| ADAPT-02 | `propose_session.md` contiene step lettura `active_beliefs` e tag `[athlete-belief:]` | static | `pytest tests/test_physio_adaptation.py::test_skill_active_beliefs_step -x` | Wave 0 |
| ADAPT-03 | Job `update_beliefs_from_session_patterns()` è deterministico (zero LLM) e gestisce n<3 sessioni senza creare beliefs | unit | `pytest tests/test_fatigue_classification.py::test_belief_update_minimum_sessions -x` | Wave 0 |
| ADAPT-03 | Job non crea beliefs con `session_type=None` (sessioni fuori piano) | unit | `pytest tests/test_fatigue_classification.py::test_belief_update_skips_null_session_type -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_fatigue_classification.py tests/test_physio_adaptation.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green prima di `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_fatigue_classification.py` — unit test `classify_fatigue_type()`, coprire ADAPT-01 + ADAPT-03
- [ ] `tests/test_physio_adaptation.py` — static test migration SQL + skill file, coprire ADAPT-02

*(Nessuna infrastruttura pytest mancante — `pytest.ini` + `tests/` esistono)*

---

## Security Domain

### Applicable ASVS Categories (ASVS Level 1)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Nessuna nuova autenticazione introdotta |
| V3 Session Management | no | Nessuna sessione nuova |
| V4 Access Control | yes (existing) | RLS Supabase su `beliefs` e `session_analyses` già attivo; nuove colonne ereditano la policy esistente |
| V5 Input Validation | yes | CHECK constraint SQL su `fatigue_type` values; confidence FLOAT 0-1; `belief_guardrails.py` per admissibility |
| V6 Cryptography | no | Nessuna operazione crittografica nuova |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via belief_key | Tampering | Supabase client usa query parametrizzate (pattern esistente) |
| Belief manipulation via job | Tampering | `belief_guardrails.check_belief_admissible()` chiamato da `create_belief()` — già mitigato |
| MCP Worker espone nuovi dati beliefs | Information disclosure | `MCP_BEARER_TOKEN` già in produzione, nessuna nuova superficie auth |
| Valori `fatigue_type` non-validi in INSERT | Tampering | CHECK constraint DB su `session_analyses.fatigue_type` |

---

## Sources

### Primary (HIGH confidence — codebase diretta)

- `coach/analytics/belief_engine.py` — API pubblica `create_belief`, `reinforce_belief`, `contradict_belief`, `list_beliefs`; thresholds `VALIDATED_MIN_N=8`, `VALIDATED_MIN_CONFIDENCE=0.7`
- `coach/analytics/belief_guardrails.py` — `check_belief_admissible()` chiamato da `create_belief()` automaticamente
- `coach/analytics/readiness.py` — pattern architetturale dataclass + funzioni deterministiche per funzioni analytics
- `coach/coaching/post_session_analysis.py` — flusso `analyze_session()`, accesso a `splits`, struttura record `session_analyses`
- `coach/coaching/pattern_extraction.py` — struttura job settimanale, `extract_biometric_patterns()` come reference per nuova funzione deterministica
- `workers/mcp-server/src/index.ts` — `getWeeklyContext()` existing response structure, pattern `Promise.all()`, `sb()` helper
- `sql/schema.sql` — schema `session_analyses`, `beliefs`, `mesocycles`, `planned_sessions`
- `migrations/2026-05-14-cognitive-mvp.sql` — schema completo tabella `beliefs` con tutti i campi
- `migrations/2026-06-07-workout-prescription-quality.sql` — pattern migration: `IF NOT EXISTS`, `WHERE NOT EXISTS`, seed dati
- `skills/propose_session.md` — struttura corrente Steps 0-5, dove inserire Step beliefs
- `tests/test_readiness.py` — pattern pytest per funzioni analytics deterministiche
- `tests/test_active_constraints.py` — pattern pytest per static migration test
- `.planning/phases/06-physiological-adaptation-intelligence/06-CONTEXT.md` — tutte le decisioni D-01..D-15

### Tertiary (da verificare su dati reali)

- Struttura `activities.splits` JSONB su dati Garmin live: dedotta da schema e codice, non ispezionata su righe reali

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — tutto è codice esistente, ispezionato direttamente
- Architecture: HIGH — pattern consolidati nel codebase, nessuna nuova astrazione
- Pitfalls: HIGH — derivati da analisi del codice esistente e vincoli DB
- Assumptions: MEDIUM su struttura reale `splits` in produzione

**Research date:** 2026-06-08
**Valid until:** 2026-09-06 (fine progetto Lavarone) — stack stabile, nessuna dipendenza esterna che muta
