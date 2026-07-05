-- 2026-07-02 — daily_metrics: colonne Garmin training load mancanti dal DDL
--
-- CONTESTO
--   coach/analytics/daily.py SCRIVE e coach/planning/briefing.py LEGGE
--   garmin_acute_load / garmin_chronic_load / garmin_load_balance /
--   garmin_training_status, ma nessun DDL esisteva né in sql/schema.sql né
--   nelle migration: le colonne erano state applicate a mano in prod.
--   Un restore DR da schema.sql avrebbe fatto crashare il job analytics
--   al primo upsert su daily_metrics.
--
--   Tipi coerenti con i valori scritti da coach/analytics/daily.py:166-170:
--   round(float, 2) → NUMERIC per i tre load; training_status (stringa
--   Garmin, es. 'productive') → TEXT.
--
-- IDEMPOTENTE: rieseguibile senza errori.

ALTER TABLE daily_metrics
  ADD COLUMN IF NOT EXISTS garmin_acute_load NUMERIC,
  ADD COLUMN IF NOT EXISTS garmin_chronic_load NUMERIC,
  ADD COLUMN IF NOT EXISTS garmin_load_balance NUMERIC,
  ADD COLUMN IF NOT EXISTS garmin_training_status TEXT;

COMMENT ON COLUMN daily_metrics.garmin_acute_load IS
  'Garmin training load acuto (~7gg), da daily_wellness.training_load_acute';
COMMENT ON COLUMN daily_metrics.garmin_chronic_load IS
  'Garmin training load cronico (~28gg), da daily_wellness.training_load_chronic';
COMMENT ON COLUMN daily_metrics.garmin_load_balance IS
  'chronic - acute (positivo = fresco, coerente col segno del TSB)';
COMMENT ON COLUMN daily_metrics.garmin_training_status IS
  'Training status Garmin (productive, peaking, strained, ...)';
