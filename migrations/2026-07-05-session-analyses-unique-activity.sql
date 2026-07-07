-- 2026-07-05 — session_analyses: unique su activity_id (M5)
--
-- CONTESTO
--   analyze_session() fa check-then-insert (select su activity_id, poi
--   insert) senza transazione: due job concorrenti (es. backfill-analyses.yml
--   lanciato a mano mentre gira ingest.yml, gruppi di concurrency diversi)
--   possono entrambi superare il check e inserire due righe per la stessa
--   attività — doppia chiamata LLM, doppio Telegram, doppia proposta di
--   modulazione. Solo un index non-unique esisteva.
--
-- IDEMPOTENTE: rieseguibile senza errori (ON CONFLICT DO NOTHING per righe
-- duplicate preesistenti, poi il constraint).

DELETE FROM session_analyses a USING session_analyses b
WHERE a.activity_id = b.activity_id AND a.id > b.id;

-- ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS non è sintassi valida in
-- Postgres (a differenza di ADD COLUMN IF NOT EXISTS) — DO block per l'idempotenza.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'session_analyses_activity_id_key'
  ) THEN
    ALTER TABLE session_analyses
      ADD CONSTRAINT session_analyses_activity_id_key UNIQUE (activity_id);
  END IF;
END $$;
