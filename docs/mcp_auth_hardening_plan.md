# Piano di hardening auth MCP — proposta (audit J1, 2026-06-01)

> **Stato**: PROPOSTA. Non ancora implementato (decisione utente: "proponi
> piano, non toccare ora" per non rischiare il connettore Claude.ai).

## Problema (J1)

In `workers/mcp-server/src/index.ts`:

1. **Header mancante = autenticato**: `isOAuthRequest = !auth` → una richiesta
   SENZA header `Authorization` viene trattata come OAuth valida e ottiene
   accesso read/write completo a Supabase (service key).
2. **`/oauth/token` regala il token**: restituisce `MCP_BEARER_TOKEN` (di fatto
   un proxy del service role) a chiunque faccia POST, senza verificare
   `code`/`code_verifier`. Gli authorization code (`btoa(auth_code_${Date.now()})`)
   non sono mai salvati né validati.

Impatto: chiunque conosca/indovini l'URL del worker può leggere e scrivere
tutti i dati. Mitigante attuale: URL non pubblicizzato, sistema single-user.

## Perché serve cautela

Il connettore Claude.ai è configurato con l'attuale flusso OAuth. Cambiare
l'auth può romperlo: andrà **disconnesso e riconnesso** in
Settings → Connectors → triathlon-coach, e va verificato che il discovery
(`/.well-known/oauth-authorization-server`) e il flusso PKCE combacino con ciò
che Claude.ai si aspetta.

## Piano proposto (incrementale, con rollback)

### Fase 1 — Chiudere il bypass header-mancante (basso rischio)
- Cambiare `isOAuthRequest = !auth` in: richiedere SEMPRE un bearer valido sugli
  endpoint MCP e `/dashboard-data`. Nessun header → `401`.
- Mantenere `/oauth/*` e `/.well-known/*` pubblici (necessari al discovery).
- **Test**: `curl` senza header → 401; con `Authorization: Bearer <MCP_BEARER_TOKEN>`
  → 200. Verificare che Claude.ai continui a funzionare (manda il bearer).

### Fase 2 — Authorization code reale con PKCE (medio rischio)
- In `/oauth/authorize`: generare un `code` casuale, salvarlo in KV con
  `code_challenge`, `code_challenge_method=S256`, scadenza 5 min, redirect_uri.
- In `/oauth/token`: validare `code` (lookup KV, non scaduto, redirect_uri
  combacia) e `code_verifier` (SHA256 == code_challenge). Solo allora emettere
  un **access token dedicato** (random, salvato in KV con TTL), NON il service
  token grezzo.
- Il worker mappa internamente l'access token → autorizzazione; il service key
  Supabase resta server-side e non lascia mai il worker.
- **Test**: rieseguire il flusso completo da Claude.ai (disconnetti/riconnetti),
  verificare che i tool rispondano; un POST diretto a `/oauth/token` senza code
  valido → 400.

### Fase 3 — Rotazione e revoca
- TTL sull'access token (es. 30 giorni) + endpoint di revoca.
- Documentare la rotazione del `MCP_BEARER_TOKEN`/secret in `RUNBOOK.md`.

## Rollback
Ogni fase è un commit separato sul worker. In caso di rottura del connettore:
`wrangler rollback` al deploy precedente e riconnessione in Claude.ai.

## Finestra consigliata
Eseguire quando sei al PC e puoi testare subito la riconnessione in Claude.ai
(non in race week, non prima di una sessione che dipende dai dati live).

## Altri item MCP minori (J2–J6) da includere nello stesso pass
- J2: `req.json()` e `rpc.params` guardati → errori JSON-RPC corretti (-32700/-32602).
- J3: `getRaceContext` legge dalla tabella `races`, non da `planned_sessions?session_type=eq.race`.
- J4: verificare `existingResp.ok` prima di `.json()` nei check di esistenza.
- J5: `forceGarminSync` ritorna subito `status:"triggered"` invece di busy-wait 90s.
- J6: definizione "zona corrente" unica tra dashboard e MCP (`valid_to`).
