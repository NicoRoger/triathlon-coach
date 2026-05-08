# Test manuale — force_garmin_sync

## Prerequisiti

1. PAT GitHub con scope `repo` + `workflow` configurato come secret Worker:
   ```bash
   wrangler secret put GH_PAT_TRIGGER
   ```
2. Worker MCP deployed: `wrangler deploy` da `workers/mcp-server`

## Test 1 — Sync recente (skip)

Se l'ultimo ingest è avvenuto < 1 ora fa, il tool deve restituire `skipped`.

```bash
curl -X POST https://mcp-server.<account>.workers.dev/mcp \
  -H "Authorization: Bearer <MCP_BEARER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "force_garmin_sync",
      "arguments": {}
    }
  }'
```

**Expected output** (se sync recente):
```json
{
  "status": "skipped",
  "reason": "sync recent (X minutes ago)",
  "last_sync": "2026-05-06T..."
}
```

## Test 2 — Sync necessario (trigger)

Aspetta che l'ultimo sync sia > 1 ora fa, poi ripeti la stessa chiamata.

**Expected output** (dopo ~30-60s):
```json
{
  "status": "completed",
  "duration_s": 45,
  "last_sync": "2026-05-06T..."
}
```

**Oppure** (se il workflow è lento):
```json
{
  "status": "timeout",
  "warning": "sync triggered but not yet visible",
  "duration_s": 90
}
```

## Test 3 — Verifica su GitHub

Dopo il trigger, controlla su GitHub Actions che il workflow `ingest` sia partito:
- https://github.com/NicoRoger/triathlon-coach/actions/workflows/ingest.yml

Deve apparire un run con trigger "workflow_dispatch".

## Verifica DB

Controlla in Supabase SQL Editor:
```sql
SELECT * FROM health WHERE component = 'garmin_sync';
```

Il campo `last_success_at` deve essere aggiornato dopo il sync completato.
