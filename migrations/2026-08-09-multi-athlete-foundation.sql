-- Migration: fondazione multi-atleta (2026-08-09)
-- Additiva e idempotente. NON rompe il sistema esistente: tutte le righe
-- attuali vengono attribuite all'atleta esistente e i job continuano a
-- funzionare anche prima che il codice sia stato aggiornato.
--
-- CONTESTO: il sistema nasce single-athlete per scelta esplicita ("nessun
-- user_id nello schema"). Ora deve seguire una seconda atleta con anamnesi,
-- routine, obiettivi e fonte dati propri (Strava invece di Garmin).
--
-- IL PUNTO CHE ROMPE IN SILENZIO: diversi vincoli UNIQUE sono globali e non
-- contengono l'atleta — `daily_wellness.date`, `daily_metrics.date`,
-- `beliefs.belief_key`, `(trigger_type, sent_date)`, ecc. Senza toccarli, la
-- seconda atleta non riuscirebbe a salvare NEMMENO una giornata di wellness:
-- collisione sul vincolo con la riga dell'altro atleta, stesso giorno. Qui
-- ogni vincolo viene ricostruito includendo athlete_id.

-- ============================================================================
-- 1. Anagrafica atleti
-- ============================================================================

CREATE TABLE IF NOT EXISTS athletes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,      -- identificatore stabile per env/config
    timezone        TEXT NOT NULL DEFAULT 'Europe/Rome',
    telegram_chat_id BIGINT UNIQUE,            -- routing messaggi in uscita/entrata
    data_source     TEXT NOT NULL DEFAULT 'garmin'
                    CHECK (data_source IN ('garmin', 'strava', 'manual')),
    -- Strava non espone HRV, sonno, body battery né resting HR: per gli
    -- atleti su Strava il readiness va ricalibrato su TSB + soggettivo.
    -- Questo flag lo rende esplicito al layer analytics invece di lasciarlo
    -- dedurre da dati mancanti (che sono indistinguibili da un sync rotto).
    has_wellness_data BOOLEAN NOT NULL DEFAULT true,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE athletes IS
    'Anagrafica atleti seguiti. slug è la chiave usata da env/config dei job.';
COMMENT ON COLUMN athletes.has_wellness_data IS
    'false per fonti senza HRV/sonno (Strava): il readiness si ricalibra su TSB + soggettivo.';

-- Atleta esistente. Lo slug è stabile e usato dai workflow.
INSERT INTO athletes (name, slug, data_source, has_wellness_data)
SELECT 'Nicolò Ruggero', 'nicolo', 'garmin', true
WHERE NOT EXISTS (SELECT 1 FROM athletes WHERE slug = 'nicolo');

-- ============================================================================
-- 2. athlete_id sulle tabelle con dati d'atleta
-- ============================================================================
-- Aggiunta NULL → backfill → NOT NULL: così la migration non fallisce su
-- tabelle già popolate e resta rieseguibile.

DO $$
DECLARE
    t TEXT;
    nicolo UUID;
    per_athlete_tables TEXT[] := ARRAY[
        'activities', 'daily_wellness', 'daily_metrics', 'subjective_log',
        'planned_sessions', 'mesocycles', 'races', 'physiology_zones',
        'session_analyses', 'plan_modulations', 'beliefs', 'beliefs_history',
        'active_constraints', 'predictions', 'outcomes', 'recommendations',
        'hypothesis_tests', 'decision_audit', 'sent_reminders',
        'bot_messages', 'pending_confirmations'
    ];
BEGIN
    SELECT id INTO nicolo FROM athletes WHERE slug = 'nicolo';

    FOREACH t IN ARRAY per_athlete_tables LOOP
        -- Salta le tabelle non ancora create (migrations applicate parzialmente)
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                       WHERE table_schema = 'public' AND table_name = t) THEN
            RAISE NOTICE 'Tabella % assente, skip', t;
            CONTINUE;
        END IF;

        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS athlete_id UUID REFERENCES athletes(id)', t
        );
        EXECUTE format('UPDATE %I SET athlete_id = $1 WHERE athlete_id IS NULL', t) USING nicolo;
        EXECUTE format('ALTER TABLE %I ALTER COLUMN athlete_id SET NOT NULL', t);
        -- Default all'atleta esistente: il codice non ancora aggiornato
        -- continua a scrivere righe valide invece di fallire con NOT NULL.
        -- Va RIMOSSO quando tutti i writer passano athlete_id esplicito.
        EXECUTE format('ALTER TABLE %I ALTER COLUMN athlete_id SET DEFAULT $1', t)
            USING nicolo;
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS idx_%s_athlete ON %I (athlete_id)', t, t
        );
        RAISE NOTICE 'athlete_id aggiunto a %', t;
    END LOOP;
END $$;

-- ============================================================================
-- 3. Vincoli UNIQUE ricostruiti con athlete_id
-- ============================================================================
-- Senza questo blocco la seconda atleta collide con la prima su ogni chiave
-- basata su data o su nome naturale.

-- daily_wellness.date (era UNIQUE globale)
ALTER TABLE daily_wellness DROP CONSTRAINT IF EXISTS daily_wellness_date_key;
DO $$ BEGIN
    ALTER TABLE daily_wellness ADD CONSTRAINT daily_wellness_athlete_date_key
        UNIQUE (athlete_id, date);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- daily_metrics.date
ALTER TABLE daily_metrics DROP CONSTRAINT IF EXISTS daily_metrics_date_key;
DO $$ BEGIN
    ALTER TABLE daily_metrics ADD CONSTRAINT daily_metrics_athlete_date_key
        UNIQUE (athlete_id, date);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- beliefs.belief_key (una belief su Nicolò non deve bloccare la stessa
-- chiave sull'altra atleta: sono apprendimenti separati)
ALTER TABLE beliefs DROP CONSTRAINT IF EXISTS beliefs_belief_key_key;
DO $$ BEGIN
    ALTER TABLE beliefs ADD CONSTRAINT beliefs_athlete_key_key
        UNIQUE (athlete_id, belief_key);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- physiology_zones (discipline, valid_from, method)
ALTER TABLE physiology_zones DROP CONSTRAINT IF EXISTS physiology_zones_discipline_valid_from_method_key;
ALTER TABLE physiology_zones DROP CONSTRAINT IF EXISTS physiology_zones_unique_test;
DO $$ BEGIN
    ALTER TABLE physiology_zones ADD CONSTRAINT physiology_zones_athlete_test_key
        UNIQUE (athlete_id, discipline, valid_from, method);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- planned_sessions (planned_date, sport, session_type)
ALTER TABLE planned_sessions DROP CONSTRAINT IF EXISTS planned_sessions_planned_date_sport_session_type_key;
ALTER TABLE planned_sessions DROP CONSTRAINT IF EXISTS planned_sessions_date_sport_type_key;
DO $$ BEGIN
    ALTER TABLE planned_sessions ADD CONSTRAINT planned_sessions_athlete_slot_key
        UNIQUE (athlete_id, planned_date, sport, session_type);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- races (name, race_date)
ALTER TABLE races DROP CONSTRAINT IF EXISTS races_name_race_date_key;
DO $$ BEGIN
    ALTER TABLE races ADD CONSTRAINT races_athlete_name_date_key
        UNIQUE (athlete_id, name, race_date);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- mesocycles.start_date
ALTER TABLE mesocycles DROP CONSTRAINT IF EXISTS mesocycles_start_date_key;
DO $$ BEGIN
    ALTER TABLE mesocycles ADD CONSTRAINT mesocycles_athlete_start_key
        UNIQUE (athlete_id, start_date);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- sent_reminders (trigger_type, sent_date) — era un indice unique
DROP INDEX IF EXISTS idx_sent_reminders_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_reminders_athlete_unique
    ON sent_reminders (athlete_id, trigger_type, sent_date);

-- active_constraints: unique parziale sui vincoli ATTIVI
DROP INDEX IF EXISTS active_constraints_injury_discipline_active;
CREATE UNIQUE INDEX IF NOT EXISTS active_constraints_athlete_active_key
    ON active_constraints (athlete_id, type, discipline)
    WHERE resolved_at IS NULL;

-- ============================================================================
-- 4. Attribuzione costi (nessun vincolo: il budget resta condiviso)
-- ============================================================================
ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS athlete_id UUID REFERENCES athletes(id);
COMMENT ON COLUMN api_usage.athlete_id IS
    'Attribuzione costi per atleta. NULL = job di sistema. Il cap mensile resta GLOBALE.';

-- NB: `health` NON riceve athlete_id. I componenti per-atleta si distinguono
-- già per nome (garmin_sync per chi usa Garmin, strava_sync per chi usa
-- Strava) e il watchdog li tratta separatamente; introdurre una chiave
-- composita richiederebbe un sentinel per i job di sistema, che è peggio.
