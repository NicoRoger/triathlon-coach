-- Fase 1.6 — Sent reminders deduplication
-- Traccia i reminder proattivi inviati per evitare doppi reminder lo stesso giorno
-- per lo stesso trigger.

CREATE TABLE IF NOT EXISTS sent_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_type TEXT NOT NULL,           -- es. weekly_review, mesocycle_end, race_t14
    sent_date DATE NOT NULL,              -- giorno locale (Europe/Rome) — chiave deduplica
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_id BIGINT,                    -- Telegram message_id se disponibile
    context JSONB                          -- payload con dati specifici trigger
);

-- Unique constraint per garantire 1 reminder/trigger/giorno
CREATE UNIQUE INDEX IF NOT EXISTS idx_sent_reminders_unique
  ON sent_reminders (trigger_type, sent_date);

CREATE INDEX IF NOT EXISTS idx_sent_reminders_recent
  ON sent_reminders (sent_at DESC);

COMMENT ON TABLE sent_reminders IS
  'Deduplica reminder proattivi: trigger_type + sent_date = unique.';
COMMENT ON COLUMN sent_reminders.context IS
  'Dati contestuali del reminder (es. race_id, days_remaining, mesocycle_id)';

-- RLS: allinea al pattern single-user di schema.sql (deny-all anon, service_role bypassa).
ALTER TABLE sent_reminders ENABLE ROW LEVEL SECURITY;
