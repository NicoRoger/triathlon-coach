-- Fase 2.7 — Multi-race architecture
-- Aggiunge campo season_year a mesocycles e races per gestire stagioni multiple
-- nel lungo termine (no Lavarone-specific code).

ALTER TABLE mesocycles
  ADD COLUMN IF NOT EXISTS season_year INTEGER;

ALTER TABLE races
  ADD COLUMN IF NOT EXISTS season_year INTEGER;

-- Backfill: deduce season_year da start_date (mesocycles) e race_date (races)
UPDATE mesocycles SET season_year = EXTRACT(YEAR FROM start_date)::int
WHERE season_year IS NULL;

UPDATE races SET season_year = EXTRACT(YEAR FROM race_date)::int
WHERE season_year IS NULL;

-- Indici per query stagione-specifica
CREATE INDEX IF NOT EXISTS idx_mesocycles_season
  ON mesocycles (season_year, start_date);
CREATE INDEX IF NOT EXISTS idx_races_season_priority
  ON races (season_year, priority, race_date);

COMMENT ON COLUMN mesocycles.season_year IS
  'Anno della stagione (default = YEAR(start_date)). Permette di gestire multi-anno.';
COMMENT ON COLUMN races.season_year IS
  'Anno della stagione (default = YEAR(race_date)). Permette di gestire multi-anno.';
