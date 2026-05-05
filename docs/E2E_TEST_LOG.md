# Test End-to-End — Procedura e Log

## Obiettivo

Validare il flusso completo di pianificazione settimanale: dal reminder Telegram → weekly review in Claude Code → commit sessioni → brief mattutino con sessione del giorno.

## Quando eseguire

**Domenica prossima** (11 maggio 2026), ore 19:00.

---

## Procedura step-by-step

### Step 1 — Ricezione reminder (automatico)

**Cosa aspettarsi:** Alle 19:00 (cron domenica `0 17 * * 0` UTC = 19:00 Europe/Rome estate) arriva su Telegram il messaggio:

> 📋 È ora della weekly review
>
> Apri Claude Code dal Mac e digita: `fai la weekly review`

**Se non arriva:**
- Controlla GitHub Actions → workflow `weekly-review` → ultimo run
- Se il run è fallito, trigger manuale: Actions → weekly-review → Run workflow
- Se il run è verde ma Telegram non riceve → verifica `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` nei secret

**Esito:** ☐ Ricevuto / ☐ Non ricevuto (causa: _____________)

---

### Step 2 — Avvia weekly review in Claude Code

Apri terminale:
```bash
cd triathlon-coach
claude
```

Digita:
```
fai la weekly review
```

**Cosa aspettarsi:** L'agente deve eseguire 5 fasi in sequenza.

---

### Step 3 — Fase 1: Raccolta dati

L'agente deve chiamare (in qualsiasi ordine):
- `get_recent_metrics(14)` — metriche ultime 2 settimane
- `get_activity_history('all', 7)` — attività ultima settimana
- `query_subjective_log(7, 'all')` — log soggettivi ultima settimana

**Verifica:** I tool call compaiono nel log della conversazione.

**Se l'agente non chiama i tool:**
- Probabile: non ha il connector MCP configurato. Verifica Claude.ai Settings → Connectors
- Workaround: forniscigli i dati manualmente con `/brief` e `/status` da Telegram

**Esito:** ☐ Tool chiamati correttamente / ☐ Mancante (dettaglio: _____________)

---

### Step 4 — Fase 2-3: Analisi e diagnosi

L'agente produce un'analisi della settimana passata:
- Volume realizzato vs pianificato
- Trend HRV e readiness
- Compliance (sessioni fatte vs previste)
- Segnali soggettivi rilevanti

**Verifica:** L'analisi cita numeri concreti (CTL, TSB, HRV z-score) e fa osservazioni specifiche, non generiche.

**Se l'analisi è generica/vaga:**
- Probabile: dati tornati vuoti dai tool. Chiedi: "mostrami i dati raw che hai ricevuto dai tool"
- Se i dati ci sono ma l'analisi è debole: è un problema di prompt. Annota per iterazione futura.

**Esito:** ☐ Analisi specifica con dati / ☐ Analisi generica (nota: _____________)

---

### Step 5 — Fase 4: Proposta piano settimanale

L'agente propone la struttura della settimana successiva:
- Schema settimanale (lun-dom) con sport, tipo, volume stimato per giorno
- Dettaglio sessioni per i prossimi 2-3 giorni (lunedì, martedì, mercoledì) con zone, durate, target
- Razionale per ogni scelta ("mercoledì soglia perché TSB +5 e HRV stabile")

**Verifica:** La proposta è coerente con:
- Fase attuale del macrociclo (vedi CLAUDE.md §3)
- Flag attivi (spalla, fascite)
- Volume della settimana precedente (±10-15%)

**Se la proposta è troppo aggressiva:**
- Rispondi: "Troppo volume, abbassa del 20%. La fascite è ancora attiva."
- L'agente deve riformulare.

**Se la proposta ignora i vincoli:**
- Annota il vincolo ignorato. Post-test: verifica che CLAUDE.md li documenti chiaramente.

**Esito:** ☐ Proposta coerente / ☐ Proposta da correggere (dettaglio: _____________)

---

### Step 6 — Fase 5: Conferma e commit

Dopo aver visto la proposta, rispondi:
```
ok
```

L'agente deve chiamare `commit_plan_change` per ogni sessione dei prossimi 2-3 giorni (minimo 3 sessioni).

**Verifica:**
1. I tool call `commit_plan_change` compaiono nel log
2. Ogni call ha i campi richiesti: `planned_date`, `sport`, `session_type`, `duration_s`, `description`

**Se l'agente non chiama commit_plan_change:**
- Probabile: non sa che il tool esiste. Digita: "ora committa le sessioni che hai proposto usando commit_plan_change"
- Se il tool fallisce: verifica errore (campo mancante? sport invalido?)

**Esito:** ☐ Sessioni committate / ☐ Errore (dettaglio: _____________)

---

### Step 7 — Verifica DB

Dopo il commit, verifica che `planned_sessions` sia popolata:

Opzione A — da Claude Code:
```
mostrami le sessioni pianificate per questa settimana
```

Opzione B — da Supabase Studio:
```sql
SELECT * FROM planned_sessions
WHERE planned_date >= '2026-05-11'
ORDER BY planned_date;
```

**Verifica:** Ci sono almeno 3 righe per lun-mer con status = 'planned'.

**Esito:** ☐ DB popolato correttamente / ☐ DB vuoto o parziale (dettaglio: _____________)

---

### Step 8 — Brief mattutino lunedì (automatico)

**Lunedì 12 maggio, ore 06:30.**

Il brief mattutino deve mostrare nella sezione "Cosa fare oggi" la sessione pianificata per lunedì, con:
- Sport + tipo + durata
- Descrizione della sessione

**Verifica:** Il brief contiene la sessione del giorno (non il messaggio "Nessuna sessione pianificata").

**Se la sessione non compare:**
- La query in `briefing.py` filtra su `planned_date = today` e `status = 'planned'`. Verifica che i dati in DB siano corretti.
- Verifica timezone: il brief usa `Europe/Rome`, il DB usa UTC. Il campo `planned_date` è una date senza timezone, dovrebbe matchare.

**Esito:** ☐ Sessione visibile nel brief / ☐ Non visibile (causa: _____________)

---

## Risultato complessivo

| Step | Esito | Note |
|------|-------|------|
| 1. Reminder Telegram | ☐ | |
| 2. Avvio review | ☐ | |
| 3. Raccolta dati (tool) | ☐ | |
| 4. Analisi e diagnosi | ☐ | |
| 5. Proposta piano | ☐ | |
| 6. Conferma e commit | ☐ | |
| 7. Verifica DB | ☐ | |
| 8. Brief lunedì | ☐ | |

**Data esecuzione:** _____________ 
**Esito globale:** ☐ PASS / ☐ FAIL (step falliti: _____________) 
**Azioni correttive necessarie:** _____________
