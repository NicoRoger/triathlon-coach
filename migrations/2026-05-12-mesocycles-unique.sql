-- Add UNIQUE constraint on mesocycles(start_date) for upsert idempotency.
-- Prevents duplicate mesocycles starting on the same date when commit_mesocycle
-- is called more than once (e.g. weekly review re-run).
ALTER TABLE mesocycles ADD CONSTRAINT mesocycles_start_date_unique UNIQUE (start_date);
