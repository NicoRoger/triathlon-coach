-- Seed: Lavarone Cross Sprint 2026 (gara A)
-- Necessario per briefing.py che ora legge da DB invece di hardcode.

-- Audit O4: target esplicito (name, race_date). Richiede il vincolo
-- races_name_date_unique (migration 2026-06-01-resilience-audit.sql). Senza
-- quel vincolo l'ON CONFLICT senza target NON deduplicava e ri-eseguire il
-- seed duplicava la gara A. Esegui PRIMA la migration 2026-06-01.
INSERT INTO races (name, race_date, priority, distance, location)
VALUES ('Lavarone Cross Sprint', '2026-08-29', 'A', 'sprint', 'Lavarone')
ON CONFLICT (name, race_date) DO NOTHING;
