-- Fase 3.1 + 3.4 — Hypothesis testing + Decision provenance

-- ============================================================================
-- Hypothesis testing framework
-- ============================================================================
-- Permette di formulare ipotesi formali sulla risposta dell'atleta (es.
-- "polarizzato vs piramidale produce miglior CTL"), eseguirle come esperimenti
-- controllati su 2+ mesocicli alternati, verificare statisticamente l'esito.

CREATE TABLE IF NOT EXISTS hypothesis_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Status del ciclo di vita
    -- proposed → setup → running → analyzing → validated / rejected / inconclusive
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed','setup','running','analyzing','validated','rejected','inconclusive','aborted')),

    -- Definizione dell'ipotesi
    hypothesis TEXT NOT NULL,                -- frase singola, falsifiabile
    rationale TEXT,                          -- perché vale la pena testare
    expected_effect TEXT,                    -- es. "+5% CTL", "-10% delta_pct race_time"

    -- Variabile manipolata e variabile misurata
    intervention TEXT,                       -- es. "polarized 80/20", "block periodization"
    control TEXT,                            -- es. "pyramidal default", "linear progression"
    metric TEXT,                             -- es. "ctl_weekly", "race_time_delta_pct"
    success_threshold NUMERIC,               -- es. 5% (effetto minimo per validare)

    -- Setup
    start_date DATE,                         -- inizio esperimento
    end_date DATE,                           -- fine prevista
    related_mesocycle_ids UUID[],            -- mesocicli che fanno parte dell'esperimento
    arms JSONB,                              -- {"intervention": {...}, "control": {...}}

    -- Risultato (popolato in fase analyzing/validated)
    result_summary TEXT,
    effect_observed NUMERIC,
    confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    n_observations INTEGER,
    p_value NUMERIC,                         -- opzionale, per sample size >= 8

    resolved_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_status
  ON hypothesis_tests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hypothesis_active
  ON hypothesis_tests (start_date, end_date)
  WHERE status IN ('setup', 'running', 'analyzing');

COMMENT ON TABLE hypothesis_tests IS
  'Esperimenti controllati per testare ipotesi sulla risposta dell''atleta a interventi specifici. Confidence cresce lentamente (pochi esperimenti/anno) ma converge nel lungo termine.';
COMMENT ON COLUMN hypothesis_tests.arms IS
  'Configurazione delle 2+ varianti messe a confronto. Esempio: {"A": {"distribution": "polarized_8020", "weeks": [1,2,3]}, "B": {"distribution": "pyramidal", "weeks": [5,6,7]}}.';


-- ============================================================================
-- Decision audit trail
-- ============================================================================
-- Per ogni decisione strutturale del coach (weekly_review, mesocycle_change,
-- modulation_applied, race_briefing) salva: timestamp, decisione, input
-- considerati, beliefs invocate, citazioni scientifiche, confidence.
-- Permette di rispondere a "perché abbiamo fatto X?" mesi dopo.

CREATE TABLE IF NOT EXISTS decision_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Tipo decisione
    -- weekly_review | mesocycle_commit | modulation_applied | race_briefing |
    -- session_proposal | test_scheduled | manual_override
    decision_type TEXT NOT NULL,
    decision_summary TEXT NOT NULL,          -- 1-3 righe descrizione

    -- Input usati per arrivare alla decisione
    data_inputs JSONB,                       -- {ctl: ..., tsb: ..., hrv: ...}
    beliefs_used JSONB,                      -- [{belief, confidence, source}]
    citations JSONB,                         -- [{source: "Seiler 2010", topic: "polarized"}]
    risks_considered JSONB,                  -- {overreaching: 0.4, injury: 0.2, ...}
    tradeoffs JSONB,                         -- {sacrificed: "...", gained: "..."}
    confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),

    -- Esito atteso (verrà confrontato con outcome reale)
    expected_outcome TEXT,
    related_prediction_ids UUID[],

    -- Esecuzione
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    applied_at TIMESTAMPTZ,
    overridden BOOLEAN NOT NULL DEFAULT FALSE,
    override_reason TEXT,

    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_decision_audit_type_recent
  ON decision_audit (decision_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_audit_unapplied
  ON decision_audit (created_at DESC) WHERE applied = FALSE;

COMMENT ON TABLE decision_audit IS
  'Audit trail di tutte le decisioni strutturali del coach. Permette analisi retrospettiva: "perché abbiamo proposto X?". Citazioni e beliefs sono dati strutturati, non solo testo.';
