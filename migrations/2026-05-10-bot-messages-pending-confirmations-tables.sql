-- Step 6.6: tabelle per reply threading e conferme azioni rischiose

CREATE TABLE IF NOT EXISTS bot_messages (
    id BIGSERIAL PRIMARY KEY,
    telegram_message_id BIGINT NOT NULL UNIQUE,
    chat_id BIGINT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    purpose TEXT NOT NULL,
    -- debrief_reminder | morning_brief | proactive_question | modulation_proposal
    -- race_week_brief | race_day_brief | pattern_observation
    -- status_response | budget_response | help | session_analysis | generic
    context_data JSONB,
    parent_workflow TEXT,
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bot_messages_telegram_id ON bot_messages(telegram_message_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_chat_purpose ON bot_messages(chat_id, purpose, sent_at DESC);

ALTER TABLE bot_messages ENABLE ROW LEVEL SECURITY;

-- pending_confirmations: conferma esplicita prima di salvare azioni rischiose
CREATE TABLE IF NOT EXISTS pending_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    chat_id BIGINT NOT NULL,
    original_message_id BIGINT NOT NULL,
    confirmation_message_id BIGINT NOT NULL,
    parsed_action TEXT NOT NULL,  -- log_injury | log_illness | modify_plan | classify
    parsed_data JSONB NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending | confirmed | rejected | corrected | expired
    resolved_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_pending_conf_chat ON pending_confirmations(chat_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_conf_conf_msg ON pending_confirmations(confirmation_message_id);

ALTER TABLE pending_confirmations ENABLE ROW LEVEL SECURITY;
