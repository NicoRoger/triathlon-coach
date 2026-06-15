-- Migration: Modulation source tracking + dismissed status (2026-06-15)
-- Additive e idempotente.
--
-- M1: colonna source — distingue modulazioni auto-generate (pipeline) da
--     quelle scritte esplicitamente dal coach. Default 'auto' per retro-compat.
-- M2: aggiunge 'dismissed' al CHECK di status (era mancante).
-- M3: indice composito per query bulk di cleanup.

-- M1: source column
ALTER TABLE plan_modulations
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'auto';

DO $$
BEGIN
    ALTER TABLE plan_modulations
        ADD CONSTRAINT plan_modulations_source_check
        CHECK (source IN ('auto', 'coach', 'athlete'));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- M2: allarga status CHECK per includere 'dismissed'
-- Rimuove il vincolo esistente (se presente) e lo ricrea con il nuovo valore.
ALTER TABLE plan_modulations DROP CONSTRAINT IF EXISTS plan_modulations_status_check;

DO $$
BEGIN
    ALTER TABLE plan_modulations
        ADD CONSTRAINT plan_modulations_status_check
        CHECK (status IN (
            'proposed', 'accepted', 'applied', 'partial', 'failed',
            'rejected', 'expired', 'discussing', 'dismissed'
        ));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- M3: indice composito per lookup bulk durante cleanup
CREATE INDEX IF NOT EXISTS idx_plan_modulations_status_proposed_at
    ON plan_modulations(status, proposed_at DESC);
