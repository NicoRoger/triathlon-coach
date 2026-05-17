-- Fase 1.5 — Injury & illness severity
-- Aggiunge campi di severity, durata attesa e localizzazione corporea a subjective_log
-- per gestire infortuni e malattie con protocolli differenziati.

ALTER TABLE subjective_log
  ADD COLUMN IF NOT EXISTS severity TEXT
    CHECK (severity IN ('mild', 'moderate', 'severe')),
  ADD COLUMN IF NOT EXISTS expected_duration_days INTEGER
    CHECK (expected_duration_days IS NULL OR expected_duration_days > 0),
  ADD COLUMN IF NOT EXISTS body_location TEXT;

-- Indice per query filtrate per severity (es. dashboard, briefing)
CREATE INDEX IF NOT EXISTS idx_subjective_log_severity
  ON subjective_log (severity)
  WHERE severity IS NOT NULL;

COMMENT ON COLUMN subjective_log.severity IS
  'Gravità infortunio/malattia: mild (allenamento ok con cautela), moderate (mod./skip sessioni qualità), severe (stop sport coinvolto)';
COMMENT ON COLUMN subjective_log.expected_duration_days IS
  'Stima durata attesa in giorni (per protocolli return-to-play)';
COMMENT ON COLUMN subjective_log.body_location IS
  'Localizzazione corporea (es. spalla_dx, fascite, ginocchio_sx, gola, polmone)';
