# Troubleshooting Playbook

## 1. Bot Telegram non risponde
- **Sintomi:** Invi un messaggio, il bot non dà segni di vita e il tick rimane singolo per molto tempo.
- **Diagnosi:** Il Cloudflare Worker potrebbe essere giù, o il webhook Telegram potrebbe essersi disallineato.
- **Fix:**
  1. Controlla lo stato del webhook: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
  2. Verifica che i secret (soprattutto `SUPABASE_SERVICE_KEY` e `TELEGRAM_CHAT_ID`) sul Worker Cloudflare non siano stati invalidati.
  3. Controlla l'uso di `wrangler tail` sul Worker.

## 2. Brief mattutino non arriva (es. 8 maggio)
- **Sintomi:** Manca il messaggio del mattino alle 06:30.
- **Diagnosi:** Il workflow GitHub Actions `morning-briefing.yml` ha fallito.
- **Fix:**
  1. Apri la tab Actions su GitHub e controlla il job fallito.
  2. Se l'errore è `ModuleNotFoundError`, controlla `requirements.txt` (spesso succede dopo step di refactoring pesanti in locale).
  3. Il codice gestisce correttamente i casi di `planned=None`, quindi l'errore è spesso infrastrutturale (Supabase non raggiungibile, Auth fallita).

## 3. Budget API esaurito
- **Sintomi:** Messaggi su Telegram di alert e AI silente o degradata.
- **Diagnosi:** Controlla la tabella `api_usage` su Supabase o lancia il comando `/budget` dal bot.
- **Fix:**
  1. Usa `/budget` per valutare l'assorbimento. 
  2. Se sei a fine mese, il sistema recupererà in automatico dal giorno 1.
  3. Le feature critiche (Race Week) sopravvivranno. Non intervenire a meno che non sia strettamente necessario, in tal caso puoi svuotare manualmente la `api_usage` dei record del mese.

## 4. Workflow GitHub Actions fallisce
- **Sintomi:** Email di "Run failed".
- **Fix:** Verifica step-by-step:
  1. I secret GitHub (Settings -> Secrets) sono validi?
  2. Il runner Ubuntu è disponbile?
  3. C'è un bug di sintassi in uno dei python script modificati di recente?

## 5. Modulation in pending da > 24h
- **Sintomi:** Hai un bottone di modulazione mid-week "vecchio" rimasto non cliccato.
- **Fix:** Esegui una patch manuale dal SQL Editor di Supabase:
  ```sql
  UPDATE plan_modulations SET status='rejected' WHERE status='proposed' AND created_at < NOW() - INTERVAL '2 days';
  ```

## 6. Pulizia vecchie Session Analyses
- **Sintomi:** Database pieno o superamento limite free tier.
- **Fix:**
  ```sql
  DELETE FROM session_analyses WHERE created_at < NOW() - INTERVAL '3 months';
  ```

## 7. Pattern observations duplicati o "sporchi"
- **Sintomi:** `docs/coaching_observations.md` è diventato enorme e confuso.
- **Fix:** Il file è testuale. Apri un editor di testo, fai uno scrub manuale consolidando i concetti. Al prossimo giro, lo script di pattern extraction prenderà il file "pulito" come base.
