-- Migration: Fix planned_sessions UNIQUE constraint
-- Description: Adds a UNIQUE constraint on (planned_date, sport) to allow UPSERT operations.

ALTER TABLE planned_sessions
ADD CONSTRAINT unique_planned_date_sport UNIQUE (planned_date, sport);
