# Runbook — Operatività quotidiana

## Routine giornaliera attesa

| Quando | Cosa fai | Cosa fa il sistema |
|--------|----------|-------------------|
| 06:30 | Ricevi brief Telegram | Action genera brief rule-based |
| Pre-allenamento | (opzionale) chiedi a Claude.ai approfondimento | MCP server fornisce contesto |
| Post-allenamento | Vocale o testo a Telegram con RPE + sensazioni | Bot logga in `subjective_log` |
| Sera 21:30 | Bot ti scrive con 4 domande standard | Salva debrief, append a journal |
| Settimanale (dom sera) | Apri Claude Code, "rivedi settimana e proponi prossima" | Genera proposta mesociclo, attendi conferma |
| Mensile | Test fitness suggeriti dall'agente | Aggiornano zone in DB |

## Comandi Telegram bot

```
/brief          — genera e invia brief on-demand
/log <testo>    — log soggettivo libero (RPE, sensazioni)
/rpe <1-10>     — log RPE rapido per ultima sessione
/debrief        — avvia flow debrief serale manuale
/status         — stato sync, ultimo dato Garmin, ultimo HRV
/help           — lista comandi
```

## Cosa fare quando...

### Sei in trasferta solo col telefono
**Tutto continua a funzionare.** Telegram bot è la tua interfaccia primaria. Per
analisi profonda apri Claude.ai mobile, il connector tira già i dati. Niente da fare.

### Garmin non sincronizza da 24h
Il watchdog ti avverte. Cause comuni:
1. Token Garmin scaduto → esegui `scripts/garmin_first_login.py` localmente, aggiorna secret
2. API Garmin down → aspetta, riprova domani
3. Update di `garminconnect` rotto → check GitHub issues della libreria, eventualmente pin versione

### Stai male / infortunato
Manda a Telegram: `/log malato T 38.2 mal di gola` o `/log dolore ginocchio dx 5/10`.
Il bot setta flag automatici (`illness_flag`, `injury_flag`). Il brief del giorno
dopo proporrà recovery o stop, secondo regole in CLAUDE.md §5.

### Vuoi modificare il piano della settimana
Apri Claude Code o Claude.ai:
> "Ho una cena imprevista venerdì sera, sposta la sessione lunga."

L'agente propone, tu confermi, modifica viene scritta su DB.

### Vuoi cambiare obiettivo gara
Edit manuale di `CLAUDE.md` §Profilo → commit. L'agente leggerà la nuova versione
al prossimo accesso. Per cambi grossi (es. cambio gara A), apri conversazione
Claude Code per ridisegnare il macrociclo.

### Il sistema sembra dare suggerimenti strani
Diagnosi prima di patch (filosofia Audio Guided Condotta):
1. Controlla `last_sync_at` di tutte le sorgenti — dati freschi?
2. Controlla `daily_wellness` ultimi 7 giorni — HRV plausibile?
3. Controlla `health.flags` — quali sono attivi e perché?
4. Solo allora intervieni sul layer giusto

## DR e backup

- **Snapshot DB cifrato**: ogni notte 02:00 UTC, push su `dr-snapshots/` bucket Supabase
  + commit hash riferimento in repo
- **Restore**: `scripts/dr_restore.py <snapshot-id>` — testato in setup, retest trimestrale
- **Disaster totale Supabase**: nuovo progetto + restore da snapshot più recente.
  RTO atteso: 30 minuti. RPO: 24h (giorno di snapshot perso).

## Manutenzione periodica

| Frequenza | Task |
|-----------|------|
| Settimanale | Review piano, debrief mancanti, anomalie |
| Mensile | Test fitness se schedulato, controllo costi (deve essere €0) |
| Trimestrale | Rotazione secret, test DR restore, review CLAUDE.md profilo |
| Annuale | Review macro: gare, obiettivi long-term, evoluzione stack |

## Limiti noti

- Sonno e HRV affidabili solo con orologio indossato di notte. Notti senza
  orologio = `daily_wellness.hrv` null = readiness degradato a "non valutabile".
- VO2max stimato Garmin è approssimativo. Va bene come trend, non come valore assoluto.
- Open water: distanze GPS in nuoto sono spesso imprecise. Cross-check con tempo/feel.

## Quando NON fidarti dell'agente

L'agente è uno strumento, non un medico né un coach umano élite. Quando:
- Sintomi medici seri → medico/fisioterapista
- Decisioni di carriera sportiva (es. selezione gara A internazionale) → confronto umano
- Fasi di forte stress psicologico → l'agente non è terapeuta. Cerca supporto umano.
