-- 2026-06-01 — Aggiunge lo stato 'cancelled' a planned_sessions
--
-- CONTESTO
--   La skill delete_session prescriveva di "cancellare" una sessione settando
--   status='cancelled', ma:
--     1) commit_plan_change forzava sempre status='planned' (impossibile cambiarlo)
--     2) 'cancelled' non era nemmeno un valore valido: il CHECK constraint
--        ammetteva solo planned/completed/skipped/modified.
--   Risultato sul campo: il coach non riusciva a rimuovere sessioni duplicate
--   (es. il "CSS fantasma" del 02/06) e le neutralizzava goffamente.
--
--   Questa migration rende 'cancelled' un valore valido. Il nuovo tool
--   delete_session lo usa per la cancellazione soft (recuperabile, mantiene lo
--   storico piano-vs-eseguito); le viste del piano nascondono le cancelled.
--
-- IDEMPOTENTE: rieseguibile senza errori.

ALTER TABLE planned_sessions
    DROP CONSTRAINT IF EXISTS planned_sessions_status_check;

ALTER TABLE planned_sessions
    ADD CONSTRAINT planned_sessions_status_check
    CHECK (status IN ('planned', 'completed', 'skipped', 'modified', 'cancelled'));
