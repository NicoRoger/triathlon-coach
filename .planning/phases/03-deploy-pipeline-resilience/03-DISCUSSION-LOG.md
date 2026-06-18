# Phase 3: Deploy & Pipeline Resilience — Discussion Log

**Date:** 2026-06-06
**Status:** Complete → CONTEXT.md written

## Areas Discussed

### 1. Ordine operazioni deploy
- **Q:** Migrations manual vs script vs CLI?
- **A:** Dashboard Supabase SQL Editor — controllo diretto
- **Q:** Wrangler configurato?
- **A:** Sì, credenziali attive localmente

### 2. apply_accepted_modulations (DEPLOY-04)
- **Q:** Step separato in ingest.yml o inline?
- **A:** Step separato dopo blocco ingest
- **Q:** On failure: blocca o logga e continua?
- **A:** Logga e continua — ingest è più critico

### 3. Verifica deploy
- **Q:** Verifica migrazioni: script, manuale o log Actions?
- **A:** Script `verify_migrations.py` con query information_schema
- **Q:** Verifica bot: wrangler tail, test Telegram, o solo output deploy?
- **A:** Test manuale via chat Telegram

### 4. Brief idempotency (PIPELINE-04)
- **Q:** Check DB sent_briefs, KV Worker, o finestra temporale?
- **A:** Check DB su `bot_messages`/`sent_briefs` — persistente, no dipendenze KV

## Deferred Ideas
- Fix A1-A10 (ingest resilience) — Phase 7
- Fix K6-K9 (bot warnings) — future fasi
- DR restore L7, DST drift L5 — documentati
