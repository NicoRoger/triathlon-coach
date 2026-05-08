-- ============================================================================
-- Migration: Step 6 — Coach Reattivo Continuo (8 maggio 2026)
-- ============================================================================
-- Nuove tabelle per coaching AI proattivo:
--   1. api_usage: tracking costi API Anthropic
--   2. session_analyses: analisi AI post-sessione
--   3. plan_modulations: proposte modulazione mid-week
-- ============================================================================

-- 1. API Usage tracking
CREATE TABLE IF NOT EXISTS api_usage (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd_estimated NUMERIC(8,4) NOT NULL,
    success BOOLEAN NOT NULL,
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_usage_purpose ON api_usage(purpose);

-- 2. Session Analyses
CREATE TABLE IF NOT EXISTS session_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id TEXT NOT NULL,
    analysis_text TEXT NOT NULL,
    suggested_actions JSONB,
    model_used TEXT,
    cost_usd NUMERIC(8,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_analyses_activity ON session_analyses(activity_id);

-- 3. Plan Modulations
CREATE TABLE IF NOT EXISTS plan_modulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposed_at TIMESTAMPTZ DEFAULT NOW(),
    trigger_event TEXT NOT NULL,
    trigger_data JSONB,
    proposed_changes JSONB NOT NULL,
    status TEXT DEFAULT 'proposed',
    resolved_at TIMESTAMPTZ,
    telegram_message_id BIGINT
);
CREATE INDEX IF NOT EXISTS idx_plan_modulations_status ON plan_modulations(status);
