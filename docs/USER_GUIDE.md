# Guida Utente — Triathlon Coach AI

## Routine giornaliera

### 06:30 — Brief mattutino (automatico)

Ogni mattina alle 06:30 ricevi su Telegram un brief che contiene:

- **Come stai oggi**: sonno, HRV (con interpretazione), body battery
- **Carico**: acute/chronic load Garmin, rapporto ACWR, training status
- **Cosa fare oggi**: sessione pianificata (se presente) o indicazione di gestire autonomamente
- **Verso Lavarone**: countdown, fase corrente, focus del periodo
- **Warning**: flag attivi (HRV crash, infortunio, malattia) + note permanenti (spalla, fascite)

Se i dati Garmin sono vecchi (>18h), il brief lo segnala con warning in testa. Il brief è 100% rule-based, zero chiamate LLM — costo zero, affidabilità massima.

**Vuoi commentare il brief?** Fai swipe → Rispondi direttamente sul messaggio e scrivi quello che vuoi. Il bot lo salva come `brief_response`, non come debrief — lo usa per il contesto della giornata.

### Post-allenamento — Log soggettivo

Dopo la sessione, manda al bot un messaggio con RPE e sensazioni.

```
/rpe 7
```
Log RPE rapido.

```
/log Z2 60min bici, gambe pesanti ma watt ok. Spalla nessun problema.
```
Log libero — il bot estrae RPE, soreness e flag automaticamente.

```
RPE 7, gambe ok, no dolori, energia buona
```
Anche senza `/log` — se il testo inizia con "RPE", viene salvato come debrief automaticamente.

> **Azioni rischiose — conferma esplicita**: se scrivi qualcosa che contiene una parola di dolore o malattia (`dolore`, `male`, `febbre`, `infortunio`…), il bot chiede conferma prima di salvare il flag:
> ```
> Tu:  "ho male alla spalla forte"
> Bot: "Ho capito: infortunio alla spalla. Salvo con flag attivo?"
>      [✅ Sì] [✏️ Correggi] [❌ Era altro]
> ```
> Questo previene falsi positivi. Le conferme scadono dopo 24h — se non rispondi, nessun flag viene attivato.

### 21:30 — Debrief serale (automatico)

Il bot ti manda un reminder con 4 domande:

1. RPE sessione principale (1-10)
2. Qualità tecnica / sensazione (libero)
3. Dolori o segnali (sì/no + dove)
4. Energia residua e sonno previsto

**Il modo più comodo**: fai swipe → Rispondi direttamente sul messaggio del reminder, anche ore dopo. Il bot riconosce che stai rispondendo a quel reminder e salva correttamente come `evening_debrief`. Non serve usare `/debrief`.

Se oggi era off, ignora il reminder.

### 18:00 Mar/Gio/Sab — Domanda proattiva (automatico)

Il bot ti fa una domanda contestuale (injury, recovery, motivazione, tecnica). Tre opzioni:

| Bottone | Effetto |
|---------|---------|
| 💬 Rispondo dopo | Rimuove i bottoni — fai reply al messaggio quando vuoi |
| 🤐 Salta | Domanda ignorata |
| 🚫 Disabilita oggi | Nessun'altra domanda per oggi |

---

## Routine settimanale

### Domenica sera — Weekly review in Claude mobile/web

Alle 19:00 ricevi il reminder su Telegram. Apri Claude da smartphone o web, nella chat/progetto con il connector coach attivo, e digita:

```
fai la weekly review
```

L'agente segue il protocollo in 7 fasi senza usare API LLM backend:

0. **Sync dati** — chiama `get_weekly_context`; se l'ultimo sync Garmin è > 1 ora fa, forza un aggiornamento automatico con `force_garmin_sync`
1. **Raccolta dati** — usa `get_weekly_context` per metriche, wellness, attività, log soggettivi, piano passato/futuro, analisi e modulazioni
2. **Analisi** — confronta carico realizzato vs pianificato, trend HRV, compliance, segnali soggettivi
3. **Diagnosi** — identifica pattern (es. "troppo volume Z3", "sonno in calo", "spalla migliorata")
4. **Proposta** — struttura settimana successiva: schema settimanale + dettaglio sessioni per i prossimi 2-3 giorni
5. **Conferma + commit** — ti mostra il piano, tu dici "ok" o "modifica X". Solo dopo il tuo ok, chiama `commit_plan_change` per ogni sessione
6. **Google Calendar** — dopo il commit, crea/aggiorna gli eventi nel tuo Google Calendar con orario, sport, durata e descrizione completa

Il tutto richiede 15-20 minuti.

**Esempio di conversazione dopo la review:**
```
> Ho una cena imprevista mercoledì. Sposta la sessione lunga a giovedì.
```
L'agente propone la modifica con razionale, tu confermi.

---

## Race week (T-7 → T+1)

Quando mancano 7 giorni a una gara A o B, il sistema entra automaticamente in **modalità race week**:

### Cosa cambia nel brief
- Template ridotto: focus gara, niente sezioni normali di load/progress
- Ogni giorno ha indicazioni specifiche (taper, richiamo, apertura, vigilia)
- T-0: race day brief con link a Claude mobile/web per piano gara completo

### Timeline tipo

| Giorno | Cosa succede |
|--------|-------------|
| T-7 | Inizio taper: volume -40%, intensità mantenuta in micro-dosi. Check logistica. |
| T-6 → T-4 | Taper progressivo. Z1-Z2 + allunghi brevi. |
| T-3 | Richiamo intensità: 10min Z2 + 5×30s allungo + 10min Z2. Check meteo/percorso. |
| T-2 | Apertura: 20-30min Z1-Z2 + 3-4 allunghi. Check materiale completo. |
| T-1 | Vigilia: 15-20min Z1. Cena entro 19:30, letto entro 22:00. Tutto pronto stasera. |
| T-0 | RACE DAY. Apri Claude mobile/web: `race day brief` per timeline completa. |
| T+1 | Debrief post-gara in Claude mobile/web. |

### Piano gara dettagliato

Apri Claude mobile/web e digita:
```
attiva race week protocol
```
L'agente produce il piano completo: warm-up, pacing, nutrition, mental checkpoints, contingency.

Per la predizione performance:
```
predici la mia performance a Lavarone
```
Ricevi range di tempo con confidence interval basato sui tuoi dati.

---

## Telegram bot — Riferimento comandi

```
/help              — lista comandi
/brief             — brief on-demand (non aspettare le 06:30)
/log <testo>       — log soggettivo libero (RPE, sensazioni, note)
/rpe <1-10>        — log RPE rapido per ultima sessione
/debrief           — avvia flow debrief serale manuale
/undo              — annulla l'ultimo log (ultimi 30 min) — chiede conferma bottoni
/history           — ultimi 10 log
/history 7d        — log ultimi 7 giorni
/history rpe       — solo log con RPE registrato
/history injury    — solo log con flag infortunio
/budget            — stato budget API AI mensile
/status            — stato sync, ultimo dato Garmin, ultimo HRV
```

### Reply threading — dettaglio

Il bot logga ogni messaggio che manda. Puoi fare swipe → Rispondi su qualsiasi messaggio del bot, anche giorni dopo, e il bot usa il contesto corretto:

| Messaggio originale | Come viene salvata la reply |
|---------------------|-----------------------------|
| Brief mattutino | `brief_response` (commento, non debrief) |
| Reminder debrief serale | `evening_debrief` con RPE/sensazioni |
| Domanda proattiva | `proactive_response` con categoria (recovery, injury…) |
| Proposta modulazione | Non testuale — usa i bottoni ✅/❌/💬 |
| Messaggio non riconosciuto | Fallback al parser standard |

Se il messaggio su cui fai reply è troppo vecchio (>90 giorni, eliminato dal cleanup domenicale), il bot cade sul parser standard senza perdere il messaggio.

### Testo non riconosciuto — help contestuale

Se mandi un testo che il bot non riesce a classificare (nessun RPE, nessun flag, nessun comando), invece di salvare silenziosamente ti chiede:

```
Bot: "Non sono sicuro di aver capito. Vuoi che salvi come:"
     [📝 Nota libera] [🩹 Sintomo/dolore] [🎯 RPE post-sessione]
```

Clicca il bottone corretto — il bot salva nel modo giusto.

---

## Claude mobile/web — Interazioni utili

Apri Claude da smartphone/web con il remote MCP connector `triathlon-coach` attivo e prova:

### Analisi stato

```
Come sto andando questa settimana?
```
L'agente tira i dati via MCP, analizza trend, ti dà diagnosi con numeri.

### Analisi ultima sessione

```
Analizza l'ultima sessione
```
Claude chiama `get_session_review_context` e produce una lettura breve senza usare API backend.

### Modifica piano

```
Spostami la sessione di mercoledì a giovedì, ho un impegno di lavoro.
```
Propone la modifica con razionale, attende il tuo ok, poi committa.

### Predizione gara

```
Predici la mia performance a Lavarone.
```
Range di tempo con confidence interval, basato su CTL attuale, test fitness recenti, specifico del percorso.

### Capire il perché

```
Spiegami perché lavoriamo polarized in questa fase.
```
Razionale fisiologico contestualizzato ai tuoi dati. L'agente cita CLAUDE.md §3 e training journal.

### Revisione mesociclo

```
Proponi il prossimo mesociclo di 4 settimane.
```
Genera block completo con carico progressivo, settimana scarico, test fitness schedulato.

### Claude Code opzionale

Claude Code resta utile per modificare il repository, testare codice e fare manutenzione tecnica. Per coaching operativo quotidiano e weekly review non è più richiesto.

---

## Setup iniziale

### Anthropic API Key (opzionale per LLM cloud)

Il sistema ora usa `COACH_LLM_MODE=quality`: mantiene LLM cloud per weekly review, race briefing e pattern extraction, ma disabilita automazioni non essenziali. Per la policy completa vedi `docs/LLM_USAGE_POLICY.md`.

Se vuoi usare Claude API per queste funzioni:
1. Vai su https://console.anthropic.com e carica almeno $10 di credito.
2. Vai su https://console.anthropic.com/settings/limits e imposta il limite di spesa mensile a **$5.50**.
3. Genera una API key da https://console.anthropic.com/settings/keys.
4. Aggiungila nei secret di GitHub come `ANTHROPIC_API_KEY`.
5. Mettila nel tuo file `.env` locale se vuoi lanciare review AI da macchina locale.

### Claude mobile/web connector

Per usare l'abbonamento Claude invece delle API:

1. Vai su Claude web/desktop → Settings → Connectors.
2. Aggiungi il remote MCP server `mcp-server` con URL `/mcp`.
3. Usa `Authorization: Bearer <MCP_BEARER_TOKEN>`.
4. Verifica da Claude mobile chiedendo: `dammi il piano dei prossimi 7 giorni`.

Tool principali:
- `get_weekly_context` — weekly review completa in una chiamata.
- `get_race_context` — race briefing.
- `get_session_review_context` — analisi sessione su richiesta.
- `get_upcoming_plan` — controllo rapido del piano.
- `commit_plan_change` — scrittura DB solo dopo conferma esplicita.

### Google Calendar (opzionale ma consigliato)

L'agente può creare automaticamente gli eventi delle sessioni pianificate nel tuo Google Calendar.

1. Vai su https://claude.com/settings/connectors
2. Cerca "Google Calendar" e attivalo
3. Autorizza l'account Google con cui vuoi sincronizzare
4. Verifica in Claude web/mobile che il connector Google Calendar sia attivo

Dopo il setup, la weekly review e l'adjust_week creeranno/aggiorneranno gli eventi automaticamente.
Mapping: ogni sessione diventa un evento con emoji sport (🏊/🚴/🏃/💪), orario default 06:30, durata e descrizione completa.

### PAT GitHub per sync forzato

Per permettere all'agente di forzare un sync Garmin prima della weekly review:

1. Genera un PAT GitHub (classic) con scope `repo` + `workflow`
   - https://github.com/settings/tokens/new
2. Aggiungi il PAT come secret del Cloudflare Worker MCP:
   ```bash
   cd workers/mcp-server
   wrangler secret put GH_PAT_TRIGGER
   ```
3. Deploy del worker aggiornato:
   ```bash
   wrangler deploy
   ```

### Migration SQL

Esegui le migration in `migrations/` nel Supabase SQL Editor. Vedi `migrations/README.md` per istruzioni.

---

## Manutenzione

### Se il watchdog suona

Il watchdog gira ogni ora. Se qualcosa è giù, ricevi alert Telegram. Diagnosi:

1. **Garmin sync fallita >24h** → Token scaduto? Esegui `python scripts/garmin_first_login.py`, aggiorna il secret `GARMIN_SESSION_JSON` su GitHub Settings → Secrets
2. **Briefing fallito** → Controlla il run della Action su GitHub Actions. Causa comune: Supabase in pausa (raro, il keepalive previene)
3. **Watchdog stesso non pinga healthchecks.io** → Controlla il workflow su GitHub Actions. Se Actions è down, è un outage GitHub — attendi.

### Aggiornare token Garmin scaduto

```bash
cd triathlon-coach
python scripts/garmin_first_login.py
# Segui le istruzioni, copia il JSON generato
# Vai su GitHub → Settings → Secrets → GARMIN_SESSION_JSON → update
```

### Rotazione secret trimestrale

Ogni 3 mesi:
- Rigenera token Garmin
- Rigenera DR_ENCRYPTION_KEY (e fai un nuovo snapshot subito dopo)
- Verifica che il token Strava refresh funzioni ancora
- Verifica che il bot Telegram risponda

### Test DR restore trimestrale

```bash
python scripts/dr_restore.py <snapshot-id>
# Verifica che il DB restaurato abbia tutti i dati
```

---

## Troubleshooting

### "Il brief non arriva alle 06:30"

1. Controlla la Action `morning-briefing` su GitHub: è rossa?
2. Se sì, leggi il log dell'errore. Cause comuni:
   - `SUPABASE_URL` non raggiungibile → Supabase in pausa (raro)
   - `TELEGRAM_BOT_TOKEN` invalido → bot cancellato? Ricrea via BotFather
3. Se la Action è verde ma non arriva → controlla Telegram: il bot è ancora attivo? Manda `/status`
4. Workaround immediato: manda `/brief` al bot per generare on-demand

### "Il comando bot non risponde"

1. Controlla che il Cloudflare Worker `telegram-bot` sia deployed: `wrangler tail` per i log live
2. Verifica webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Se il webhook punta a un URL morto, ri-settalo:
   ```
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://telegram-bot.<account>.workers.dev/webhook"
   ```

### "Il bot salva le cose nel modo sbagliato"

- **Ha salvato il debrief come nota libera** → Hai mandato la risposta senza fare reply al reminder? Il bot usa il reply threading per capire il contesto. Fai swipe sul messaggio del reminder → Rispondi.
- **Ha creato un flag injury che non volevo** → Usa `/undo` entro 30 minuti per annullare. Oppure la prossima volta clicca [❌ Era altro] quando ti chiede conferma.
- **Non capisce il mio messaggio** → Ti apparirà il menu di classificazione [📝 Nota libera] [🩹 Sintomo] [🎯 RPE]. Clicca il tipo corretto.

### "Il reply threading non funziona"

- Il reply threading richiede che il Worker abbia loggato il messaggio in `bot_messages` quando lo ha mandato. Se hai aggiornato il Worker dopo che il messaggio era già stato inviato, quei vecchi messaggi non hanno un record in DB e il reply cade sul parser standard. Comportamento corretto.
- Messaggi più vecchi di 90 giorni vengono eliminati dal cleanup domenicale — il reply su di essi cade sul parser standard.

### "L'agente non ha dati aggiornati in Claude.ai"

1. Il MCP Worker è up? Prova: "che dati hai su di me?" in Claude.ai
2. Se risponde senza dati → Worker down. Controlla Cloudflare Dashboard → Workers
3. Workaround: copia/incolla il brief Telegram nella chat Claude.ai come contesto

### "HRV risulta null nel brief"

Garmin HR strap indossato di notte? Se l'orologio è sul comodino, HRV = null. È corretto. Il readiness viene degradato a "non valutabile" ma il sistema non crasha.

### "Il piano proposto è troppo aggressivo/conservativo"

Rispondi all'agente:
```
Troppo aggressivo: abbassa il volume del 20%. La fascite non è ancora risolta.
```
L'agente riformula. Non committa finché non dici "ok". Se il pattern si ripete, aggiorna le note in CLAUDE.md §2 (stato_attuale) con vincoli più espliciti.
