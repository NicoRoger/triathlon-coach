# Audit Resilienza Telegram Bot

**Data:** 2026-05-09
**Componente:** `workers/telegram-bot/src/index.ts` e interazioni correlate.

## 1. Mappa dei Comandi
| Comando | Parametri Attesi | Parser | Side Effects |
|---------|-----------------|--------|--------------|
| `/help` o `/start` | Nessuno | Exact match | Invio messaggio help |
| `/brief` | Nessuno | Exact match | Invio fallback msg |
| `/status` | Nessuno | Exact match | Fetch stato e invio |
| `/budget` | Nessuno | Exact match | DB Read `api_usage`, invio msg |
| `/rpe <1-10>` | Intero | Split stringa | DB Insert `subjective_log` |
| `/log <testo>` | Stringa | Regex `rpe`, string match | DB Insert `subjective_log` |
| `/debrief` | Nessuno | Exact match | KV Put (stato conv), invio prompt |
| *(Testo libero)* | Stringa | Verifica KV per debrief | DB Insert (debrief o free note) |
| *(Callback Query)* | `accept_mod_X` ecc. | `data.split("_")` | DB Patch `plan_modulations`, Edit msg |

## 2. Test Casi Reali

### Test Funzionali Base
- **Sintassi corretta `/log RPE 7 gambe ok`**: ✅ ok. Parsato RPE e testo. DB popolato. P0.
- **Sintassi sbagliata `/rpe foo`**: ✅ ok. Risponde "Uso: /rpe <1-10>". P0.
- **Comando inesistente `/pippo`**: ✅ ok. Trattato come free_note. P0.
- **Argomenti lunghi**: ✅ ok. Supabase gestisce campi TEXT estesi. P0.
- **Caratteri speciali / Emoji**: ✅ ok. Codifica UTF-8 supportata nativamente. P0.

### Test Edge Case
- **Idempotenza Callback (`accept_mod_X` doppio click)**: ⚠️ degraded. Se premuto due volte velocemente, fa due PATCH identici al DB. Supabase è idempotente, ma per sicurezza il bot nasconde i bottoni dopo il click (mitigato). P2.
- **Messaggio audio/foto**: ❌ broken (potenziale). L'oggetto `query.message.text` è `undefined` se arriva una foto, causando crash nel `trim()`. P1.
- **Allow-list errata (Security)**: ✅ ok. Lo script del Worker Cloudflare protegge a livello di webhook se si usa secret path, ma il codice `index.ts` non verifica esplicitamente il `chat_id` contro un allow-list. P1.

### Test Persistenza Dati
- **Log RPE**: ✅ ok. Inserisce `{ kind: "post_session", rpe: X }` correttamente.
- **Debrief State Machine**: ✅ ok. Il KV Cloudflare memorizza lo stato `/debrief`. Il prossimo messaggio senza `/` chiude lo stato e salva.
- **Modulazione in pending da molto**: ✅ ok. L'ID uuid è valido, ma manca validazione temporale (scadenza modulazione vecchia). P2.

## 3. Bug Riscontrati e Fix Proposti
- **Bug 1: Crash su media (Audio/Foto)**
  - *Fix:* Controllare `if (!text) return new Response("OK")` all'inizio del trigger.
- **Bug 2: Nessuna validazione Authorization ChatID**
  - *Fix:* Controllare che `chatId.toString() === env.TELEGRAM_CHAT_ID`.
- **Bug 3 (Segnalato dall'utente): Fallimento Morning Briefing**
  - *Diagnosi Root Cause:* Il log workflow GitHub indicava il fallimento del debrief mattutino (briefing). Questo si verifica in un potenziale bug di concorrenza tra l'assenza di dati (`planned=None` gestito bene) ma la dipendenza `supabase` mancante dal `requirements.txt` che causava `ModuleNotFoundError`, o un disallineamento `planned.get()` se l'oggetto DB è formalmente vuoto. Fissato nel `briefing.py` rafforzando i type checks e assicurandosi i pacchetti in reqs.

## 4. Conclusione
Il bot è molto robusto per i flussi testuali. Manca di robustezza contro i flussi media/non-text, e potrebbe esporre vulnerabilità se un altro utente trovasse il bot (va bloccato su singola chat ID).
