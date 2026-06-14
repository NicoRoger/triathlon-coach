-- Migration: Physiological Adaptation Intelligence 2026-06-08
-- Additive e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- Copre:
--   Phase 6 — ADAPT-01: colonne fatigue_type, fatigue_confidence, sport su session_analyses
--             Classificazione deterministica cedimento muscolare vs cardiovascolare
--   Phase 6 — ADAPT-02: seed belief "endurance_failure_type" (endurance puro, cedimento muscolare first)
--             Basato su profilo atleta CLAUDE.md §2 + storico élite 2021-2022

-- ── ADAPT-01: colonne per classificazione tipo di cedimento ─────────────────
-- fatigue_type: risultato classificazione deterministica (classify_fatigue_type() in analytics)
-- fatigue_confidence: score di confidenza 0-1 per il tipo classificato
-- sport: disciplina dell'attività analizzata (evita JOIN con activities per last_fatigue_by_sport)

ALTER TABLE session_analyses
    ADD COLUMN IF NOT EXISTS fatigue_type TEXT CHECK (
        fatigue_type IN ('muscular', 'cardiovascular', 'mixed', 'insufficient_data')
    ),
    ADD COLUMN IF NOT EXISTS fatigue_confidence FLOAT CHECK (
        fatigue_confidence IS NULL OR (fatigue_confidence >= 0 AND fatigue_confidence <= 1)
    ),
    ADD COLUMN IF NOT EXISTS sport TEXT;

-- ── ADAPT-02: seed belief "endurance puro, cedimento muscolare first" ────────
-- Schema beliefs da migrations/2026-05-14-cognitive-mvp.sql:
--   belief_key (UNIQUE), belief_text, confidence, evidence_n, status,
--   source, source_metadata JSONB, last_reinforced_at, first_observed_at
--
-- Note: evidence_note è un campo informale — va dentro source_metadata JSONB (Pitfall 3).
-- Il belief entra nel normale lifecycle Bayesian: reinforce_belief/contradict_belief lo
-- aggiornano come ogni altro belief (D-08). Non è immutabile.
-- ON CONFLICT (belief_key) DO NOTHING: idempotenza garantita al re-run (Pitfall 5).

INSERT INTO beliefs (
    belief_key, belief_text, confidence, evidence_n, status,
    source, source_metadata, last_reinforced_at, first_observed_at
)
VALUES (
    'endurance_failure_type',
    'Nicolò è atleta endurance puro: primo cedimento muscolare, non cardiovascolare. HR rimane stabile anche ad alta intensità; il cedimento è al tono muscolare.',
    0.75,
    8,
    'validated_belief',
    'manual_seed',
    '{"evidence_note": "Basato su CLAUDE.md §2: profilo atleta, confermato da storico élite 2021-2022 (114 sessioni)"}'::jsonb,
    NOW(),
    NOW()
) ON CONFLICT (belief_key) DO NOTHING;
