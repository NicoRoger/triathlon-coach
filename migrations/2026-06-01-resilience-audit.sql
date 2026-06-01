-- Migration: Resilience Audit 2026-06-01
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   O4 — races UNIQUE(name, race_date): impedisce il re-seed che duplica la gara A
--        (ON CONFLICT DO NOTHING del seed era un no-op senza target unique).
--   O5 — mesocycles.target_race_id FK → races(id) ON DELETE SET NULL (no orfani).
--   O6/D1 — plan_modulations.expires_at: consente la scadenza delle modulazioni
--        stantie (una proposta di lunedì non deve essere applicabile venerdì).
--        Default conservativo 48h; le righe esistenti restano NULL (mai scadono,
--        retro-compatibile). CONFERMARE la finestra di 48h con l'atleta.

-- ── O4: races UNIQUE(name, race_date) ───────────────────────────────────────
DO $$
BEGIN
    ALTER TABLE races ADD CONSTRAINT races_name_date_unique UNIQUE (name, race_date);
EXCEPTION
    WHEN duplicate_table THEN NULL;
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O5: mesocycles.target_race_id FK → races(id) ON DELETE SET NULL ──────────
DO $$
BEGIN
    ALTER TABLE mesocycles
        ADD CONSTRAINT mesocycles_target_race_fk
        FOREIGN KEY (target_race_id) REFERENCES races(id) ON DELETE SET NULL;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ── O6/D1: plan_modulations.expires_at ──────────────────────────────────────
ALTER TABLE plan_modulations
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Default per le NUOVE proposte (48h dalla creazione). Le righe storiche
-- restano NULL → l'enforcement nel codice (apply_modulation) le tratta come
-- "mai scadute" per retro-compatibilità.
ALTER TABLE plan_modulations
    ALTER COLUMN expires_at SET DEFAULT (NOW() + INTERVAL '48 hours');
