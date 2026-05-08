---
name: adjust_week
description: Ribilancia il carico settimanale dato un evento (malattia, viaggio, fatica). Usa quando l'atleta segnala un cambio di contesto che invalida il piano.
---

# Adjust Week

## Quando usare
Trigger:
- Atleta dichiara malattia / infortunio
- Trasferta/viaggio non previsto
- Flag `fatigue_warning` o `anticipate_recovery_week` attivo
- Richiesta esplicita: "sposta", "rimuovi", "adatta la settimana"

## Procedura
1. Leggi `get_planned_session` per ogni giorno residuo della settimana
2. Leggi `get_recent_metrics(7)` per stato fatigue
3. Leggi `query_subjective_log(7, kind='all')` per contesto
4. Costruisci proposta che:
   - **Preserva** il volume settimanale totale se possibile
   - **Sposta** intensità verso giorni con readiness migliore
   - **Sostituisce** sessioni perse con qualità >> quantità
   - **Mantiene** la sessione lunga se è gara A in <8 settimane
5. Per ogni cambio: chiamata `propose_plan_change` separata
6. Riassunto finale con before/after
7. Dopo conferma atleta e `commit_plan_change`, aggiorna Google Calendar:
   - Sessione **spostata**: `gcal:delete_event` sul vecchio `calendar_event_id` + `gcal:create_event` nella nuova data
   - Sessione **modificata** (stessa data): `gcal:update_event` con nuovi dettagli
   - Sessione **cancellata**: `gcal:delete_event` se ha `calendar_event_id`
   - Se gcal fallisce, non bloccare — segnala all'utente

## Output template
```
Settimana ridisegnata. Stato: [readiness, contesto].

PRIMA → DOPO
Lun: Z2 60min          → confermata
Mar: Soglia bici 75min → spostata a giovedì (riposo gambe oggi)
Mer: Recovery          → confermata
Gio: Lungo bici        → SCAMBIATA con soglia di martedì
Ven: Off               → confermato
Sab: Brick 90min       → ridotto a 60min (recupero malattia)
Dom: Lungo corsa       → confermato

TSS settimanale: 480 → 420 (-12%)
Razionale: malattia martedì + flag post_illness_caution.

Approvi? Risposta sì/no/modifica.
```

## Vincoli duri
- Mai due sessioni intense (Z4+) in giorni consecutivi
- Mai brick + lungo nello stesso weekend di taper
- Riposo settimanale: ≥1 giorno completo OR 2 giorni recovery soft
- Carico settimanale: variazione max ±20% rispetto a piano originale (sopra serve riprogrammazione mesociclo)

## Cosa NON fare
- Non scrivere su DB direttamente. Sempre `propose_plan_change` → conferma.
- Non improvvisare nuovi tipi di sessione fuori dal repertorio standard.

