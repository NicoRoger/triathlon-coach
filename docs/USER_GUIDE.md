# Guida Utente — Triathlon Coach AI

---

## Panoramica del sistema

| Livello | Cosa fa | Quando |
|---------|---------|--------|
| **Automatico** | Garmin sync, brief mattutino, debrief reminder, pattern extraction, watchdog | In background, senza intervento |
| **Bot Telegram** | Log RPE, debrief, video, comandi rapidi | Tu quando vuoi |
| **Claude Code / Claude.ai** | Weekly review, pianificazione, analisi profonda, race week | Tu quando necessario |

---

## Routine giornaliera

### 06:30 — Brief mattutino (automatico)

Ogni mattina alle 06:30 ricevi su Telegram un brief con:

- **Come stai oggi**: sonno, HRV (con interpretazione), body battery
- **Carico**: CTL/ATL/TSB, training status Garmin
- **Sessione del giorno**: sessione pianificata con dettaglio (sport, durata, zone target) o indicazione di gestire autonomamente
- **Verso Lavarone**: countdown, fase corrente, focus del periodo
- **Warning**: flag attivi (HRV crash, infortunio, malattia, fascite, spalla)
- **Insight personale**: osservazione contestuale estratta dai pattern longitudinali (es. "mercoledì tendi ad avere HRV più basso — sessione tecnica oggi")

Il brief è 100% rule-based, zero LLM — costo zero, affidabilità massima.

In race week (T-7 → T+1) il brief cambia template: focus gara, indicazioni giornaliere specifiche per taper/attivazione/vigilia.

**Vuoi commentare il brief?** Fai swipe → Rispondi direttamente sul messaggio. Il bot salva come `brief_response`, non come debrief.

---

### Post-allenamento — Log soggettivo

Manda al bot un messaggio con RPE e sensazioni. Tre modalità:

```
/rpe 7
```
Log RPE rapido per l'ultima sessione.

```
/log Z2 60min bici, gambe pesanti ma watt ok. Spalla nessun problema.
```
Log libero — il bot estrae RPE, sensazioni, flag automaticamente.

```
RPE 7, gambe ok, no dolori, energia buona
```
Senza comando — se inizia con "RPE" viene salvato come debrief.

**Campi riconosciuti nel debrief:**
- RPE (1–10)
- Qualità sessione: `ottima` / `ok` / `brutta`
- Stato mentale: `concentrato` / `distratto` / `motivato` / `demotivato`
- Qualità sonno: `dormito bene` / `mal dormito` / `sonno ottimo`
- Ore sonno: `dormito 7 ore` / `8h`
- Problemi nutrition: `crampi` / `stomaco` / `nausea`
- Flag infortunio: qualsiasi parola di dolore (`male`, `dolore`, `fastidio`…)
- Flag malattia: `febbre`, `raffreddore`, `influenza`…

**Azioni rischiose — conferma esplicita**: se scrivi qualcosa che contiene una parola di dolore o malattia, il bot chiede conferma prima di salvare il flag:

```
Tu:  "ho male alla spalla forte"
Bot: "Ho capito: infortunio alla spalla. Salvo con flag attivo?"
     [✅ Sì] [✏️ Correggi] [❌ Era altro]
```
Le conferme scadono dopo 24h.

---

### Messaggi liberi — routing contestuale

Se mandi un messaggio che non è un log/debrief ma contiene temi rilevanti per la pianificazione (trasferta, infortunio, obiettivo, forma, spalla, fascite, viaggio, gara…), il bot rileva il contesto e ti propone:

```
Bot: "Sembra rilevante per la pianificazione. Vuoi:"
     [📋 Weekly review]  [⚡ Modifica ora]  [📝 Solo nota]
```

- **Weekly review** → ti ricorda di aprire Claude Code domenica
- **Modifica ora** → nota salvata, usala come input nella prossima sessione Claude Code
- **Solo nota** → salvato come log libero senza routing

---

### Video analisi tecnica

Manda un video al bot Telegram (max 20MB) con una caption che indica lo sport:

```
[video] "nuoto - analisi stile libero"
[video] "corsa - analisi appoggio"
[video] "bici - posizione in sella"
```

Il bot salva il video e chiede conferma sport se non rilevato dalla caption. La video analisi si fa in Claude Code:

```
analizza il video di nuoto di ieri
```

L'agente segue il protocollo per disciplina (priorità per spalla dx in nuoto, fascite in corsa), produce: punti critici prioritari, punti di forza, piano correzione su 3 sessioni, confronto con sessione precedente.

**Budget**: max 2 video analisi/settimana. Il sistema skippa se il budget mensile è esaurito.

---

### 21:30 — Debrief serale (automatico)

Il bot manda un reminder. Il modo corretto:

**Fai swipe → Rispondi direttamente sul messaggio del reminder**, anche ore dopo. Il bot riconosce il contesto e salva come `evening_debrief`.

Se oggi era off, ignora il reminder.

---

### 18:00 Mar/Gio/Sab — Domanda proattiva (automatico)

Il bot fa una domanda contestuale su recovery, infortuni, motivazione o tecnica.

| Bottone | Effetto |
|---------|---------|
| 💬 Rispondo dopo | Rimuove i bottoni, fai reply quando vuoi |
| 🤐 Salta | Domanda ignorata |
| 🚫 Disabilita oggi | Nessun'altra domanda per oggi |

---

## Fitness test — rilevamento automatico

Quando Garmin registra un'attività che corrisponde a un test fisiologico, il sistema lo rileva automaticamente durante il prossimo ingest (ogni 3h).

**Test riconosciuti:**

| Test | Come registrarlo su Garmin | Risultato |
|------|---------------------------|-----------|
| FTP bici (20min) | Workout "FTP Test 20min" o simile | FTP in Watt |
| FTP bici (ramp) | Ramp test Garmin | FTP in Watt |
| Soglia corsa (30min) | Corsa a sforzo massimo sostenuto 30min | Pace soglia in min/km |
| CSS nuoto (400+200) | 400m max + 200m max in piscina | CSS in sec/100m |
| LTHR corsa | Corsa a sforzo soglia con HR strap | LTHR in bpm |

**Cosa succede dopo il rilevamento:**
1. Zone calcolate automaticamente per la disciplina
2. `physiology_zones` nel DB aggiornato
3. CLAUDE.md §2 aggiornato con i nuovi valori
4. Notifica Telegram con risultato, zone calcolate e indicazione del prossimo test

Se il rilevamento automatico fallisce (workout con nome non standard), inserisci il valore manualmente in Claude Code:
```
Ho fatto il test FTP oggi: 210W, 20min, attività ID 12345678.
```

**Ciclo test pianificato**: giugno 2026 — FTP bici, soglia corsa, CSS nuoto.

---

## Routine settimanale

### Domenica sera (19:00) — Weekly review in Claude Code (manuale, ~20 min)

Ricevi il reminder su Telegram. Apri Claude Code e digita:

```
fai la weekly review
```

**Fase 0 — Sync dati**
Forza sync Garmin se l'ultimo è > 1 ora fa. Garantisce dati completi anche se hai appena finito un allenamento.

**Fase 1 — Raccolta dati**
L'agente legge dal DB tramite MCP:
- Attività completate, metriche CTL/ATL/TSB/HRV ultime 2 settimane
- Debrief, RPE, flag, malattie, infortuni
- Sessioni pianificate vs eseguite, giorno per giorno
- Video tecnici caricati durante la settimana
- Zone fisiologiche correnti

Legge anche: `CLAUDE.md`, `docs/coaching_observations.md`, `docs/progress_tracker.md`, `docs/elite_training_reference.md`.

**Fase 2 — Analisi narrativa (AI)**
Produce un'analisi di 15–20 righe: cosa ha funzionato, costo fisiologico pagato, segnali da monitorare. Non compiacente.

**Fase 3 — Comunicazione**
Presenta i punti salienti della settimana con numeri e diagnosi.

**Fase 4 — Proposta settimana successiva**
Struttura i prossimi 7 giorni rispettando:
- Struttura fissa (lun=corsa, mar=nuoto, mer=bici, gio=nuoto, ven=corsa, sab=bici, dom=corsa)
- Vincoli attivi (spalla dx: Z1-Z2 solo; fascite: +10% max/settimana)
- Volume elite come target a lungo termine (non da imitare subito — 40–50% come punto di partenza)
- Regole deterministiche (HRV crash → recovery, compliance <70% → volume -10%)

**Fase 5 — Conferma e commit**
L'agente mostra il piano. Tu dici "ok" o richiedi modifiche. Solo dopo la tua conferma esplicita scrive su `planned_sessions`.

**Fase 6 — Google Calendar**
Dopo il commit, crea/aggiorna gli eventi nel tuo Google Calendar.

**Esempio:**
```
Tu:    "Ho una cena mercoledì. Sposta la bici a giovedì."
Coach: "Proposta: mercoledì off, giovedì bici Z2 90min + nuoto tecnico 45min."
Tu:    "ok"
Coach: [committa e aggiorna calendario]
```

---

### Domenica notte (23:00) — Pattern extraction (automatico, nessuna azione richiesta)

Parte automaticamente dopo la weekly review. Non toccare niente.

**Step 1 — Adaptive planner**
Calcola compliance settimana. Applica regole o manda proposte:

| Condizione | Azione |
|------------|--------|
| RPE medio > 7.5 | Aggiunge giorno recovery (automatico) |
| Nuoto saltato | Propone cross-training (automatico) |
| Compliance < 70% | Propone riduzione volume 10% (via Telegram, richiede ok) |
| Compliance < 50% | Propone piano ridotto settimana successiva (via Telegram, richiede ok) |

**Step 2 — Pattern extraction**
Analizza 4 settimane di dati e aggiorna `docs/coaching_observations.md` con pattern biometrici e soggettivi.

**Step 3 — Update CLAUDE.md**
Aggiorna sezione "stato corrente" con CTL/TSB e fase di allenamento (solo se cambio >5% CTL o cambio fase).

**Step 4 — Update progress tracker**
Riscrive `docs/progress_tracker.md` con CTL trend 90gg, compliance ultime 4 settimane, infortuni attivi, prossima gara.

**Step 5 — Commit automatico**
Committa i file aggiornati nel repo.

---

## Race week (T-7 → T+1)

Si attiva automaticamente quando mancano 7 giorni a una gara A o B. Nessuna azione richiesta.

### Cosa cambia automaticamente

- Brief mattutino in modalità race week (template dedicato)
- Indicazioni logistica (meteo, percorso, materiale) ai giorni giusti

### Timeline

| Giorno | Sessione tipo | Note |
|--------|--------------|------|
| T-7 | Volume -40%, intensità mantenuta breve | Inizio taper |
| T-6 → T-4 | Z1-Z2 + allunghi brevi | Taper progressivo |
| T-3 | 10min Z2 + 5×30s allungo + 10min Z2 | Richiamo intensità |
| T-2 | 20-30min Z1-Z2 + 3-4 allunghi | Check materiale |
| T-1 | 15-20min Z1 | Cena ≤19:30, letto ≤22:00 |
| T-0 | RACE DAY | Brief speciale |
| T+1 | Recovery | Reminder debrief post-gara |

### Piano gara completo (manuale, Claude Code)

```
attiva race week protocol
```
Produce: warm-up, pacing per segmento, nutrition, mental checkpoints, piano contingency.

```
predici la mia performance a Lavarone
```
Range di tempo con confidence interval.

---

## Claude Code — Comandi utili

```
fai la weekly review
```
```
come sto andando questa settimana?
```
```
domani non riesco ad allenarmi, ripianifica
```
```
proponi il prossimo mesociclo di 4 settimane
```
```
analizza il video di nuoto di ieri
```
```
mostrami le mie zone aggiornate
```
```
predici la mia performance a Lavarone
```
```
attiva race week protocol
```
```
perché facciamo lavoro polarizzato in questa fase?
```

---

## Telegram — Riferimento comandi

```
/help              — lista comandi
/brief             — brief on-demand
/log <testo>       — log soggettivo libero
/rpe <1-10>        — log RPE rapido
/debrief           — avvia flow debrief manuale
/undo              — annulla l'ultimo log (ultimi 30 min)
/history           — ultimi 10 log
/history 7d        — log ultimi 7 giorni
/history rpe       — solo log con RPE
/history injury    — solo log con flag infortunio
/budget            — stato budget API Anthropic mensile
/status            — stato sync, ultimo dato Garmin, ultimo HRV
```

### Reply threading

Fai swipe → Rispondi su qualsiasi messaggio del bot:

| Messaggio originale | Come viene salvata la reply |
|---------------------|-----------------------------|
| Brief mattutino | `brief_response` |
| Reminder debrief serale | `evening_debrief` |
| Domanda proattiva | `proactive_response` |
| Proposta modulazione | Usa i bottoni ✅/❌/💬 |

Messaggi > 90 giorni vengono eliminati dal cleanup domenicale.

---

## Documenti di riferimento

| File | Contenuto | Aggiornato da |
|------|-----------|---------------|
| `CLAUDE.md` | Profilo atleta, metodologia, regole coach, stato corrente | Agente (auto) + manuale |
| `docs/elite_training_reference.md` | 114 sessioni periodo elite set 2021–mag 2022: volume, HR zone, struttura settimanale, allenamenti nuoto | Script analisi archivio FIT (statico) |
| `docs/coaching_observations.md` | Pattern longitudinali: recovery, RPE per sport, biometria, fattori contestuali | Automatico ogni domenica notte |
| `docs/progress_tracker.md` | CTL trend 90gg, compliance 4 settimane, infortuni, prossima gara | Automatico ogni domenica notte |
| `docs/training_journal.md` | Decisioni settimanali, note coach, storico mesocicli | Manuale dopo weekly review |

Il coach usa `docs/elite_training_reference.md` come **target a lungo termine** — non come punto di partenza. Volume elite: 4.2h/sett media, picco 9.9h. Punto di partenza attuale: 40–50%.

---

## Setup iniziale

### 1. Anthropic API Key

1. Carica almeno $10 su https://console.anthropic.com
2. Imposta limite mensile a **$5.50** (Settings → Limits)
3. Genera API key (Settings → Keys)
4. Aggiungi nei secret GitHub: `ANTHROPIC_API_KEY`
5. Aggiungi nei Cloudflare Workers:
   ```bash
   cd workers/telegram-bot && wrangler secret put ANTHROPIC_API_KEY
   cd workers/mcp-server && wrangler secret put ANTHROPIC_API_KEY
   ```
6. Aggiungi nel file `.env` locale

### 2. GH_PAT_TRIGGER — due configurazioni necessarie

Stesso token, due posti diversi. Genera una volta sola:

**Genera il PAT**: GitHub → Settings → Developer settings → Personal access tokens (classic) → scope `repo` + `workflow`

**A) GitHub Actions secret** (per il workflow `pattern-extraction` che committa i doc):
GitHub repo → Settings → Secrets and variables → Actions → New repository secret
- Nome: `GH_PAT_TRIGGER`

**B) Cloudflare Worker secret** (per il tool MCP `force_garmin_sync`):
```bash
cd workers/mcp-server
wrangler secret put GH_PAT_TRIGGER
wrangler deploy
```

### 3. Google Calendar

1. https://claude.ai/settings/connectors → Google Calendar → Attiva
2. Autorizza l'account Google
3. Verifica: `claude mcp list` → connector connesso

### 4. Migration SQL

Esegui le migration in `migrations/` nel Supabase SQL Editor in ordine cronologico. Vedi `migrations/README.md`.

---

## Manutenzione

### Se il watchdog suona

| Alert | Diagnosi | Fix |
|-------|----------|-----|
| Garmin sync fallita >24h | Token scaduto | `python scripts/garmin_first_login.py` → aggiorna secret `GARMIN_SESSION_JSON` |
| Briefing fallito | Supabase in pausa o token Telegram invalido | Controlla GitHub Actions → `morning-briefing` |
| Pattern extraction fallita | PAT mancante o budget API esaurito | Verifica `GH_PAT_TRIGGER` in GitHub secrets |

### Rotazione secret trimestrale

- Rigenera token Garmin
- Rigenera `DR_ENCRYPTION_KEY` (poi fai subito un nuovo snapshot)
- Verifica token Strava e bot Telegram

---

## Troubleshooting

### "Il brief non arriva alle 06:30"
Controlla Action `morning-briefing` su GitHub. Workaround: `/brief` al bot.

### "Il bot non risponde"
1. `wrangler tail` per log live del Worker
2. Verifica webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
3. Se URL morto: ri-setta il webhook con l'URL del Worker attivo

### "Il fitness test non è stato rilevato"
Il nome del workout su Garmin non corrisponde ai pattern. Inserisci manualmente in Claude Code.

### "Il pattern extraction ha fallito"
- Budget API esaurito → cade in modalità rule-based, non crasha
- `GH_PAT_TRIGGER` mancante → il commit finale fallisce ma i doc sono aggiornati sul runner

### "L'agente non ha dati aggiornati in Claude.ai"
Worker MCP down. Controlla Cloudflare Dashboard → Workers. Workaround: copia il brief Telegram come contesto.

### "Il piano proposto è troppo aggressivo"
Dì all'agente: "abbassa il volume del 20%, fascite non risolta". Non committa finché non dici "ok". Se il pattern si ripete, aggiorna CLAUDE.md §2 con vincoli più espliciti.

### "HRV risulta null nel brief"
Orologio non indossato di notte. Il readiness viene degradato a "non valutabile", il sistema non crasha.
