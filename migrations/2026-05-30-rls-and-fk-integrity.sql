-- 2026-05-30 — RLS sulle tabelle scoperte + integrità FK (ON DELETE)
--
-- CONTESTO
--   sql/schema.sql abilita RLS su tutte le sue tabelle (design single-user:
--   "nessuna policy = solo service_role accede"). Le migration successive
--   (2026-05-14-*) hanno creato nuove tabelle SENZA abilitare RLS, lasciandole
--   esposte al ruolo `anon` via PostgREST sotto il default Supabase attuale.
--
--   Questa migration ri-allinea quelle tabelle al pattern deny-all-to-anon.
--   È anche la risposta corretta all'avviso Supabase del 30/05/2026
--   (Data API exposure): NON si concede GRANT al ruolo anon — si abilita RLS,
--   coerentemente col fatto che tutto il backend usa la service_role key
--   (che bypassa RLS/GRANT). L'app non è impattata a runtime; questo chiude
--   solo il gap di esposizione delle tabelle prive di RLS.
--
-- IDEMPOTENTE: rieseguibile senza errori.

-- ============================================================================
-- 1) RLS sulle 8 tabelle scoperte (deny-all per anon/authenticated)
-- ============================================================================
ALTER TABLE predictions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcomes         ENABLE ROW LEVEL SECURITY;
ALTER TABLE beliefs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE beliefs_history  ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE hypothesis_tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_audit   ENABLE ROW LEVEL SECURITY;
ALTER TABLE sent_reminders   ENABLE ROW LEVEL SECURITY;

-- Nessuna policy creata di proposito: senza policy l'accesso anon/authenticated
-- è negato; la service_role (usata da Python/MCP/Telegram) bypassa RLS.

-- ============================================================================
-- 2) Integrità referenziale: FK senza clausola ON DELETE
-- ============================================================================
-- Senza ON DELETE, cancellare un'attività/gara lascerebbe FK dangling o
-- bloccherebbe la delete (es. scripts/db_cleanup.py). Mettiamo SET NULL: il
-- riferimento è informativo/opzionale, non deve impedire il cleanup.
--
-- NB: i nomi constraint sono quelli auto-generati da Postgres (<tab>_<col>_fkey).
-- Se nella tua istanza differiscono, adatta i DROP. I DROP usano IF EXISTS,
-- quindi la migration resta sicura anche se un constraint non c'è.

-- physiology_zones.test_activity_id → activities(id)
ALTER TABLE physiology_zones
    DROP CONSTRAINT IF EXISTS physiology_zones_test_activity_id_fkey;
ALTER TABLE physiology_zones
    ADD CONSTRAINT physiology_zones_test_activity_id_fkey
    FOREIGN KEY (test_activity_id) REFERENCES activities(id) ON DELETE SET NULL;

-- planned_sessions.completed_activity_id → activities(id)
ALTER TABLE planned_sessions
    DROP CONSTRAINT IF EXISTS planned_sessions_completed_activity_id_fkey;
ALTER TABLE planned_sessions
    ADD CONSTRAINT planned_sessions_completed_activity_id_fkey
    FOREIGN KEY (completed_activity_id) REFERENCES activities(id) ON DELETE SET NULL;

-- mesocycles.target_race_id → races(id)
-- In schema.sql era dichiarata come UUID semplice (FK solo nel commento):
-- qui formalizziamo la foreign key con ON DELETE SET NULL.
ALTER TABLE mesocycles
    DROP CONSTRAINT IF EXISTS mesocycles_target_race_id_fkey;
ALTER TABLE mesocycles
    ADD CONSTRAINT mesocycles_target_race_id_fkey
    FOREIGN KEY (target_race_id) REFERENCES races(id) ON DELETE SET NULL;
