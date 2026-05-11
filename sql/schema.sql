-- ============================================================================
-- Triathlon Coach AI — Supabase schema v0.1
-- ============================================================================
-- Convenzioni:
--   - Tutti i timestamp in UTC (TIMESTAMPTZ)
--   - Ogni tabella ha created_at e updated_at
--   - RLS attivo, policy: solo proprietario (single-user system)
--   - Naming: snake_case, plurale per tabelle
-- ============================================================================

-- Estensioni
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- ATTIVITÀ (oggettive, da Garmin/Strava)
-- ============================================================================
CREATE TABLE activities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id     TEXT NOT NULL,                  -- es. garmin_<id> o strava_<id>
    source          TEXT NOT NULL CHECK (source IN ('garmin', 'strava', 'manual')),
    sport           TEXT NOT NULL CHECK (sport IN ('swim', 'bike', 'run', 'brick', 'strength', 'other')),
    started_at      TIMESTAMPTZ NOT NULL,
    duration_s      INTEGER NOT NULL,
    distance_m      NUMERIC,
    elevation_gain_m NUMERIC,

    -- Metriche cardio
    avg_hr          INTEGER,
    max_hr          INTEGER,
    hr_zones_s      JSONB,        -- {"z1": 600, "z2": 1200, ...}

    -- Metriche potenza/passo
    avg_power_w     NUMERIC,
    np_w            NUMERIC,      -- normalized power (bici)
    avg_pace_s_per_km NUMERIC,    -- corsa
    avg_pace_s_per_100m NUMERIC,  -- nuoto

    -- Carico
    tss             NUMERIC,      -- training stress score
    if_value        NUMERIC,      -- intensity factor
    rpe             SMALLINT CHECK (rpe BETWEEN 1 AND 10),  -- soggettivo, popolato post-debrief

    -- Raw payload per riprocessing
    raw_payload     JSONB,

    -- Garmin completeness Step 5.1
    splits          JSONB,        -- split per km/lap (get_activity_splits)
    weather         JSONB,        -- condizioni meteo (get_activity_weather)

    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (external_id, source)
);

CREATE INDEX idx_activities_started_at ON activities (started_at DESC);
CREATE INDEX idx_activities_sport_date ON activities (sport, started_at DESC);

-- ============================================================================
-- WELLNESS GIORNALIERO (Garmin morning data)
-- ============================================================================
CREATE TABLE daily_wellness (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date            DATE NOT NULL UNIQUE,

    -- HRV
    hrv_rmssd       NUMERIC,
    hrv_status      TEXT,         -- balanced / unbalanced / low

    -- Sleep
    sleep_score     SMALLINT,
    sleep_total_s   INTEGER,
    sleep_deep_s    INTEGER,
    sleep_rem_s     INTEGER,
    sleep_efficiency NUMERIC,

    -- Body battery / stress
    body_battery_min SMALLINT,
    body_battery_max SMALLINT,
    stress_avg      SMALLINT,

    -- Resting
    resting_hr      INTEGER,

    -- Garmin training metrics
    training_status TEXT,         -- productive / maintaining / overreaching / unproductive
    training_load_acute  NUMERIC, -- 7d
    training_load_chronic NUMERIC, -- 28d
    vo2max_run      NUMERIC,
    vo2max_bike     NUMERIC,

    -- Garmin completeness Step 5.1
    training_readiness_score SMALLINT,
    avg_sleep_stress NUMERIC,

    raw_payload     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_daily_wellness_date ON daily_wellness (date DESC);

-- ============================================================================
-- LOG SOGGETTIVO (RPE, dolori, malattia, note libere)
-- ============================================================================
CREATE TABLE subjective_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activity_id     UUID REFERENCES activities(id) ON DELETE SET NULL,

    kind            TEXT NOT NULL CHECK (kind IN (
        'post_session', 'morning', 'evening_debrief',
        'illness', 'injury', 'free_note'
    )),

    rpe             SMALLINT CHECK (rpe BETWEEN 1 AND 10),
    sleep_quality   SMALLINT CHECK (sleep_quality BETWEEN 1 AND 10),  -- pre-orologio, soggettivo
    motivation      SMALLINT CHECK (motivation BETWEEN 1 AND 10),
    soreness        SMALLINT CHECK (soreness BETWEEN 0 AND 10),

    -- Sintomi specifici (booleani)
    illness_flag    BOOLEAN DEFAULT FALSE,
    illness_details TEXT,
    injury_flag     BOOLEAN DEFAULT FALSE,
    injury_details  TEXT,
    injury_location TEXT,

    -- Testo libero (parsato da bot Telegram)
    raw_text        TEXT,
    parsed_data     JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subjective_log_logged_at ON subjective_log (logged_at DESC);
CREATE INDEX idx_subjective_log_activity ON subjective_log (activity_id);

-- ============================================================================
-- ZONE FISIOLOGICHE (versionate, mai sovrascritte)
-- ============================================================================
CREATE TABLE physiology_zones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    discipline      TEXT NOT NULL CHECK (discipline IN ('swim', 'bike', 'run')),
    valid_from      DATE NOT NULL,
    valid_to        DATE,             -- NULL = corrente

    -- Bici
    ftp_w           NUMERIC,
    -- Corsa
    threshold_pace_s_per_km NUMERIC,
    -- Nuoto
    css_pace_s_per_100m NUMERIC,
    -- HR
    lthr            INTEGER,          -- lactate threshold HR
    hr_max          INTEGER,

    -- Test source
    test_activity_id UUID REFERENCES activities(id),
    method          TEXT,             -- '20min_test', 'ramp', 'css_400_200', 'estimated'
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_zones_discipline_valid ON physiology_zones (discipline, valid_from DESC);

-- ============================================================================
-- METRICHE CALCOLATE (PMC, readiness, snapshot daily)
-- ============================================================================
CREATE TABLE daily_metrics (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date            DATE NOT NULL UNIQUE,

    -- PMC (Performance Management Chart)
    ctl             NUMERIC,    -- chronic training load (42d EWMA)
    atl             NUMERIC,    -- acute training load (7d EWMA)
    tsb             NUMERIC,    -- training stress balance (CTL - ATL)
    daily_tss       NUMERIC,    -- somma TSS del giorno

    -- Per disciplina (utile per polarized analysis)
    ctl_swim        NUMERIC,
    ctl_bike        NUMERIC,
    ctl_run         NUMERIC,

    -- HRV trend
    hrv_z_score     NUMERIC,    -- z-score vs baseline 28d
    hrv_baseline_28d NUMERIC,
    hrv_baseline_28d_sd NUMERIC,

    -- Readiness composito
    readiness_score SMALLINT,   -- 0-100
    readiness_label TEXT,       -- ready / caution / rest
    readiness_factors JSONB,    -- {"hrv": 75, "sleep": 80, "tsb": 60, ...}

    -- Flag attivi
    flags           TEXT[],     -- ['fatigue_warning', 'illness_flag', ...]

    -- Garmin training readiness Step 5.1
    garmin_training_readiness SMALLINT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_daily_metrics_date ON daily_metrics (date DESC);

-- ============================================================================
-- PIANIFICAZIONE (proiezione di plans/*.yaml in repo)
-- ============================================================================
CREATE TABLE mesocycles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    phase           TEXT NOT NULL CHECK (phase IN ('base', 'build', 'specific', 'peak', 'taper', 'recovery')),
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    target_race_id  UUID,             -- FK su races
    weekly_pattern  JSONB,             -- pattern carico/scarico
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE planned_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mesocycle_id    UUID REFERENCES mesocycles(id) ON DELETE CASCADE,
    planned_date    DATE NOT NULL,
    sport           TEXT NOT NULL,
    session_type    TEXT,             -- LSD, threshold, vo2max, race_pace, recovery, ...
    duration_s      INTEGER,
    target_tss      NUMERIC,
    target_zones    JSONB,             -- {"z2": 0.7, "z4": 0.2, ...}
    description     TEXT,              -- prosa per atleta
    structured      JSONB,             -- workout strutturato (per esportazione FIT futura)
    status          TEXT DEFAULT 'planned' CHECK (status IN ('planned', 'completed', 'skipped', 'modified')),
    completed_activity_id UUID REFERENCES activities(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_planned_sessions_date ON planned_sessions (planned_date);

-- ============================================================================
-- GARE
-- ============================================================================
CREATE TABLE races (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    race_date       DATE NOT NULL,
    race_tz         TEXT NOT NULL DEFAULT 'Europe/Rome',
    distance        TEXT,             -- 'sprint', 'olympic', '70.3', 'ironman', 'custom'
    location        TEXT,
    priority        TEXT CHECK (priority IN ('A', 'B', 'C')),
    target_time_s   INTEGER,
    target_position TEXT,
    actual_time_s   INTEGER,
    actual_position TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- COACHING AI (aggiunto con migration 2026-05-08-step6-tables)
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_usage (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ DEFAULT NOW(),
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    purpose             TEXT NOT NULL,
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cost_usd_estimated  NUMERIC(8,4) NOT NULL,
    success             BOOLEAN NOT NULL,
    metadata            JSONB
);
CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_usage_purpose   ON api_usage(purpose);

CREATE TABLE IF NOT EXISTS session_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id     TEXT NOT NULL,
    analysis_text   TEXT NOT NULL,
    suggested_actions JSONB,
    model_used      TEXT,
    cost_usd        NUMERIC(8,4),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_analyses_activity ON session_analyses(activity_id);

CREATE TABLE IF NOT EXISTS plan_modulations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposed_at     TIMESTAMPTZ DEFAULT NOW(),
    trigger_event   TEXT NOT NULL,
    trigger_data    JSONB,
    proposed_changes JSONB NOT NULL,
    status          TEXT DEFAULT 'proposed',
    resolved_at     TIMESTAMPTZ,
    telegram_message_id BIGINT
);
CREATE INDEX IF NOT EXISTS idx_plan_modulations_status ON plan_modulations(status);

-- ============================================================================
-- HEALTH (system status per watchdog)
-- ============================================================================
CREATE TABLE health (
    component       TEXT PRIMARY KEY,         -- 'garmin_sync', 'strava_sync', 'briefing', ...
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    failure_count   INTEGER DEFAULT 0,
    last_error      TEXT,
    metadata        JSONB,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bootstrap rows
INSERT INTO health (component) VALUES
    ('garmin_sync'), ('strava_sync'), ('briefing_morning'),
    ('debrief_evening'), ('analytics_daily'), ('dr_snapshot');

-- ============================================================================
-- TRIGGER updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN
        ('activities','daily_wellness','daily_metrics','mesocycles','planned_sessions','health')
    LOOP
        EXECUTE format('CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I
                        FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at()', t, t);
    END LOOP;
END $$;

-- ============================================================================
-- RLS — single user, deny all by default, service_role bypassa
-- ============================================================================
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_wellness ENABLE ROW LEVEL SECURITY;
ALTER TABLE subjective_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE physiology_zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE mesocycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE planned_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE races ENABLE ROW LEVEL SECURITY;
ALTER TABLE health ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_modulations ENABLE ROW LEVEL SECURITY;

-- Per single-user: nessuna policy = solo service_role accede.
-- Se in futuro vorrai accesso autenticato lato Worker, aggiungi policy specifica.
