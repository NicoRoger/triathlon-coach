-- Fase 2.1 — Outcome tracking engine
-- Chiude il loop prediction → outcome → error → calibration → belief update.
-- Ogni proposta verificabile (CTL settimanale, race time, FTP, readiness,
-- recovery duration, compliance) genera una riga in predictions.
-- Il workflow domenicale verifica e popola outcomes.

CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Tipologia: ctl_weekly, race_time, ftp, threshold_pace, css,
    --           readiness_score, recovery_duration_h, compliance_pct, weekly_volume_min
    prediction_type TEXT NOT NULL,
    target_date DATE NOT NULL,                  -- data in cui verificare
    predicted_value NUMERIC NOT NULL,
    predicted_range_low NUMERIC,                -- bound inferiore CI
    predicted_range_high NUMERIC,               -- bound superiore CI
    confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    model_version TEXT,                         -- es. ctl_proj_v1, race_pred_v2
    reasoning_summary TEXT,                     -- 1-3 righe spiegazione
    source TEXT,                                -- es. weekly_review, test_scheduler, race_prediction
    related_entity_id UUID,                     -- ref a race.id / mesocycle.id / activity external_id
    related_entity_type TEXT,                   -- es. race, mesocycle, activity, test
    resolved BOOLEAN NOT NULL DEFAULT FALSE,    -- TRUE quando outcome scritto
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_predictions_unresolved
  ON predictions (target_date) WHERE resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_predictions_type_recent
  ON predictions (prediction_type, created_at DESC);

COMMENT ON TABLE predictions IS
  'Ogni predizione verificabile del sistema. Chiude il loop di apprendimento.';
COMMENT ON COLUMN predictions.prediction_type IS
  'Tipologia: ctl_weekly | race_time | ftp | threshold_pace | css | readiness_score | recovery_duration_h | compliance_pct | weekly_volume_min';


CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id UUID NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    actual_value NUMERIC NOT NULL,
    delta NUMERIC NOT NULL,                     -- actual - predicted
    delta_pct NUMERIC,                          -- (actual - predicted) / predicted * 100
    in_range BOOLEAN,                           -- true se actual è dentro range_low/high
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolution_source TEXT,                     -- es. auto_cron, manual_athlete, fitness_test_processor
    notes TEXT,
    metadata JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_outcomes_prediction_unique
  ON outcomes (prediction_id);  -- 1 outcome per prediction
CREATE INDEX IF NOT EXISTS idx_outcomes_recent
  ON outcomes (resolved_at DESC);

COMMENT ON TABLE outcomes IS
  'Risultato effettivo verificato per ogni prediction. delta_pct = bias del modello.';


-- View di comodo per analisi bias longitudinale
CREATE OR REPLACE VIEW prediction_accuracy AS
SELECT
  p.prediction_type,
  p.model_version,
  COUNT(o.id) AS n,
  ROUND(AVG(o.delta_pct)::numeric, 3) AS mean_delta_pct,
  ROUND(STDDEV(o.delta_pct)::numeric, 3) AS stddev_delta_pct,
  ROUND(AVG(ABS(o.delta_pct))::numeric, 3) AS mean_abs_delta_pct,
  ROUND(AVG(o.in_range::int)::numeric, 3) AS in_range_rate,
  MIN(p.created_at) AS first_prediction_at,
  MAX(o.resolved_at) AS last_outcome_at
FROM predictions p
JOIN outcomes o ON o.prediction_id = p.id
GROUP BY p.prediction_type, p.model_version;

COMMENT ON VIEW prediction_accuracy IS
  'Aggregato accuratezza per prediction_type + model_version. Usato per calibrazione bias.';

-- RLS: allinea al pattern single-user di schema.sql (deny-all anon, service_role bypassa).
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes    ENABLE ROW LEVEL SECURITY;
