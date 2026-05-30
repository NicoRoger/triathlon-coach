-- Fase 4 Cognitive MVP — beliefs storage + recommendation provenance

-- ============================================================================
-- Beliefs table (Modulo 4.4 — Bayesian Belief Engine)
-- ============================================================================
-- Ogni belief è probabilistica, decay-aware, lifecycle-aware.
-- Le belief non sono cancellate da contradictory evidence: la confidence cala.

CREATE TABLE IF NOT EXISTS beliefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Identità: belief_key è la chiave naturale (es. "hrv_low_saturday")
    -- Diverse occorrenze dello stesso key vengono UPSERT-ate.
    belief_key TEXT NOT NULL UNIQUE,
    belief_text TEXT NOT NULL,            -- "HRV basso sabato (mean z=-0.8)"
    category TEXT,                        -- es. recovery / training_response / preference

    -- Stato probabilistico
    confidence NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_n INTEGER NOT NULL DEFAULT 0,
    supporting_outcomes UUID[] DEFAULT '{}',
    contradicting_outcomes UUID[] DEFAULT '{}',
    evidence_decay_half_life_days INTEGER NOT NULL DEFAULT 120,

    -- Prescription associata (se la belief è actionable)
    prescription TEXT,
    expected_outcome TEXT,

    -- Lifecycle
    -- hypothesis (n<4) | weak_belief (n>=4 AND conf>0.55) | validated_belief (n>=8 AND conf>0.7) |
    -- strong_belief (longitudinal stability > 6 mesi)
    status TEXT NOT NULL DEFAULT 'hypothesis'
        CHECK (status IN ('hypothesis','weak_belief','validated_belief','strong_belief','retired')),
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reinforced_at TIMESTAMPTZ,        -- ultima evidenza positiva
    last_contradicted_at TIMESTAMPTZ,      -- ultima evidenza contraria

    -- Origine (per audit)
    source TEXT,                           -- pattern_extraction | hypothesis_validated | manual
    source_metadata JSONB,

    -- Guardrails flag
    flagged BOOLEAN NOT NULL DEFAULT FALSE,
    flag_reason TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_beliefs_status_confidence
  ON beliefs (status, confidence DESC) WHERE status != 'retired';
CREATE INDEX IF NOT EXISTS idx_beliefs_category
  ON beliefs (category, status);
CREATE INDEX IF NOT EXISTS idx_beliefs_last_updated
  ON beliefs (last_updated_at DESC);

COMMENT ON TABLE beliefs IS
  'Bayesian belief engine: probabilità, decay esponenziale, lifecycle 4-stati. Contradictory evidence riduce confidence (non cancella).';
COMMENT ON COLUMN beliefs.belief_key IS
  'Chiave naturale UNIQUE (snake_case). UPSERT su update da nuova evidenza.';
COMMENT ON COLUMN beliefs.evidence_decay_half_life_days IS
  'Default 120gg: dopo 120gg senza reinforcement, weight evidenza scende del 50%.';


-- Cronologia cambi belief (audit trail per debug e analisi longitudinale)
CREATE TABLE IF NOT EXISTS beliefs_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belief_id UUID NOT NULL REFERENCES beliefs(id) ON DELETE CASCADE,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_type TEXT NOT NULL,             -- created | reinforced | contradicted | promoted | demoted | flagged | retired
    confidence_before NUMERIC,
    confidence_after NUMERIC,
    evidence_n_before INTEGER,
    evidence_n_after INTEGER,
    status_before TEXT,
    status_after TEXT,
    reason TEXT,
    related_outcome_id UUID,               -- outcome che ha causato il cambio
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_beliefs_history_belief
  ON beliefs_history (belief_id, changed_at DESC);

COMMENT ON TABLE beliefs_history IS
  'Audit trail: ogni reinforcement/contradiction/promotion/demotion lascia traccia. Permette di rispondere a "perché abbiamo cambiato idea?".';


-- ============================================================================
-- Recommendations table (Modulo 4.3 — Uncertainty Framework)
-- ============================================================================
-- Ogni recommendation prodotta dal sistema viene loggata con il suo
-- recommendation object standard per audit + analisi calibrazione.

CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Sorgente
    source_module TEXT NOT NULL,           -- briefing | weekly_review | modulation | etc.
    -- Contenuto
    recommendation TEXT NOT NULL,          -- testo della recommendation
    -- Uncertainty fields (Modulo 4.3)
    confidence NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_n INTEGER,
    evidence_quality TEXT,                 -- weak | moderate | strong
    data_coverage NUMERIC CHECK (data_coverage IS NULL OR (data_coverage >= 0 AND data_coverage <= 1)),
    uncertainty_drivers JSONB,             -- ["limited hot-weather samples", ...]
    blind_spots JSONB,                     -- ["running biomechanics unavailable", ...]
    -- Priority engine output (Modulo 4.2)
    winning_priority INTEGER,
    overridden_priorities INTEGER[],
    priority_reason TEXT,
    tradeoffs JSONB,
    -- Beliefs/citations utilizzati
    beliefs_used UUID[] DEFAULT '{}',      -- ref a beliefs.id
    citations JSONB,                       -- [{source, topic}]
    -- Outcome link (riempito da outcome_engine)
    related_prediction_ids UUID[] DEFAULT '{}',
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_recommendations_source_recent
  ON recommendations (source_module, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_low_confidence
  ON recommendations (created_at DESC) WHERE confidence < 0.6;

COMMENT ON TABLE recommendations IS
  'Recommendation object standard (Fase 4.3). Audit trail di tutte le proposte con confidence, blind spots, priority resolution.';

-- RLS: allinea al pattern single-user di schema.sql (deny-all anon, service_role bypassa).
ALTER TABLE beliefs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE beliefs_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
