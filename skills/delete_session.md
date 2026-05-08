---
name: delete_session
description: Cancella una sessione pianificata dal DB e, se presente, rimuove l'evento corrispondente da Google Calendar. Da usare quando l'atleta chiede di eliminare una sessione specifica.
---

# Delete Session

## Quando usare

Trigger:
- Atleta chiede di eliminare una sessione specifica: "cancella la sessione di giovedì", "rimuovi il lungo di domenica"
- Replanning che richiede eliminazione (non spostamento) di una sessione

## Procedura

1. Identifica la sessione da cancellare:
   - Chiama `get_planned_session(date)` per la data indicata
   - Se ci sono più sessioni per quella data (es. mattina nuoto + sera corsa), chiedi conferma su quale cancellare

2. Mostra all'atleta cosa verrà cancellato:
   ```
   Cancello: [sport] — [session_type] del [data]
   Durata: [duration_s/60] min | TSS target: [tss]
   Descrizione: [description breve]

   Confermi? sì/no
   ```

3. Dopo conferma esplicita:
   a. Se la sessione ha un `calendar_event_id`:
      - Chiama `gcal:delete_event` con quell'ID per rimuovere l'evento dal calendario
      - Se gcal fallisce, segnala ma prosegui
   b. Aggiorna la sessione in DB settando `status = 'cancelled'` via `commit_plan_change` con lo stesso date/sport ma status cancelled
      - Nota: non eliminare la riga, marca come cancelled per mantenere lo storico

4. Conferma all'atleta:
   ```
   ✅ Sessione [sport] di [data] cancellata.
   [Se gcal ok: Evento rimosso dal calendario.]
   [Se gcal fallito: ⚠️ Evento calendario non rimosso — rimuovilo manualmente.]
   
   TSS settimanale aggiornato: [nuovo totale]
   ```

## Vincoli

- **Mai cancellare senza conferma esplicita.** Pattern: proponi → aspetta → esegui.
- Se la cancellazione lascia un "buco" eccessivo nel carico settimanale (>20% sotto target), segnala e proponi sostituzione.
- Non cancellare sessioni di test fitness schedulate senza discutere le implicazioni con l'atleta.

## Cosa NON fare

- Non cancellare sessioni passate (solo future o del giorno corrente se non ancora eseguita).
- Non cancellare senza prima verificare l'impatto sul carico settimanale.
- Non improvvisare una sostituzione automatica — se serve, chiama la skill `adjust_week`.
