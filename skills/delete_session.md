---
name: delete_session
description: Cancella o sposta una sessione pianificata, con cleanup di Google Calendar. Da usare quando l'atleta chiede di eliminare o spostare una sessione specifica.
---

# Delete / Reschedule Session

## Quando usare

Trigger:
- Atleta chiede di eliminare una sessione: "cancella la sessione di giovedì", "rimuovi il lungo di domenica"
- Atleta chiede di spostare una sessione: "sposta il test di nuoto a giovedì", "metti la bici di sabato a domenica"
- Replanning che richiede eliminazione o spostamento di una sessione esistente

## Tool disponibili

- `delete_session` — cancella una sessione (soft di default, hard per duplicati/errori)
- `reschedule_session` — sposta una sessione a una nuova data/sport mantenendo tutto
- `get_planned_session(date)` — per ispezionare cosa c'è in una data

Entrambi accettano `session_id` (preferito, se lo conosci da get_upcoming_plan /
get_weekly_context) oppure la coppia `date` + `sport`.

## Procedura — CANCELLAZIONE

1. Identifica la sessione: se non hai il `session_id`, usa `get_planned_session(date)`.
   Se per quella data ci sono più sessioni (sport diversi), chiedi quale.

2. Mostra all'atleta cosa verrà cancellato e chiedi conferma:
   ```
   Cancello: [sport] — [session_type] del [data] ([durata]min, TSS [tss]).
   Confermi? sì/no
   ```

3. Dopo conferma esplicita, chiama `delete_session`:
   - **Soft (default)**: `delete_session(session_id=...)` → marca `cancelled`, sparisce
     dal piano ma resta nello storico. Usa questo nel caso normale.
   - **Hard**: `delete_session(session_id=..., hard=true)` → elimina la riga. Usa
     SOLO per duplicati o sessioni create per errore (es. un test "fantasma").

4. Cleanup calendario: il tool restituisce `calendar_event_id`. Se non è null,
   chiama `gcal:delete_event` con quell'ID. Se gcal fallisce, segnala ma prosegui.

5. Conferma all'atleta:
   ```
   ✅ Sessione [sport] del [data] cancellata.
   [Se gcal ok: Evento rimosso dal calendario.]
   [Se gcal fallito: ⚠️ Evento calendario non rimosso — rimuovilo manualmente.]
   ```

## Procedura — SPOSTAMENTO

1. Identifica la sessione (come sopra) e la nuova data.

2. Mostra la proposta e chiedi conferma:
   ```
   Sposto: [sport] — [session_type] dal [data vecchia] al [data nuova].
   Confermi? sì/no
   ```

3. Dopo conferma, chiama `reschedule_session(session_id=..., new_date=...)`
   (aggiungi `new_sport` solo se cambia anche lo sport).
   - Se restituisce `status: "conflict"`, la data di destinazione ha già una
     sessione attiva di quello sport. Riferiscilo all'atleta e proponi: cancellare
     quella sessione prima, oppure scegliere un'altra data. NON forzare.

4. Cleanup calendario: il tool restituisce `calendar_event_id`. Se non è null,
   aggiorna l'evento su Google Calendar (`gcal:update_event`) con la nuova data.

5. Conferma all'atleta con il nuovo giorno e il calendario aggiornato.

## Vincoli

- **Mai cancellare o spostare senza conferma esplicita.** Pattern: proponi → aspetta → esegui.
- Se la cancellazione lascia un "buco" eccessivo nel carico settimanale (>20% sotto
  target), segnala e proponi una sostituzione.
- Non cancellare sessioni di test fitness schedulate senza discutere le implicazioni.

## Cosa NON fare

- Non cancellare sessioni passate già eseguite (solo future o del giorno corrente se non ancora fatta).
- Non usare `hard=true` per una cancellazione normale: serve a rimuovere errori/duplicati, non a gestire un cambio di programma.
- Non improvvisare una sostituzione automatica — se serve, usa la skill `adjust_week`.
