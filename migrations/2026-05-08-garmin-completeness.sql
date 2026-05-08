-- ============================================================================
-- Migration: Garmin data completeness — Step 5.1 (8 maggio 2026)
-- ============================================================================
-- Aggiunge colonne per dati Garmin ad alto valore non ancora estratti:
--   - daily_wellness.training_readiness_score (da get_training_readiness)
--   - daily_wellness.avg_sleep_stress (da sleep.dailySleepDTO)
--   - activities.splits (da get_activity_splits)
--   - activities.weather (da get_activity_weather)
-- ============================================================================

-- daily_wellness: training readiness score Garmin (0-100)
ALTER TABLE daily_wellness
    ADD COLUMN IF NOT EXISTS training_readiness_score SMALLINT;

-- daily_wellness: stress medio durante il sonno
ALTER TABLE daily_wellness
    ADD COLUMN IF NOT EXISTS avg_sleep_stress NUMERIC;

-- activities: split per km/lap (array di oggetti con pace, HR, elevation, ecc.)
ALTER TABLE activities
    ADD COLUMN IF NOT EXISTS splits JSONB;

-- activities: condizioni meteo durante l'attività (temperatura, vento, umidità, ecc.)
ALTER TABLE activities
    ADD COLUMN IF NOT EXISTS weather JSONB;

-- daily_metrics: Garmin training readiness per aggregazione
-- (già abbiamo garmin_acute/chronic/balance/status in daily_metrics, 
--  aggiungiamo readiness Garmin per confronto col nostro)
ALTER TABLE daily_metrics
    ADD COLUMN IF NOT EXISTS garmin_training_readiness SMALLINT;
