# Phase 4: Live Behavior Verification - Context

**Gathered:** 2026-06-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Verificare che il sistema end-to-end funzioni correttamente su dati reali, e correggere i problemi che la verifica trova. Questa fase copre: brief con zone numeriche precise da `physiology_zones`, analisi post-sessione generate da Gemini, flusso modulazioni con inline buttons Telegram (K5 + DEPLOY-04), e budget tracker Anthropic.

**In scope:**
- Verifica e fix zone nel brief (VERIFY-03, FITNESS-04): briefing.py legge physiology_zones e mostra Z1-Z5 inline con watt/pace/HR
- Verifica e fix pipeline session_analyses (VERIFY-04): post_session_analysis triggerato da ingest.yml, righe in DB con model_used='gemini-2.5-flash'
- Test end-to-end modulazione (VERIFY-05 + DEPLOY-04): scenario tap ✅ → planned_sessions + accepted→applied
- Ispezione budget tracker (VERIFY-06): codice + tabella api_usage, nessun test live costoso
- Script verify_live_behavior.py: read-only con staleness check

**Out of scope:**
- Struttura avanzata sessione (riscaldamento/intervalli/defatigamento) → Phase 5
- FTP test scheduling per bici → Phase 5
- Qualità del testo delle analisi post-sessione → Phase 9
- MCP auth hardening → Phase 11

</domain>

<decisions>
## Implementation Decisions

### Fix scope — "Verify + Fix" non "Verify + Document"

- **D-01:** Phase 4 **corregge** i problemi che trova. Non documenta per fasi successive. La fase è completa solo quando il comportamento live corrisponde ai success criteria nel ROADMAP.
- **D-02:** Confine netto con Phase 5: Phase 4 porta le zone numeriche nel brief (presenti e corrette); Phase 5 porta la struttura avanzata della sessione (riscaldamento, intervalli specifici, defatigamento). Phase 4 non tocca la prescription structure.
- **D-03:** Se post_session_analysis non è triggerato da ingest.yml, Phase 4 aggiunge lo step nel workflow. Questo è un fix di pipeline (come apply_accepted_modulations in Phase 3), non un fix di qualità dell'analisi.
- **D-04:** VERIFY-06 verificato con ispezione codice (`coach/utils/budget.py`) e query su `api_usage` table per vedere la spesa reale. Nessun test live che provochi spesa aggiuntiva o sfiori la soglia di degrado.

### Modulation test setup (VERIFY-05 + DEPLOY-04)

- **D-05:** Prima tentativo via trigger manuale: `python -m coach.coaching.post_session_analysis --recent` su un'attività Garmin recente. Se genera segnale sufficiente (HRV basso + carico), produce una `plan_modulation` naturale. Percorso preferito per realismo.
- **D-06:** Fallback se il trigger naturale non produce modulazione entro 1-2 run: INSERT sintetico diretto in `plan_modulations` (status='pending', corpo realistico). Documenta che il path di generazione è testato separatamente da quello di conferma.
- **D-07:** Dopo tap ✅ su Telegram, trigger ingest manuale immediato (`python -m coach.ingest.garmin` o `force_garmin_sync` via MCP tool). Non aspettare il ciclo automatico da 3h — verifica immediata che `planned_sessions` sia aggiornato.
- **D-08:** VERIFY-05 e DEPLOY-04 bundlati in un unico scenario end-to-end: lo stesso tap ✅ verifica sia K5 (Telegram bot → planned_sessions) sia apply_accepted_modulations (accepted→applied nel log ingest). Un solo test di scenario copre entrambi.

### Brief zone display (VERIFY-03 + FITNESS-04)

- **D-09:** Primo passo di Phase 4: leggere `coach/planning/briefing.py` + query `bot_messages` per capire lo stato attuale. Decidere il fix in base a cosa manca (lettura physiology_zones assente, valori hard-coded, o format diverso).
- **D-10:** Formato zone inline nella sessione: `Z2: 142-178W / 5:10-5:45 min/km` (compact, mobile-friendly). Le zone appaiono accanto alla descrizione della sessione, non in un blocco separato.
- **D-11:** Se FTP bici non è in DB (test non ancora processato), il brief mostra placeholder: `[FTP non misurato — zone bici TBD]`. Non blocca Phase 4. Non schedula il test FTP (→ Phase 5).
- **D-12:** FTP test scheduling → Phase 5. Phase 4 verifica e fixa le zone esistenti (nuoto, corsa); bici con placeholder se FTP mancante.

### Verification evidence format

- **D-13:** Creare `scripts/verify_live_behavior.py` — unico script read-only che controlla: (1) brief zone in `bot_messages` recenti, (2) `session_analyses` recenti con model_used check, (3) `plan_modulations` status e timestamps, (4) `api_usage` spesa Anthropic vs soglie budget.
- **D-14:** Script read-only informativo, **nessun exit 1** (come verify_analytics.py e verify_physiology.py). Output pass/fail per ogni check ma non rompe pipeline. Per audit umano, non CI.
- **D-15:** Include timestamp staleness check per ogni area: mostra "ultima session_analysis: 2026-06-05 (2 giorni fa) — OK" o "ultima session_analysis: 2026-05-28 (10 giorni fa) — STALE". Utile per diagnosi pipeline stall.

### Claude's Discretion

- Struttura interna di verify_live_behavior.py (numero di sezioni, stile output) — segui il pattern di verify_analytics.py
- Threshold staleness (quanti giorni = stale) per session_analyses e plan_modulations — usa 7 giorni come cutoff ragionevole
- Messaggio di log quando la verifica trova un fix da applicare
- Gestione errori in briefing.py per physiology_zones mancante o None

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements e roadmap
- `.planning/REQUIREMENTS.md` §Verifica Fix Precedenti (VERIFY-03, VERIFY-04, VERIFY-05, VERIFY-06) e §Correttezza Fitness Test & Zone (FITNESS-04) — acceptance criteria definitivi
- `.planning/ROADMAP.md` §Phase 4 — goal, success criteria (5 items), requirements mappati

### Codice da verificare e potenzialmente fixare
- `coach/planning/briefing.py` — **LEGGERE PRIMA** per capire stato attuale zone nel brief; entry point fix D-09/D-10/D-11
- `coach/coaching/post_session_analysis.py` — trigger manuale per generare modulazione (D-05); verifica che il job funzioni
- `coach/coaching/modulation.py` — logica generazione plan_modulations; verificare che path completo funzioni
- `coach/utils/budget.py` — soglia degrado Sonnet→Haiku a €4.00, hard block a $4.80 (D-04)
- `workers/telegram-bot/src/index.ts` — fix K5 (accept tap → planned_sessions); già deployato in Phase 3, testare live
- `.github/workflows/ingest.yml` — verificare se post_session_analysis è già wired; aggiungere se manca (D-03)

### Context Phase 3 (dipendenze live)
- `.planning/phases/03-deploy-pipeline-resilience/03-CONTEXT.md` — decisioni D-04 (apply_accepted_modulations), D-06 (D-03 wrangler deploy)
- `.planning/phases/03-deploy-pipeline-resilience/03-VERIFICATION.md` — conferma cosa è live e cosa era stato deferito (K5)

### Audit e bug
- `docs/audit_resilience_2026-06-01.md` §K (K2-K5 bot fixes) — dettaglio fix K5 già deployato; §DEPLOY-04 (apply_accepted_modulations flow)

### Pattern script operativi (per verify_live_behavior.py)
- `scripts/verify_analytics.py` — pattern di riferimento: struttura, output formattato, logging, load_dotenv, main()
- `scripts/verify_physiology.py` — secondo esempio; show come fare pass/fail display per ogni check
- `coach/utils/supabase_client.py` — `get_supabase()` per connessione DB reale

### Schema DB (tabelle da interrogare)
- `sql/schema.sql` — struttura: `session_analyses` (model_used, created_at), `plan_modulations` (status, created_at), `api_usage` (cost_usd, created_at), `bot_messages` (type, content, created_at), `physiology_zones` (discipline, zones_json)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/verify_analytics.py` — template completo per verify_live_behavior.py: load_dotenv, logging, check per sezione con pass/fail, main() con summary finale
- `scripts/verify_physiology.py` — mostra come fare bounds check e confronto DB vs expected per ogni disciplina
- `coach/utils/supabase_client.get_supabase()` — connessione al DB reale; richiede `.env` con SUPABASE_URL + SUPABASE_SERVICE_KEY

### Established Patterns
- Script in `scripts/` seguono: `load_dotenv()`, `logging.getLogger(__name__)`, sezioni con header stampati, `if __name__ == "__main__": main()`
- `PYTHONPATH=.` richiesto per tutti i comandi Python nel progetto
- Ingest.yml usa step separati con `python -m coach.X.Y` — stesso pattern per aggiungere post_session_analysis step
- `bot_messages` table ha colonne `type`, `content`, `created_at` — usata per idempotency check brief e per leggere l'ultimo brief inviato

### Integration Points
- `briefing.py` → `physiology_zones` table: il fix zone consiste nell'aggiungere una query a questa tabella e formattare le zone inline nella sessione
- `ingest.yml` → `post_session_analysis`: nuovo step dopo il blocco ingest Garmin, stesso pattern di `apply_accepted_modulations`
- `plan_modulations` → Telegram bot (K5): il bot legge status='pending', manda inline keyboard; su tap ✅ aggiorna status='accepted'; apply_accepted_modulations in ingest converte accepted→applied in planned_sessions

</code_context>

<specifics>
## Specific Ideas

- Formato zone nel brief (D-10): `Z2: 130-155bpm | 5:10-5:45/km` per corsa, `Z2: 142-178W | 140-160bpm` per bici, `Z1-Z2: < 1:35/100m` per nuoto
- Placeholder FTP (D-11): `[FTP bici non ancora misurato — usa Z2 HR: 140-160bpm come riferimento]`
- Output verify_live_behavior.py (D-15):
  ```
  === Live Behavior Check — 2026-06-07 ===

  [BRIEF ZONES]
  ✓ briefing.py legge physiology_zones
  ✓ Ultima sessione brief include zone inline (2026-06-07)

  [SESSION ANALYSES]
  ✓ session_analyses: 12 righe (ultima: 2026-06-05, 2 giorni fa — OK)
  ✓ model_used: gemini-2.5-flash su tutte le righe recenti

  [PLAN MODULATIONS]
  ✓ plan_modulations: status breakdown: pending=0, accepted=0, applied=2
  ✓ Ultima modulazione: 2026-06-04 (3 giorni fa — OK)

  [BUDGET TRACKER]
  ✓ Spesa Anthropic mese corrente: $0.45 (soglia degrado €4.00: OK)
  ✓ budget.py: DOWNGRADE_THRESHOLD = 4.0, BLOCK_THRESHOLD = 4.8

  === Riepilogo: 4/4 OK ===
  ```

</specifics>

<deferred>
## Deferred Ideas

- FTP test bici scheduling: Phase 4 mostra placeholder se FTP mancante; il test viene proposto e schedulato in Phase 5 (§5.3 CLAUDE.md — test ogni 4-6 settimane)
- Struttura sessione avanzata nel brief (riscaldamento/intervalli/defatigamento) → Phase 5 (Workout Prescription Quality)
- Exit 1 su failure in verify_live_behavior.py per uso CI — non in scope Phase 4; richiederebbe fixture dati o mock del DB per essere stabile in CI clean

</deferred>

---

*Phase: 4-live-behavior-verification*
*Context gathered: 2026-06-07*
