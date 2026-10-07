-- Migration: token di servizio persistiti tra i run (2026-10-06)
-- Additiva e idempotente. Esegui una volta nel SQL editor di Supabase.
--
-- PERCHÉ: garminconnect >= 0.3 usa token DI con refresh token a ROTAZIONE
-- (ogni refresh restituisce un refresh token nuovo e invalida il vecchio).
-- L'ingest gira su GitHub Actions: ripristinava i token da GARMIN_SESSION_JSON
-- in una cartella temporanea, il refresh scriveva i token nuovi lì e la
-- cartella spariva a fine job. Al run successivo si ripartiva dal refresh
-- token del secret, ormai invalidato → 401 "Failed to retrieve social
-- profile" a ogni run (rotto dal 30/09/2026, 57 tentativi falliti).
-- Qui l'ingest salva i token aggiornati dopo ogni login e li rilegge al run
-- successivo, scegliendo sempre il più recente tra questa tabella e il secret.
--
-- Contiene credenziali: escluso di proposito dagli snapshot DR
-- (tests/test_dr_coverage.py → INTENTIONALLY_EXCLUDED).

CREATE TABLE IF NOT EXISTS service_tokens (
    name        TEXT PRIMARY KEY,          -- es. 'garmin:nicolo'
    payload     TEXT NOT NULL,             -- JSON serializzato dalla libreria
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE service_tokens IS
    'Token OAuth di servizi esterni aggiornati dai job (refresh a rotazione). Solo service_role.';

-- RLS: solo service_role. Nessuna policy per anon/authenticated = zero righe.
ALTER TABLE service_tokens ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    CREATE POLICY "service_role_full_access" ON service_tokens
        FOR ALL TO service_role USING (true) WITH CHECK (true);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
