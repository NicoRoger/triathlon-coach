# Phase 2: Fitness Test Correctness - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Verificare che i valori di `physiology_zones` nel DB (FTP bici, soglia corsa, CSS nuoto) derivino dai test fitness eseguiti da Nicolò a giugno 2026, siano entro bounds fisiologici plausibili, e non siano stati corrotti dai bug E1/E2.

I test fitness (FTP bici, soglia corsa, CSS nuoto) **sono già stati eseguiti** su Garmin a giugno 2026. Non si sa se il processore li abbia già elaborati automaticamente — da verificare. Phase 2 copre:
1. Creare `scripts/verify_physiology.py` — script informativo read-only che mostra le zone in DB e le confronta con i campi CLAUDE.md
2. Creare `scripts/cleanup_physiology_zones.py` — script con `--confirm` per cancellare righe con valori fuori bounds (corrotte da E1/E2 pre-fix)
3. Se `physiology_zones` è vuota, triggerare il processore sui test già eseguiti (con finestra temporale ampliata)
4. Verificare che i valori risultanti siano nei bounds plausibili (FTP 80-450W, threshold 150-360 s/km, CSS 70-150 s/100m)

Non rientra in Phase 2: migrazione E4 (UNIQUE constraint) → Phase 3, deploy, qualità del brief, test LTHR.

</domain>

<decisions>
## Implementation Decisions

### Script verify_physiology.py (VERIFY-02 / FITNESS-02)

- **D-01:** Aggiungere `scripts/verify_physiology.py` — script read-only informativo, nessun exit 1, nessuna modifica al DB
- **D-02:** Output per ogni disciplina (swim/bike/run): metodo, data test, valori (FTP/threshold/CSS), indicazione bounds [OK/FUORI RANGE] con i limiti mostrati
- **D-03:** Include confronto con campi CLAUDE.md: `ftp_attuale_w`, `threshold_pace_per_km`, `css_attuale_per_100m` — evidenziare discrepanze DB vs CLAUDE.md
- **D-04:** Se tabella vuota → stampa `physiology_zones: vuoto — test eseguiti ma non processati, usare --trigger-processor` (o simile istruzione)
- **D-05:** Nessun controllo del codice sorgente (E1/E2) — i test e1/e2 già passano; lo script si concentra sui dati live

### Script cleanup_physiology_zones.py (FITNESS-01 / FITNESS-02)

- **D-06:** Script separato `scripts/cleanup_physiology_zones.py` — separato da verify per chiarezza (read-only vs distruttivo)
- **D-07:** Senza flag → dry run: mostra quali righe verrebbero cancellate (valori fuori PLAUSIBLE_BOUNDS) senza toccare il DB
- **D-08:** Con `--confirm` → esegue DELETE delle righe out-of-bounds + log di quante righe rimosse per disciplina
- **D-09:** Usa gli stessi PLAUSIBLE_BOUNDS definiti in `fitness_test_processor.py` (non duplicarli — importarli o ridefinirli con lo stesso valore)

### Trigger processore su test già eseguiti (FITNESS-01 / VERIFY-02)

- **D-10:** Se `physiology_zones` risulta vuota o mancante per una disciplina, Phase 2 include il trigger manuale del processore con finestra temporale ampliata (non solo 6h — abbracciare tutto giugno 2026)
- **D-11:** Comando: `python -m coach.coaching.fitness_test_processor --check-recent` con la `cutoff` modificata per coprire i test di giugno 2026; oppure script ad-hoc che chiama `FitnessTestProcessor.process_fitness_test()` direttamente sulle activity rows trovate
- **D-12:** La verifica finale è bounds-check su ciò che finisce in DB — Nicolò non ricorda i valori esatti, quindi il confronto è plausibilità, non valore atteso specifico

### Migrazione E4 (decisione di scope)

- **D-13:** [informational] La migrazione `physiology_zones UNIQUE(discipline, valid_from, method)` rimane in **Phase 3** insieme a tutte le altre migrazioni pending
- **D-14:** [informational] Phase 2 NON esegue la migrazione. Conseguenza accettata: se Nicolò runnasse il processore con il constraint mancante e il primo test avesse già una riga in DB, l'upsert fallirebbe. Da tener presente ma rischio basso con tabella vuota/pulita

### Test fitness (decisioni contestuali)

- **D-15:** [informational] I test FTP bici, soglia corsa, CSS nuoto sono **già stati eseguiti** su Garmin a giugno 2026 (confermato dall'atleta)
- **D-16:** Lo stato del DB (`physiology_zones` vuota o popolata) è ignoto — il primo task di Phase 2 è runnare `verify_physiology.py`
- **D-17:** Se il processore non ha elaborato i test, Phase 2 include il trigger manuale (D-10/D-11)
- **D-18:** [informational] Nessun LTHR test in scope per Phase 2 — solo FTP bici, soglia corsa, CSS nuoto

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisiti Phase 2
- `.planning/REQUIREMENTS.md` §FITNESS, §VERIFY — requisiti FITNESS-01/02/03 e VERIFY-02 con acceptance criteria
- `.planning/ROADMAP.md` §Phase 2 — goal, success criteria (4 items), requirements mappati

### Audit di resilienza (fonte dei bug da correggere)
- `docs/audit_resilience_2026-06-01.md` — tabella bug E, in particolare:
  - §E1: FTP fallback su `averageSpeed` (m/s) come watt → FTP corrotto
  - §E2: threshold fallback su `averagePace` (unità diversa da s/km) → zone nonsense
  - §E3: CSS senza guard `t400 > t200 > 0` → CSS negativo/assurdo
  - §E4: upsert senza unique constraint → sovrascrittura colonne sibling; migrazione in Phase 3
  - §E5: nessun try/except per-attività in `check_recent`

### Codice processore (già fixato — solo riferimento)
- `coach/coaching/fitness_test_processor.py` — extractors E1/E2/E3/E4/E5 già fixati con commenti `# Bug fix audit E`; PLAUSIBLE_BOUNDS definiti top-of-file; logica `check_recent()`
- `tests/test_fitness_test.py` — test E1/E2/E3/E5 esistenti che coprono i fix

### Schema e migrazione pending
- `sql/schema.sql` §physiology_zones — struttura tabella (manca UNIQUE constraint E4 — in migrations)
- `migrations/2026-06-01-resilience-audit.sql` §E4 — migrazione UNIQUE constraint, da eseguire in Phase 3

### Pattern script operativi (per verify_physiology.py e cleanup_physiology_zones.py)
- `scripts/verify_analytics.py` — pattern di riferimento per i nuovi script (logging, load_dotenv, main, output formattato)
- `coach/utils/supabase_client.py` — `get_supabase()` per connettersi al DB reale

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coach/coaching/fitness_test_processor.py` → `PLAUSIBLE_BOUNDS` dict: usare (o importare) per il cleanup script; non ridefinire valori diversi
- `FitnessTestProcessor.process_fitness_test()` + `check_recent()`: entry points per il trigger manuale se DB vuoto
- `coach/utils/supabase_client.get_supabase()`: connessione al DB reale (richiede `.env`)
- `scripts/verify_analytics.py`: pattern completo per il nuovo `verify_physiology.py` (struttura, output, logging)

### Established Patterns
- Script in `scripts/` seguono: `load_dotenv()`, `logging.getLogger(__name__)`, `if __name__ == "__main__": main()`
- `PYTHONPATH=.` richiesto per tutti i comandi Python
- Il processore usa `upsert on_conflict="discipline,valid_from,method"` — funzionerà solo dopo la migrazione E4 (Phase 3)
- La `cutoff` di `check_recent()` è hardcoded a 6h — per re-processare test vecchi bisogna o modificare la cutoff o chiamare `process_fitness_test()` direttamente

### Integration Points
- `physiology_zones` tabella: letta da `workers/mcp-server/src/index.ts` → tool `get_physiology_zones(discipline)` per Claude.ai
- Campi CLAUDE.md aggiornati da `fitness_test_processor._update_claude_md()`: `ftp_attuale_w`, `threshold_pace_per_km`, `css_attuale_per_100m`
- `activities` tabella: il processore cerca i test per sport + planned_date + session_type='fitness_test'; se la planned_session manca, usa keyword match sui notes

</code_context>

<specifics>
## Specific Ideas

- Output atteso di `verify_physiology.py`:
  ```
  === Physiology Zones ===

  BIKE:
    FTP: 240W  [OK — range 80-450W]  (metodo: 20min_test, data: 2026-06-03)
    CLAUDE.md ftp_attuale_w: 240W  ✓ match

  RUN:
    Threshold: 4:30/km (270 s/km)  [OK — range 150-360 s/km]  (metodo: 30min_test, data: 2026-06-05)
    CLAUDE.md threshold_pace_per_km: 4:30 ✓ match

  SWIM:
    CSS: 1:45/100m (105 s/100m)  [OK — range 70-150 s/100m]  (metodo: css_400_200, data: 2026-06-01)
    CLAUDE.md css_attuale_per_100m: 1:45 ✓ match
  ```
  (oppure se vuota o discrepante → messaggio esplicito)

- `cleanup_physiology_zones.py --confirm` deve loggare esattamente le righe cancellate (discipline, valid_from, method, valore fuori range) per audit

</specifics>

<deferred>
## Deferred Ideas

- Migrazione E4 (physiology_zones UNIQUE constraint) → Phase 3, coordinata con deploy bot e altre migrazioni
- Trigger LTHR test processing → non in scope Phase 2 (solo FTP/threshold/CSS)
- Bounds-check automatico con exit 1 (health check CI) per verify_physiology.py → potrebbe diventare un check in Phase 4 (live verification)
- Confronto con valore Garmin "ufficiale" (FTP stimato da Garmin) come sanity check → non in scope, Garmin FTP è stimato e non affidabile

</deferred>

---

*Phase: 2-Fitness Test Correctness*
*Context gathered: 2026-06-05*
