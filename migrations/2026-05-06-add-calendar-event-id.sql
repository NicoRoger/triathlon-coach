-- Migration: add calendar_event_id to planned_sessions
-- Data: 2026-05-06
-- Descrizione: Aggiunge colonna per memorizzare l'ID evento Google Calendar
--              associato a ciascuna sessione pianificata.
--
-- Esecuzione: copiare ed eseguire nel Supabase SQL Editor
-- (Project → SQL Editor → New Query → Incolla → Run)

ALTER TABLE planned_sessions
  ADD COLUMN IF NOT EXISTS calendar_event_id TEXT;

-- Indice opzionale per lookup rapido da calendar_event_id
CREATE INDEX IF NOT EXISTS idx_planned_sessions_calendar_event_id
  ON planned_sessions (calendar_event_id)
  WHERE calendar_event_id IS NOT NULL;
