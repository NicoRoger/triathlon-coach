-- Migration: Fix planned_sessions UNIQUE constraint
-- Description: Adds a UNIQUE constraint on (planned_date, sport) to allow UPSERT operations.
-- Audit 2026-06-01 (O3): reso idempotente — ADD CONSTRAINT fallisce su re-run se il
-- vincolo esiste già (README promette idempotenza). Guard via DO/EXCEPTION.

DO $$
BEGIN
    ALTER TABLE planned_sessions
        ADD CONSTRAINT unique_planned_date_sport UNIQUE (planned_date, sport);
EXCEPTION
    WHEN duplicate_table THEN NULL;  -- constraint già presente
    WHEN duplicate_object THEN NULL;
END $$;
