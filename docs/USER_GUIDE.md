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

### Post-allenamento — Log soggettivo

Dopo la sessione, manda al bot un messaggio con RPE e sensazioni. Due opzioni:

```
/rpe 7
```
Log RPE rapido per l'ultima sessione.

```
/log Z2 60min bici, gambe pesanti ma watt ok. Spalla nessun problema.
```
Log libero — il bot salva in `subjective_log` con timestamp.

### 21:30 — Debrief serale (automatico)

Il bot ti scrive con 4 domande standard:

1. RPE sessione principale (1-10)
2. Qualità tecnica / sensazione (libero)
3. Dolori o segnali (sì/no + dove)
4. Energia residua e sonno previsto

Rispondi in un unico messaggio o uno per volta. Se oggi era off, ignora.

---

## Routine settimanale

### Domenica sera — Weekly review in Claude Code

Alle 19:00 ricevi il reminder su Telegram. Apri Claude Code e digita:

```
fai la weekly review
```

L'agente segue il protocollo in 7 fasi:

0. **Sync dati** — se l'ultimo sync Garmin è > 1 ora fa, forza un aggiornamento automatico (tool `force_garmin_sync`). Questo garantisce che la review sia basata su dati completi anche se hai appena finito un allenamento
1. **Raccolta dati** — chiama `get_recent_metrics(14)`, `get_activity_history('all', 7)`, `query_subjective_log(7, 'all')`
2. **Analisi** — confronta carico realizzato vs pianificato, trend HRV, compliance, segnali soggettivi
3. **Diagnosi** — identifica pattern (es. "troppo volume Z3", "sonno in calo", "spalla migliorata")
4. **Proposta** — struttura settimana successiva: schema settimanale + dettaglio sessioni per i prossimi 2-3 giorni
5. **Conferma + commit** — ti mostra il piano, tu dici "ok" o "modifica X". Solo dopo il tuo ok, chiama `commit_plan_change` per ogni sessione
6. **Google Calendar** — dopo il commit, crea/aggiorna gli eventi nel tuo Google Calendar con orario, sport, durata e descrizione completa

Il tutto richiede 15-20 minuti. Il piano ibrido (struttura solida + dettagli vicini) viene raffinato ogni 2-3 giorni in conversazioni successive.

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
- T-0: race day brief con link a Claude Code per piano gara completo

### Timeline tipo

| Giorno | Cosa succede |
|--------|-------------|
| T-7 | Inizio taper: volume -40%, intensità mantenuta in micro-dosi. Check logistica. |
| T-6 → T-4 | Taper progressivo. Z1-Z2 + allunghi brevi. |
| T-3 | Richiamo intensità: 10min Z2 + 5×30s allungo + 10min Z2. Check meteo/percorso. |
| T-2 | Apertura: 20-30min Z1-Z2 + 3-4 allunghi. Check materiale completo. |
| T-1 | Vigilia: 15-20min Z1. Cena entro 19:30, letto entro 22:00. Tutto pronto stasera. |
| T-0 | RACE DAY. Apri Claude Code: `race day brief` per timeline completa. |
| T+1 | Debrief post-gara in Claude Code. |

### Piano gara dettagliato

Apri Claude Code e digita:
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

## Telegram bot — Comandi

```
/help           — lista comandi
/brief          — genera e invia brief on-demand (non aspettare le 06:30)
/log <testo>    — log soggettivo libero (RPE, sensazioni, note)
/rpe <1-10>     — log RPE rapido per ultima sessione
/status         — stato sync, ultimo dato Garmin, ultimo HRV
/debrief        — avvia flow debrief serale manuale
```

---

## Claude Code — Interazioni utili

Apri Claude Code dal Mac (`cd triathlon-coach && claude`) e prova:

### Analisi stato

```
Come sto andando questa settimana?
```
L'agente tira i dati via MCP, analizza trend, ti dà diagnosi con numeri.

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

---

## Setup iniziale

### Google Calendar (opzionale ma consigliato)

L'agente può creare automaticamente gli eventi delle sessioni pianificate nel tuo Google Calendar.

1. Vai su https://claude.com/settings/connectors
2. Cerca "Google Calendar" e attivalo
3. Autorizza l'account Google con cui vuoi sincronizzare
4. Verifica in Claude Code con `claude mcp list` che il connector sia ✓ Connected

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
