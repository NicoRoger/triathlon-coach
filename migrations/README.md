# Migrations

File SQL da eseguire manualmente nel **Supabase SQL Editor** per aggiornare lo schema del database.

## Come eseguire

1. Vai su https://supabase.com/dashboard → seleziona il progetto `triathlon-coach`
2. Apri **SQL Editor** → **New Query**
3. Incolla il contenuto del file `.sql` della migration
4. Clicca **Run**
5. Verifica che l'output sia senza errori

## Ordine di esecuzione

Le migration sono ordinate per data nel nome file. Eseguile in ordine cronologico.

| File | Descrizione | Stato |
|------|-------------|-------|
| `2026-05-06-add-calendar-event-id.sql` | Aggiunge `calendar_event_id` a `planned_sessions` | ⬜ Da eseguire |

## Note

- Le migration usano `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` dove possibile, quindi sono idempotenti (puoi eseguirle più volte senza danni).
- Dopo l'esecuzione, segna lo stato come ✅ in questa tabella.
