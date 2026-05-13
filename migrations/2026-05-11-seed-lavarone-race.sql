-- Seed: Lavarone Cross Sprint 2026 (gara A)
-- Necessario per briefing.py che ora legge da DB invece di hardcode.

INSERT INTO races (name, race_date, priority, distance, location)
VALUES ('Lavarone Cross Sprint', '2026-08-29', 'A', 'sprint', 'Lavarone')
ON CONFLICT DO NOTHING;
