# Guida Utente — Triathlon Coach AI

> Versione aggiornata: maggio 2026

---

## Indice

1. [Panoramica del sistema](#1-panoramica-del-sistema)
2. [Prima volta — onboarding completo](#2-prima-volta--onboarding-completo)
3. [Routine giornaliera](#3-routine-giornaliera)
4. [Routine settimanale](#4-routine-settimanale)
5. [Pianificazione mesociclo](#5-pianificazione-mesociclo)
6. [Race week](#6-race-week)
7. [Dashboard web](#7-dashboard-web)
8. [Skill di Claude.ai — riferimento completo](#8-skill-di-claudeai--riferimento-completo)
9. [Telegram — comandi e log](#9-telegram--comandi-e-log)
10. [Fitness test — rilevamento automatico](#10-fitness-test--rilevamento-automatico)
11. [Manutenzione e troubleshooting](#11-manutenzione-e-troubleshooting)

---

## 1. Panoramica del sistema

Il sistema è composto da tre livelli che lavorano insieme:

| Livello | Strumento | Chi agisce | Frequenza |
|---------|-----------|------------|-----------|
| **Automatico** | GitHub Actions + Python | Il sistema, senza intervento | Ogni 3h / ogni giorno / ogni domenica |
| **Notifiche e log** | Bot Telegram | Tu, in risposta ai messaggi | Ogni giorno |
| **Pianificazione e analisi** | Claude.ai (web o mobile) | Tu, quando necessario | Domenica sera + ad hoc |
| **Monitoraggio** | Dashboard web | Tu, quando vuoi controllare | On demand |

### Cosa fa da solo il sistema

- Ogni 3 ore: sincronizza le attività Garmin, ricalcola CTL/ATL/TSB/HRV, aggiorna la readiness
- Ogni mattina alle 06:30: invia il brief mattutino su Telegram
- Ogni sera alle 21:30: invia il reminder per il debrief serale
- Mar/Gio/Sab alle 18:00: invia una domanda proattiva contestuale
- Ogni domenica sera: invia il reminder per la weekly review
- Ogni domenica notte: estrae pattern, aggiorna `docs/coaching_observations.md`, aggiorna `docs/progress_tracker.md`, committa nel repo
- Ogni notte: snapshot DR cifrato delle tabelle critiche

### Cosa fai tu

- Rispondere al debrief serale (ogni sera dopo l'allenamento)
- Fare la weekly review ogni domenica sera in Claude.ai (~20 min)
- Avviare le skill Claude.ai quando necessario (mesociclo, race week, analisi video, ecc.)
- Controllare la dashboard quando vuoi un quadro visivo completo

---

## 2. Prima volta — onboarding completo

Questa sezione copre tutto quello che serve per portare il sistema a zero → operativo. Se il sistema è già in funzione, puoi saltarla.

### 2.1 Setup infrastruttura (una tantum)

Tutti i passi sono già documentati in `docs/SETUP.md`. In sintesi:

1. **Supabase**: crea il progetto, esegui le migration in `migrations/` in ordine cronologico nel SQL editor
2. **Garmin**: esegui `python scripts/garmin_first_login.py`, copia il cookie JSON risultante nel secret GitHub `GARMIN_SESSION_JSON`
3. **Telegram**: crea il bot con BotFather, ottieni `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, aggiungili ai secret GitHub
4. **Anthropic**: crea API key su console.anthropic.com, imposta budget mensile a $5.50, aggiungi `ANTHROPIC_API_KEY` nei secret GitHub e come secret Wrangler nel worker Telegram
5. **GitHub PAT**: genera token con scope `repo` + `workflow`, aggiungilo come `GH_PAT_TRIGGER` nei secret GitHub **e** come secret Wrangler nel worker MCP
6. **Cloudflare**: deploya i Workers (`wrangler deploy` in `workers/mcp-server/` e `workers/telegram-bot/`), crea il Pages project (`wrangler pages project create triathlon-dashboard`), aggiungi `CF_PAGES_API_TOKEN` e `CF_ACCOUNT_ID` nei secret GitHub
7. **Claude.ai**: vai su claude.ai/settings/connectors, aggiungi il connector MCP con l'URL del worker MCP e il bearer token

### 2.2 Inserimento profilo atleta (una tantum)

Apri `CLAUDE.md` e compila le sezioni:

- `§1 Profilo atleta`: data di nascita, peso, altezza, storia infortuni, vincoli attuali
- `§2 Zone fisiologiche`: FTP, CSS, passo soglia, LTHR — anche valori stimati se non hai ancora fatto un test
- `§5 Stato corrente`: fase attuale, CTL indicativo, prossima gara
- `§6 Obiettivi`: gara obiettivo A (con data), obiettivi B/C secondari

Questi dati sono la memoria persistente del coach. Aggiornali manualmente quando cambiano dati strutturali (infortuni, obiettivi), il resto viene aggiornato automaticamente.

### 2.3 Prima settimana con zero pianificato

Il sistema può lavorare anche senza sessioni pianificate, ma funziona meglio con un piano. Il flusso corretto per la prima settimana:

**Step 1 — Genera il primo mesociclo**

In Claude.ai, scrivi:
```
proponi il primo mesociclo di 4 settimane
```
L'agente chiederà: fase target (base/build), data prossima gara, CTL attuale. Produce un blocco 3+1 (3 settimane di carico + 1 taper), lo salva nel DB (`mesocycles`) e crea le sessioni pianificate (`planned_sessions`) giorno per giorno.

Vedi sezione [5 — Pianificazione mesociclo](#5-pianificazione-mesociclo) per i dettagli.

**Step 2 — Prima weekly review**

Anche se hai pochi dati storici, fai la weekly review domenica:
```
fai la weekly review
```
L'agente proporrà la settimana successiva tenendo conto di quello che hai già pianificato nel mesociclo.

**Step 3 — Inizia a loggare**

Da subito, dopo ogni allenamento, manda al bot il debrief (vedi sezione [9](#9-telegram--comandi-e-log)). I dati soggettivi sono essenziali per l'adattamento del piano.

### 2.4 Backfill dati storici (opzionale)

Se hai già mesi di attività Garmin sincronizzabili, puoi fare un backfill delle analisi post-sessione:

1. Vai su GitHub → Actions → `backfill-analyses`
2. Clicca "Run workflow"
3. Inserisci il numero di giorni (es. `90` per 3 mesi)
4. Avvia

Il sistema analizzerà retroattivamente le sessioni recenti e popolerà `session_analyses`.

---

## 3. Routine giornaliera

### 06:30 — Brief mattutino (automatico)

Ricevi su Telegram un brief con:

- **Forma**: CTL, TSB, HRV z-score con interpretazione
- **Readiness**: score 0-100, label (pronto / attenzione / riposo), flag attivi
- **Sessione del giorno**: tipo, sport, durata, zone target — o "giornata libera"
- **Verso la gara**: countdown, fase mesociclo corrente
- **Warning**: HRV crash, infortunio, malattia, fascite, spalla

Il brief è completamente deterministico (zero LLM, zero costo). In race week (T-7 → T+1) il template cambia con focus gara.

**Vuoi commentare il brief?** Fai swipe → Rispondi direttamente. Il bot lo salva come `brief_response` (non come debrief).

---

### Durante/dopo l'allenamento — Log soggettivo

Manda al bot un messaggio con RPE e sensazioni. Tre modalità:

```
/rpe 7
```
Log RPE rapido per l'ultima sessione completata.

```
/log Z2 60min bici, gambe pesanti ma watt ok. Spalla ok.
```
Log libero — il bot estrae RPE, sensazioni, flag automaticamente.

```
RPE 7, gambe ok, energia buona, nessun dolore
```
Senza comando — se inizia con "RPE" viene salvato come debrief post-sessione.

**Campi riconosciuti:**
- RPE (1–10)
- Qualità sessione: `ottima` / `ok` / `brutta`
- Stato mentale: `motivato` / `demotivato` / `concentrato`
- Qualità sonno: `dormito bene` / `mal dormito`
- Ore sonno: `8h` / `dormito 6 ore`
- Flag infortunio: parole di dolore (`male`, `dolore`, `fastidio`, `fitta`…)
- Flag malattia: `febbre`, `raffreddore`, `influenza`…

**Conferma per flag rischiosi**: se scrivi qualcosa che attiva un flag infortunio/malattia, il bot chiede conferma prima di salvare:

```
Tu:  "fitta alla fascite a fine corsa"
Bot: "Ho capito: infortunio al piede/fascite. Salvo con flag attivo?"
     [✅ Sì] [✏️ Correggi] [❌ Era altro]
```

---

### 18:00 Mar/Gio/Sab — Domanda proattiva (automatico)

Il bot fa una domanda contestuale su recovery, sensazioni, motivazione o tecnica. Puoi:

| Bottone | Effetto |
|---------|---------|
| 💬 Rispondo dopo | Rimuove i bottoni, rispondi quando vuoi con swipe-reply |
| 🤐 Salta | Ignora la domanda |
| 🚫 Disabilita oggi | Nessun'altra domanda per oggi |

---

### 21:30 — Debrief serale (automatico)

Il bot manda un reminder. Il modo corretto:

**Fai swipe → Rispondi direttamente sul messaggio del reminder**, anche ore dopo. Il bot riconosce il contesto e salva come `evening_debrief`.

Se oggi era giorno off, ignora il reminder.

---

### Video analisi tecnica

Manda un video al bot Telegram (max 20MB) con caption che indica lo sport:

```
[video] "nuoto - analisi stile libero"
[video] "corsa - analisi appoggio"
[video] "bici - posizione in sella"
```

L'analisi vera si fa in Claude.ai:
```
analizza il video di nuoto di ieri
```

L'agente segue il protocollo per disciplina (vincoli attivi: spalla dx in nuoto, fascite in corsa), produce: priorità tecniche, punti di forza, piano correzione su 3 sessioni, confronto con video precedente.

Budget: max 2 video analisi/settimana. Il sistema skippa se il budget API mensile è esaurito.

---

## 4. Routine settimanale

### Domenica sera (19:00) — Reminder weekly review (automatico)

Ricevi il reminder su Telegram. Aprire Claude.ai (web o mobile app).

### Domenica sera (19:00–20:00) — Weekly review (manuale, ~20 min)

In Claude.ai scrivi:

```
fai la weekly review
```

**Fase 0 — Sync dati**
L'agente forza sync Garmin se l'ultimo è > 1h fa, garantendo dati completi.

**Fase 1 — Raccolta dati**
Legge dal DB tramite MCP in un'unica chiamata aggregata:
- Attività completate + metriche CTL/ATL/TSB/HRV ultime 2 settimane
- Debrief, RPE, flag, malattie, infortuni
- Sessioni pianificate vs eseguite giorno per giorno
- Video tecnici caricati durante la settimana
- Mesociclo attivo (fase, settimana corrente, target settimanale)
- Zone fisiologiche correnti

Legge anche: `CLAUDE.md`, `docs/coaching_observations.md`, `docs/progress_tracker.md`, `docs/elite_training_reference.md`.

**Fase 2 — Analisi narrativa**
Produce un'analisi di 15–20 righe: cosa ha funzionato, costo fisiologico pagato, segnali da monitorare. Non compiacente.

**Fase 3 — Proposta settimana successiva**
Struttura i prossimi 7 giorni rispettando:
- Struttura fissa (lun=corsa, mar=nuoto, mer=bici, gio=nuoto, ven=corsa, sab=bici, dom=corsa)
- Vincoli attivi (spalla dx, fascite, ecc.)
- Fase e progressione del mesociclo attivo
- Regole deterministiche: se HRV crash → recovery; se compliance <70% → volume -10%; se fase peak/taper → non ridurre il volume automaticamente

**Fase 4 — Conferma e commit**
L'agente mostra il piano. Tu dici **"ok"** o chiedi modifiche. Solo dopo la tua conferma esplicita scrive su `planned_sessions`. Non committa mai senza "ok".

**Esempio:**
```
Tu:    "Ho una cena mercoledì sera, sposta la bici"
Coach: "Proposta: mercoledì off, giovedì bici Z2 90min + nuoto tecnica 45min"
Tu:    "ok"
Coach: [committa le sessioni nel DB]
```

---

### Domenica notte (23:00) — Pattern extraction (automatico, nessuna azione)

Parte automaticamente. Non serve fare niente.

**Step 1 — Adaptive planner**: controlla la compliance della settimana, applica regole:

| Condizione | Azione |
|------------|--------|
| RPE medio > 7.5 | Aggiunge giorno recovery (automatico) |
| Compliance < 70% | Propone volume -10% (via Telegram, richiede ok) |
| Compliance < 50% | Propone piano ridotto settimana successiva |
| Fase peak o taper | Non riduce il volume (regola bloccante) |

**Step 2 — Pattern extraction**: analizza 4 settimane, aggiorna `docs/coaching_observations.md` con insight biometrici e soggettivi.

**Step 3 — Update stato**: aggiorna `CLAUDE.md` §5 con CTL/TSB correnti e fase (solo se cambio >5% CTL).

**Step 4 — Update progress tracker**: riscrive `docs/progress_tracker.md` con CTL trend 90gg, compliance 4 settimane, infortuni attivi, prossima gara, mesociclo corrente.

**Step 5 — Commit**: committa i file aggiornati nel repo Git.

---

## 5. Pianificazione mesociclo

Il mesociclo è il blocco di pianificazione di medio termine (tipicamente 3–6 settimane). Senza mesocicli nel DB, il piano è sessione-per-sessione e la Goal Board nella dashboard rimane vuota.

### Quando pianificare un mesociclo

- All'inizio del sistema (prima volta)
- Quando si conclude il mesociclo corrente (ultima settimana)
- Dopo una gara A, per il blocco di recovery + rebuild
- Quando cambia un obiettivo strutturale (nuova gara, infortunio)

### Come generare un mesociclo

In Claude.ai:

```
proponi il prossimo mesociclo di 4 settimane
```

Oppure, più specificato:

```
pianifica un mesociclo di build di 4 settimane verso Lavarone
```

L'agente:
1. Legge il CTL attuale, la fase precedente, le zone, i vincoli da `CLAUDE.md`
2. Struttura un blocco 3+1 (3 settimane di carico progressivo + 1 settimana di taper/recovery)
3. Distribuisce le sessioni rispettando la struttura settimanale fissa e i vincoli infortuni
4. Presenta il piano con volume per settimana, distribuzione sport, sessioni chiave
5. Chiede conferma, poi salva il mesociclo in `mesocycles` e le sessioni in `planned_sessions`

### Fasi dei mesocicli

| Fase | Obiettivo | Volume | Intensità |
|------|-----------|--------|-----------|
| `base` | Aerobic base, tecnica, adattamento | Alto | Bassa (Z1-Z2 predominante) |
| `build` | Sviluppo soglia, lavoro specifico | Alto-medio | Progressiva |
| `specific` | Simulazione gara, race pace | Medio | Alta |
| `peak` | Picco prestazione | Ridotto | Alta (sessioni brevi e intense) |
| `taper` | Scarico pre-gara | Molto ridotto | Media-alta (solo allunghi) |
| `recovery` | Recupero post-gara | Basso | Bassa |

### Modifica di un mesociclo in corso

Se cambiano le condizioni (infortunio, viaggio, gara anticipata):

```
adatta il mesociclo: ho avuto un problema alla fascite questa settimana
```

L'agente rilegge le sessioni future del mesociclo e propone le modifiche. Confermi con "ok".

---

## 6. Race week

Si attiva automaticamente 7 giorni prima di qualsiasi gara A o B registrata nel DB. Non serve fare niente di speciale — il brief mattutino cambia template automaticamente.

### Timeline race week

| Giorno | Sessione tipo | Brief |
|--------|--------------|-------|
| T-7 | Volume -40%, intensità mantenuta breve | Inizio taper |
| T-6 → T-4 | Z1-Z2 + allunghi brevi | Taper progressivo |
| T-3 | 10min Z2 + 5×30s allungo + 10min Z2 | Richiamo intensità |
| T-2 | 20-30min Z1-Z2 + 3-4 allunghi | Check materiale |
| T-1 | 15-20min Z1 | Cena ≤19:30, letto ≤22:00 |
| T-0 | RACE DAY | Brief speciale gara |
| T+1 | Recovery | Reminder debrief post-gara |

### Skill manuali per race week (Claude.ai)

```
attiva race week protocol
```
Produce: warm-up, pacing per segmento, nutrition plan, mental checkpoints, piano contingency. Da fare T-3 o T-2.

```
predici la mia performance a Lavarone
```
Range di tempo con confidence interval. Usa zone aggiornate, attività recenti, condizioni meteo se disponibili.

```
preparami il briefing gara
```
Brief strategico: obiettivo + pacing, logistica giornata, solo nutrizione testata, cosa fare se le gambe cedono a metà.

---

## 7. Dashboard web

**URL**: [https://triathlon-dashboard.pages.dev](https://triathlon-dashboard.pages.dev)

Accessibile da smartphone, tablet, PC. Login con il bearer token MCP.

### Contenuto

| Sezione | Cosa mostra |
|---------|-------------|
| **Readiness card** | Score readiness (0-100), label, CTL attuale, TSB, flag attivi, countdown prossima gara |
| **PMC Chart** | CTL/ATL/TSB ultimi 90 giorni (linea continua) + proiezione 12 settimane in avanti (linea tratteggiata) calcolata dai `target_tss` delle sessioni pianificate |
| **Wellness Chart** | HRV rmssd, sleep score, body battery — ultimi 30 giorni |
| **Compliance Bar** | Percentuale sessioni eseguite vs pianificate, ultime 4 settimane |
| **Prossime sessioni** | Prossime 7 sessioni pianificate con sport, tipo, durata, TSS |
| **Goal Board** | Timeline Excalidraw: blocchi mesociclo per fase, volume settimanale, sessioni chiave, gare |

### Goal Board

La Goal Board è generata automaticamente dai dati del DB:
- Blocchi colorati per fase mesociclo (base=blu, build=giallo, specific=arancione, peak=rosso, taper=viola, recovery=verde)
- Barre volume settimanale (altezza proporzionale alla durata totale pianificata)
- Diamanti sessioni chiave (TSS ≥ 70 o session_type: fitness_test/race_pace/vo2max)
- Diamanti gare colorati per priorità (A=rosso, B=arancione, C=giallo)

**Nota**: la Goal Board appare vuota o quasi se `mesocycles` nel DB è vuoto. Vai alla sezione [5](#5-pianificazione-mesociclo) per generare il primo mesociclo.

Il pulsante **↺ Rigenera** aggiorna la board dai dati più recenti senza ricaricare la pagina.

### Aggiornamento dati

I dati si aggiornano automaticamente ogni 5 minuti. Il pulsante **↺** forza un refresh immediato. Il timestamp in alto a destra mostra l'ora dell'ultimo caricamento.

---

## 8. Skill di Claude.ai — riferimento completo

Tutte le skill si usano in Claude.ai (web o mobile) con il connector MCP attivo. Non richiedono Claude Code CLI.

### Skill di pianificazione

**Weekly review**
```
fai la weekly review
```
La skill più importante. Analizza la settimana appena conclusa e pianifica la successiva. ~20 min. Da fare ogni domenica sera.

**Proposta sessione del giorno**
```
cosa faccio oggi?
dettagliami la sessione di domani
adatta la sessione di oggi: ho le gambe pesanti
```
Espande la sessione pianificata con warm-up, main set, cool-down, zone target, note tecniche. Adatta l'intensità in base alla readiness corrente.

**Genera mesociclo**
```
proponi il prossimo mesociclo di 4 settimane
pianifica un blocco di build verso Lavarone
```
Pianifica un blocco completo 3+1, salva nel DB mesocicli e sessioni. Vedi sezione [5](#5-pianificazione-mesociclo).

**Adjust week**
```
domani non riesco ad allenarmi, sposta la sessione
questa settimana viaggio, riadatta il piano
ho un infortunio alla spalla, modifica la settimana
```
Ribalanncia la settimana corrente mantenendo il volume totale dove possibile. Propone e chiede conferma prima di committare.

**Cancella sessione**
```
cancella la sessione di giovedì
rimuovi il lungo di domenica
```
Marca la sessione come `cancelled` nel DB (e rimuove dall'eventuale Google Calendar se collegato).

### Skill di analisi

**Query metrics**
```
come sto andando questa settimana?
mostrami il trend HRV degli ultimi 14 giorni
come è evoluto il mio CTL nell'ultimo mese?
```
Analisi narrativa dei dati biometrici recenti. Non mostra tabelle raw ma sintesi interpretata.

**Session analysis** (automatica)
L'analisi post-sessione è automatica: dopo ogni ingest, il sistema analizza le attività completate con Claude Haiku (~$0.02/sessione) e salva l'analisi in `session_analyses`. Non richiede azione.

**Analisi video**
```
analizza il video di nuoto di ieri
analisi tecnica corsa
```
Richiede che tu abbia prima inviato il video al bot Telegram. Vedi sezione [3](#3-routine-giornaliera).

### Skill di gara

**Race week protocol**
```
attiva race week protocol
```
Struttura completa T-7 → T+1: sessioni, checklist materiale, nutrition, mental prep.

**Race prediction**
```
predici la mia performance a Lavarone
quanto posso fare alla cross sprint?
```
Range di tempo con confidence interval basato su zone attuali e performance recenti.

**Race briefing**
```
preparami il briefing gara per Lavarone
```
Brief strategico T-2: pacing, logistica, nutrition testata, gestione crisi.

**Fitness test**
```
pianifica il prossimo test FTP
quando è il momento giusto per fare il test CSS?
```
Propone il protocollo completo con nome esatto da usare su Garmin per il rilevamento automatico.

### Skill di contesto

**Modulation** (semi-automatica)
Quando il sistema rileva HRV crash (z-score < -1.5) o flag critici, genera automaticamente una proposta di modulazione nel DB. Ricevi notifica su Telegram con i bottoni ✅/❌. Se vuoi forzarla manualmente:
```
proponi una modulazione del piano per questa settimana
```

---

## 9. Telegram — comandi e log

### Comandi

```
/help              — lista comandi
/brief             — brief on-demand (non aspettare le 06:30)
/log <testo>       — log soggettivo libero
/rpe <1-10>        — log RPE rapido per l'ultima sessione
/debrief           — avvia flow debrief manuale guidato
/undo              — annulla l'ultimo log (entro 30 min)
/history           — ultimi 10 log
/history 7d        — log ultimi 7 giorni
/history rpe       — solo log con RPE
/history injury    — solo log con flag infortunio
/budget            — stato budget API Anthropic mensile (con speso/rimasto)
/status            — stato sync, ultimo dato Garmin, ultimo HRV
```

### Reply threading

Fai swipe → rispondi su qualsiasi messaggio del bot:

| Messaggio originale | Come viene salvata la reply |
|---------------------|-----------------------------|
| Brief mattutino | `brief_response` |
| Reminder debrief serale | `evening_debrief` |
| Domanda proattiva | `proactive_response` |
| Proposta modulazione | Usa i bottoni ✅ Approva / ❌ Rifiuta / 💬 Commenta |

### Gestione flag infortunio/malattia

Quando un flag viene salvato, il sistema:
1. Aggiorna `daily_metrics.flags` con `injury_flag` o `illness_flag`
2. Adatta il brief del giorno successivo (sport alternativi, warning)
3. La weekly review terrà conto del flag nelle proposte

Per disattivare un flag:
```
/log spalla ok, nessun dolore da 3 giorni
```
Il bot proporrà di rimuovere il flag attivo.

---

## 10. Fitness test — rilevamento automatico

I test fisiologici aggiornano le zone usate dal sistema per prescrivere l'intensità delle sessioni. Senza test recenti, il sistema usa valori stimati da `CLAUDE.md`.

### Test supportati

| Test | Nome esatto su Garmin | Risultato |
|------|----------------------|-----------|
| FTP bici (20 min) | `FTP Test 20min` | FTP in Watt |
| FTP bici (ramp) | `Ramp Test FTP` | FTP in Watt |
| Soglia corsa (30 min) | `Threshold Run 30min` | Pace soglia in min/km |
| CSS nuoto (400+200) | `CSS Test 400-200` | CSS in sec/100m |
| LTHR corsa | `LTHR Test` | LTHR in bpm |

**Il nome deve corrispondere esattamente** per il rilevamento automatico. Usa questi nomi quando crei il workout su Garmin Connect.

### Cosa succede dopo il test

1. L'ingest successivo (entro 3h) rileva l'attività
2. Calcola il risultato (splits, HR, power)
3. Aggiorna `physiology_zones` nel DB (nuova riga con `valid_from=oggi`, la precedente chiusa con `valid_to=oggi`)
4. Aggiorna `CLAUDE.md §2` con i nuovi valori
5. Invia notifica Telegram con risultato e zone calcolate

### Se il rilevamento automatico fallisce

Il nome del workout su Garmin non corrisponde. Inserisci manualmente in Claude.ai:

```
Ho fatto il test FTP oggi: 215W in 20 minuti, attività Garmin ID 12345678
```

L'agente aggiornerà manualmente le zone.

### Quando fare i test

Il sistema traccia l'ultima data per ogni test in `physiology_zones`. Il consiglio generale:
- FTP bici: ogni 6-8 settimane, in fase base o build
- Soglia corsa: ogni 6-8 settimane
- CSS nuoto: ogni 8-10 settimane
- Non fare test in peak, taper o race week

---

## 11. Manutenzione e troubleshooting

### Monitoraggio automatico

Il sistema si monitora da solo:
- **Watchdog**: ogni ora controlla che tutti i componenti abbiano girato di recente. Allerta su Telegram se qualcosa è fermo
- **Healthchecks.io**: ping per garmin_sync, briefing_morning
- **Keepalive**: ogni giorno verifica la connessione Supabase

### Se il watchdog suona

| Alert | Diagnosi più probabile | Fix |
|-------|------------------------|-----|
| Garmin sync fallita >24h | Token Garmin scaduto | `python scripts/garmin_first_login.py` → aggiorna secret `GARMIN_SESSION_JSON` in GitHub |
| Briefing fallito | Supabase in pausa o token Telegram invalido | Controlla GitHub Actions → `morning-briefing` → log errori |
| Pattern extraction fallita | PAT mancante o budget API esaurito | Verifica `GH_PAT_TRIGGER` nei secret GitHub |
| Worker MCP down | Cloudflare Worker crashato | Cloudflare dashboard → Workers → controlla log → `wrangler deploy` |

### Rotazione secret (trimestrale)

1. Rigenera `GARMIN_SESSION_JSON`: esegui `python scripts/garmin_first_login.py`, aggiorna il secret GitHub
2. Verifica validità token Telegram bot (non scadono mai, ma se li hai regenerati)
3. Rigenera `DR_ENCRYPTION_KEY` (poi esegui subito un nuovo snapshot per non perdere la chiave vecchia)

### Troubleshooting rapido

**"Il brief non arriva alle 06:30"**
Controlla GitHub Actions → `morning-briefing`. Workaround immediato: `/brief` al bot.

**"Il bot non risponde"**
1. `wrangler tail` per log live del Worker telegram-bot
2. Verifica webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Se URL morto: ri-setta webhook con l'URL del Worker attivo

**"Il fitness test non è stato rilevato"**
Il nome del workout su Garmin non corrisponde ai pattern. Inserisci manualmente in Claude.ai.

**"L'agente Claude.ai non vede i dati aggiornati"**
Worker MCP down. Controlla Cloudflare Dashboard → Workers → mcp-server. Workaround: copia il brief Telegram come contesto nel messaggio.

**"La dashboard mostra dati vuoti"**
1. Verifica login: premi ↺, se torna alla login screen il token è scaduto
2. Verifica worker: `curl -H "Authorization: Bearer <TOKEN>" https://mcp-server.nicorugg.workers.dev/dashboard-data`
3. Se `{}` o errore: controlla GitHub Actions per errori recenti nell'ingest

**"HRV risulta null nel brief"**
Orologio non indossato di notte. La readiness viene degradata a "non valutabile", il sistema non crasha. Nessuna azione richiesta.

**"Il piano proposto è troppo aggressivo"**
Dì all'agente: "abbassa il volume del 15%, fascite non ancora risolta". L'agente non committa finché non dici "ok". Se il pattern si ripete, aggiorna `CLAUDE.md §2` con i vincoli in modo più esplicito (es. "max volume corsa settimanale: 35km fino a risoluzione fascite").

**"La Goal Board è vuota o quasi"**
La tabella `mesocycles` è vuota. Vai in Claude.ai e chiedi: `proponi il primo mesociclo di 4 settimane`. Dopo il commit, premi ↺ Rigenera nella dashboard.

---

## Documenti di riferimento

| File | Contenuto | Aggiornato da |
|------|-----------|---------------|
| `CLAUDE.md` | Profilo atleta, zone, metodologia, vincoli, stato corrente | Agente auto (domenica notte) + manuale |
| `docs/coaching_observations.md` | Pattern longitudinali biometrici e soggettivi | Automatico ogni domenica notte |
| `docs/progress_tracker.md` | CTL trend 90gg, compliance 4 settimane, mesociclo corrente, infortuni | Automatico ogni domenica notte |
| `docs/training_journal.md` | Decisioni settimanali, note coach, storico mesocicli | Manuale dopo weekly review |
| `docs/elite_training_reference.md` | 114 sessioni periodo elite set 2021–mag 2022 — target a lungo termine | Statico (storico) |
| `docs/injury_log.md` | Timeline infortuni, protocollo rehab, milestones | Manuale, aggiornato con flag injury |
| `docs/race_history.md` | Risultati gare passate con split e note strategiche | Manuale dopo ogni gara |
| `docs/FITNESS_TEST_PROTOCOL.md` | Nomi esatti Garmin e protocolli per ogni test fisiologico | Manuale (raramente cambia) |
| `docs/SETUP.md` | Setup infrastruttura completo (una tantum) | Manuale |

---

*Il coach usa `docs/elite_training_reference.md` come **target a lungo termine**, non come punto di partenza. Volume elite: media 4.2h/settimana, picco 9.9h. Il punto di partenza attuale è 40–50% di quel volume.*
