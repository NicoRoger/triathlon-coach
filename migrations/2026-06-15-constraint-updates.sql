-- Migration: active_constraints — symptom_status, history, note (2026-06-15)
-- Additive e idempotente.
--
-- M1: symptom_status — traccia evoluzione sintomatologica (symptomatic/asymptomatic/recovering)
-- M2: history JSONB — audit trail di ogni aggiornamento (chi/quando/cosa è cambiato)
-- M3: note TEXT — campo libero per note contestuali senza sovrascrivere description

ALTER TABLE active_constraints
    ADD COLUMN IF NOT EXISTS symptom_status TEXT CHECK (symptom_status IN ('symptomatic', 'asymptomatic', 'recovering'));

ALTER TABLE active_constraints
    ADD COLUMN IF NOT EXISTS history JSONB NOT NULL DEFAULT '[]';

ALTER TABLE active_constraints
    ADD COLUMN IF NOT EXISTS note TEXT;
