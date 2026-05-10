# Session Log — 10 maggio 2026 — Step 6.6: Bot Telegram robusto

## Obiettivo

Implementare reply threading nativo + conferma azioni rischiose + nuovi comandi per rendere il bot Telegram conversazionale e contestuale.

## Cosa è stato implementato

### Feature 1 — Reply Threading ✅

Il bot ora traccia ogni messaggio che invia in `bot_messages` (nuova tabella). Quando l'utente fa swipe-reply su un messaggio precedente, il bot:
- Recupera il contesto dalla tabella (purpose + context_data)
- Instrada il parsing al handler corretto in base al `purpose`:
  - `debrief_reminder` → parser debrief, salva come `evening_debrief`
  - `morning_brief` → salva come `brief_response`
  - `proactive_question` → salva come `proactive_response` con categoria
  - `modulation_proposal` → rimanda ai bottoni inline

**Infrastruttura**: `coach/utils/telegram_logger.py` (`send_and_log_message`) centralizza l'invio e il logging. Tutti i call site aggiornati: `briefing.py`, `modulation.py`, `proactive_questions.py`, `post_session_analysis.py`.

### Feature 2 — Conferma azioni rischiose ✅

Prima di salvare `injury_flag=true` o `illness_flag=true`, il bot chiede conferma esplicita con bottoni inline:
- `[✅ Sì]` → salva con flag
- `[✏️ Correggi]` → aspetta reply con correzione
- `[❌ Era altro]` → salva come `free_note` senza flag

Stato pending salvato in `pending_confirmations` (nuova tabella), scade automaticamente dopo 24h (cleanup domenicale).

### Feature 3 — /undo ✅

`/undo` mostra l'ultimo log degli ultimi 30 minuti e chiede conferma via bottoni. Su conferma, hard delete da `subjective_log`.

### Feature 4 — /history ✅

`/history`, `/history 7d`, `/history rpe`, `/history injury` — lista log recenti con filtri. Mostra data, tipo, RPE, flags, preview testo.

### Feature 5 — Help contestuale ✅

Se il parser non capisce il testo (nessun dato estratto), invece di salvare silenziosamente come `free_note`, chiede classificazione:
- `[📝 Nota libera]` `[🩹 Sintomo/dolore]` `[🎯 RPE post-sessione]`

### Feature 6 — Idempotenza e dedup ✅

- Dedup update_id già esistente — confermato funzionante
- **Nuovo**: dedup su `callback_query_id` con KV TTL 300s — previene doppio click su stesso bottone

### Feature 7 — Proactive question buttons ✅

Le domande proattive (Mar/Gio/Sab 18:00) ora hanno 3 bottoni inline:
- `[💬 Rispondo dopo]` `[🤐 Salta]` `[🚫 Disabilita oggi]`

"Disabilita oggi" scrive flag KV che dura fino a mezzanotte.

## File modificati

| File | Tipo modifica |
|------|--------------|
| `workers/telegram-bot/src/index.ts` | Riscritta da 504 → 590 righe con tutte le feature |
| `coach/utils/telegram_logger.py` | **NUOVO**: centralizza invio + logging bot_messages |
| `coach/planning/briefing.py` | `send_to_telegram()` ora usa `telegram_logger` |
| `coach/coaching/modulation.py` | `_send_modulation_telegram()` ora usa `telegram_logger` |
| `coach/coaching/proactive_questions.py` | `send_to_telegram()` → `telegram_logger` + bottoni inline |
| `coach/coaching/post_session_analysis.py` | `_send_analysis_telegram()` → `telegram_logger` |
| `scripts/send_debrief_reminder.py` | **NUOVO**: sostituisce il curl nel workflow |
| `.github/workflows/debrief-reminder.yml` | Convertito da curl a Python (checkout + pip + script) |
| `.github/workflows/db_cleanup.yml` | **NUOVO**: cleanup domenicale bot_messages + pending_confirmations |
| `migrations/2026-05-10-bot-messages-pending-confirmations-tables.sql` | **NUOVA** migration |
| `tests/test_telegram_advanced.py` | **NUOVO**: 18 test unitari (parser, threading, pending, dedup) |
| `docs/USER_GUIDE.md` | Aggiornata sezione bot con nuovi comandi + reply threading + conferme |
| `docs/SYSTEM_STATUS.md` | Aggiornata a Step 6.6, aggiunte 2 tabelle e 1 workflow |

## Cosa manca / rimandato

- **Pattern corrections**: tabella `pattern_corrections` non creata (rimanda a sessione successiva)
- **race_week_brief / race_day_brief**: non loggati in `bot_messages` (rimanda a quando viene integrata la race week)
- **Weekly-review reminder**: non aggiornato a `telegram_logger` (usa ancora curl diretto) — rimanda
- **Deploy Worker**: richiede `cd workers/telegram-bot && npx wrangler deploy` da terminale utente

## Setup richiesto

1. **Migration Supabase**: eseguire `migrations/2026-05-10-bot-messages-pending-confirmations-tables.sql`
2. **Deploy Worker**: `cd workers/telegram-bot && npx wrangler deploy`
3. Verifica: dopo il prossimo brief mattutino, `bot_messages` deve avere un record con `purpose='morning_brief'`
