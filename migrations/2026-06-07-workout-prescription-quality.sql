-- Migration: Workout Prescription Quality 2026-06-07
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   Phase 5 — nuova tabella active_constraints: vincoli medici dinamici (D-12/D-13)
--             WORKOUT-03: vincoli medici da DB, non da CLAUDE.md statico
--   Phase 5 — mesocycles.progression_plan JSONB (D-27)
--             WORKOUT-04: progressione qualità multi-sessione nel mesociclo

-- ── active_constraints: vincoli medici/medici/tattici dinamici ──────────────
-- Tabella per i vincoli attivi che influenzano la prescrizione degli allenamenti.
-- Sostituisce i vincoli hardcoded in CLAUDE.md §2 (spalla dx, fascite sx, ecc.).
-- resolved_at IS NULL = vincolo attivo; resolved_at non NULL = risolto.

CREATE TABLE IF NOT EXISTS active_constraints (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type            TEXT NOT NULL CHECK (type IN ('injury', 'medical', 'tactical')),
    discipline      TEXT NOT NULL CHECK (discipline IN ('swim', 'bike', 'run', 'all')),
    description     TEXT NOT NULL,
    severity        TEXT CHECK (severity IN ('high', 'medium', 'low')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

-- RLS: accesso solo via service_role (pattern single-user esistente, V4 ASVS L1)
-- Stessa policy delle altre tabelle in sql/schema.sql: service_role bypass,
-- tutti gli altri ruoli negati per default (nessuna policy = zero righe visibili).
-- La policy esplicita rende l'intento auditabile e protegge da futuri ruoli authenticated.
ALTER TABLE active_constraints ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "service_role_full_access" ON active_constraints
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── mesocycles.progression_plan JSONB ────────────────────────────────────────
-- Colonna JSONB per il piano di progressione qualità multi-sessione (D-27).
-- Struttura: { "run_threshold": { "week1": "4x6min", "week2": "5x6min", "week3": "6x6min" }, ... }
-- NULL = nessun piano di progressione esplicito per questo mesociclo.

ALTER TABLE mesocycles
    ADD COLUMN IF NOT EXISTS progression_plan JSONB;

-- ── Partial UNIQUE index: previene duplicati attivi per stessa (type, discipline) ──
-- WHERE NOT EXISTS è necessario ma non sufficiente: due esecuzioni concorrenti
-- (es. retry CI) possono passare entrambe il check prima che uno dei due INSERT
-- faccia il commit. Il partial UNIQUE index garantisce unicità a livello DB.
CREATE UNIQUE INDEX IF NOT EXISTS active_constraints_injury_discipline_active
  ON active_constraints (type, discipline)
  WHERE resolved_at IS NULL;

-- ── Seed dati D-13: 2 vincoli medici attivi per Nicolò ───────────────────────
-- Pattern WHERE NOT EXISTS: idempotente in combinazione con il UNIQUE index sopra.
-- Guard: skip se esiste già un vincolo attivo (resolved_at IS NULL) per stessa (type, discipline).

INSERT INTO active_constraints (type, discipline, description, severity)
SELECT 'injury', 'swim',
       'borsite + tendinopatia CLB spalla destra: max Z1-Z2, zero Z4+, distanza 72h tra sessioni nuoto',
       'high'
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints
    WHERE type = 'injury' AND discipline = 'swim' AND resolved_at IS NULL
);

INSERT INTO active_constraints (type, discipline, description, severity)
SELECT 'injury', 'run',
       'fascite plantare sinistra: max +10% volume/settimana, cap 14-15km/settimana attuale, asintomatica da 14gg',
       'medium'
WHERE NOT EXISTS (
    SELECT 1 FROM active_constraints
    WHERE type = 'injury' AND discipline = 'run' AND resolved_at IS NULL
);
