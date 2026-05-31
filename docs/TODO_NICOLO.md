# 📋 Azioni manuali — Nicolò

Cose che **devo fare io** (richiedono accessi/credenziali che l'agente non ha:
Supabase SQL Editor, Cloudflare `wrangler`, GitHub settings). L'agente aggiorna
questo file man mano; io spunto ✅ quando fatto.

> Legenda: 🔴 urgente · 🟡 importante · 🟢 quando capita

---

## 🔴 1. Eseguire le migration in sospeso (Supabase SQL Editor)
Dashboard Supabase → progetto `triathlon-coach` → SQL Editor → New Query → incolla
ed esegui, **in ordine**. Sono idempotenti.

Nuove di questo ciclo:
- [ ] `migrations/2026-05-30-rls-and-fk-integrity.sql` — sicurezza (RLS sulle 8 tabelle scoperte) + integrità FK. Risponde anche all'email Supabase.
- [ ] `migrations/2026-05-30-seed-run-zones-provisional.sql` — carica le zone corsa dal test del 30/05 (soglia 4:23/km, LTHR 183).

(Niente migration per lo stato `expired` delle modulazioni: la colonna non ha
CHECK constraint, quindi il nuovo stato è già valido. Le 14 proposte appese
verranno auto-scadute dal cron — nessuna azione tua.)

Verifica RLS dopo l'esecuzione:
```sql
SELECT relname, relrowsecurity FROM pg_class
WHERE relname IN ('predictions','outcomes','beliefs','beliefs_history',
                  'recommendations','hypothesis_tests','decision_audit','sent_reminders');
-- relrowsecurity deve essere true per tutte
```

> Nota: ci sono anche migration più vecchie ancora ⏳ in `docs/OPEN_ISSUES.md`
> (tabella "Pending migrations"). Se non le hai mai eseguite, falle prima di queste.

---

## 🔴 2. Redeploy dei Cloudflare Workers
Le modifiche al codice dei worker hanno effetto **solo dopo il deploy**.

- [ ] **mcp-server** (weekly review più snella + nuovo tool `commit_physiology_zones`):
  ```bash
  cd workers/mcp-server && wrangler deploy
  ```
- [ ] **telegram-bot** — solo se in futuro tocchiamo quel worker (per ora non serve).

---

## 🟡 3. Rotazione PAT GitHub `GH_PAT_TRIGGER`
Il token che fa funzionare `force_garmin_sync` sta per scadere.
- [ ] Rigenera il token (meglio: **fine-grained PAT** sul solo repo `nicoroger/triathlon-coach`, permesso *Actions: Read and write*).
- [ ] Aggiorna il secret del worker:
  ```bash
  cd workers/mcp-server && wrangler secret put GH_PAT_TRIGGER
  ```
- [ ] Verifica: da Claude.ai chiama `force_garmin_sync` → il workflow `ingest` parte.

Dettagli in `docs/RUNBOOK.md → Rotazione secret/token`.

---

## 🟢 4. Pulizia modulazioni vecchie — NESSUNA AZIONE
Le 14 modulazioni `proposed` mai chiuse vengono ora auto-scadute (`expired`) dal
job proattivo (gira ogni 30 min) quando superano i 4 giorni. È la causa per cui
vedevi il sistema "confuso" nella weekly review. Si risolve da solo dopo il
deploy/prossimo run del workflow `proactive-reminders`.

---

## ✅ Fatte
(sposta qui le voci completate)
