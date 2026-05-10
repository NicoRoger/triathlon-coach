# Audit Security & Privacy

**Data:** 2026-05-09

## 1. Test Allow-List Bot Telegram
- **Sintomo:** Messaggi da chat ID sconosciute.
- **Esito Pre-Audit:** Il bot non faceva check del Chat ID dentro `handleCommand`. In teoria uno sconosciuto poteva inserire log nel database.
- **Fix (P1):** Aggiunto blocco formale in cima ad `handleCommand`: `if (chatId.toString() !== env.TELEGRAM_CHAT_ID) return;`. ✅ risolto.

## 2. Test Autenticazione MCP Worker
- **Check Authorization Header:** Il Worker `mcp-server` accetta le chiamate solo se la request contiene `Authorization: Bearer <API_KEY>` che matcha il secret.
- **Esito:** ✅ ok. Accesso negato a client non autorizzati.

## 3. Test Leak dei Secret
- Nessun `print()` espone i secret. Tutti i log passano attraverso la configurazione `logging` che non esegue il dump di payload grezzi di Supabase Request.
- `.env` è regolarmente ignorato da `.gitignore`.
- **Esito:** ✅ ok.

## 4. Input Validation (SQL Injection)
- I tool MCP passano i parametri come body JSON a Supabase via Rest API o Client Python `supabase-py`.
- Il driver PostgREST sanitizza l'input e fa il binding dei parametri nativamente, impedendo classiche query SQL Injection.
- Emoji e caratteri UTF-8 sono supportati (verificato in Step 1).
- **Esito:** ✅ ok.
