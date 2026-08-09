-- Migration: allarga plan_modulations.source ai valori realmente scritti dal codice
-- Additiva e idempotente.
--
-- CAUSA: la migration 2026-06-15 ha introdotto
--     CHECK (source IN ('auto', 'coach', 'athlete'))
-- ma il codice scrive etichette di PROVENIENZA più fini:
--     test_scheduler          → coach/coaching/test_scheduler.py:225, test_prediction.py:242
--     pattern_extraction_job  → coach/coaching/pattern_extraction.py:275,300
--
-- EFFETTO OSSERVATO: dal 2026-07-12 il workflow pattern-extraction (domenicale)
-- moriva con 23514 allo step "Schedule fitness tests", cioè il TERZO di otto.
-- Tutti gli step successivi non venivano eseguiti: sync beliefs, decay,
-- rigenerazione anamnesi, progress tracker e commit. Per 4 domeniche di fila:
-- docs/ fermo al 2026-07-05, nessun test fitness più proposto, nessuna belief
-- consolidata.
--
-- SCELTA: allargare il vincolo invece di annacquare i valori a 'auto'. Le
-- etichette identificano QUALE automatismo ha prodotto la proposta, che è
-- esattamente l'informazione che serve per l'audit; comprimerle a 'auto' la
-- distruggerebbe. 'auto' resta il default per retro-compatibilità.

ALTER TABLE plan_modulations DROP CONSTRAINT IF EXISTS plan_modulations_source_check;

DO $$
BEGIN
    ALTER TABLE plan_modulations
        ADD CONSTRAINT plan_modulations_source_check
        CHECK (source IN (
            'auto',                    -- pipeline post-sessione (default storico)
            'coach',                   -- decisione esplicita del coach via MCP
            'athlete',                 -- richiesta diretta dell'atleta
            'test_scheduler',          -- test fitness scaduto (Phase 2.6)
            'pattern_extraction_job'   -- progressione da pattern settimanali
        ));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
