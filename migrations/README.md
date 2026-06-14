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
| `2026-05-30-rls-and-fk-integrity.sql` | Abilita RLS sulle 8 tabelle scoperte (predictions, outcomes, beliefs, beliefs_history, recommendations, hypothesis_tests, decision_audit, sent_reminders) + ON DELETE SET NULL sulle FK orfane | ⬜ Da eseguire |
| `2026-05-30-seed-run-zones-provisional.sql` | Zone corsa provvisorie dal test soglia 30/05 (BUG-010) | ⬜ Da eseguire |

## Note

- Le migration usano `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` dove possibile, quindi sono idempotenti (puoi eseguirle più volte senza danni).
- Dopo l'esecuzione, segna lo stato come ✅ in questa tabella.

## ⚠️ Standard obbligatorio per ogni NUOVA tabella

Coerente col design single-user di `sql/schema.sql` ("nessuna policy = solo
`service_role` accede"), **ogni nuova tabella in `public` deve abilitare RLS**
nella stessa migration che la crea:

```sql
ALTER TABLE <nuova_tabella> ENABLE ROW LEVEL SECURITY;
```

Senza policy = deny-all per `anon`/`authenticated`; la `service_role` key
(usata da backend Python, MCP worker, Telegram worker) bypassa comunque RLS.

**NON** concedere `GRANT ... TO anon`: esporrebbe la tabella alla Data API
pubblica. Questo è anche l'approccio corretto rispetto all'avviso Supabase del
30/05/2026 sull'esposizione delle tabelle `public` (vedi `docs/audit_2026-05-30.md`).
