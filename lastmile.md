# Step 6 — Coach Reattivo Continuo con Budget Cap

## Contesto

Sto trasformando `triathlon-coach` da assistente reattivo a coach proattivo continuo. Step 5.0 (gcal export, force_garmin_sync, debrief parser fix) è chiuso. Step 5.1 (audit completezza dati Garmin + test E2E) sta per partire in altra sessione. Questo Step 6 lavora in parallelo a 5.1 ma su un altro asse: introdurre l'analisi AI proattiva delle sessioni e della modulazione del piano.

**Repo**: https://github.com/NicoRoger/triathlon-coach
**Branch**: main
**Stato**: 7 sessioni planned per settimana 7-13 maggio. MCP server con 7 tool (incluso force_garmin_sync). Brief mattutino narrative italiano. Connector triathlon-coach + Google Calendar funzionanti.

## Vincolo critico assoluto — Budget Cap €5/mese

L'utente impone un tetto MASSIMO di €5/mese sui costi Anthropic API. Questo è non negoziabile. Tutto il design deve garantire che questo limite NON venga superato MAI in nessuno scenario, incluso scenario "agente impazzisce e chiama API in loop".

Devi implementare 3 livelli di protezione:

### Livello 1 — Hard cap configurato Anthropic Console (lato utente)

L'utente configurerà su https://console.anthropic.com/settings/limits un monthly spend limit di $5.50 (margine del 10% per non hittarlo per errore). Documenta nel `docs/USER_GUIDE.md` come fare. Quando questo cap viene raggiunto, Anthropic blocca le richieste con HTTP 429 / 403.

### Livello 2 — Soft cap nel sistema con tracking persistente

Crea tabella nuova `api_usage` su Supabase:

```sql
CREATE TABLE api_usage (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    provider TEXT NOT NULL,           -- 'anthropic'
    model TEXT NOT NULL,              -- 'claude-sonnet-4-6', 'claude-haiku-4-5', etc
    purpose TEXT NOT NULL,            -- 'session_analysis', 'weekly_review', 'race_week', 'proactive_question', 'modulation_proposal', 'mental_coaching'
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd_estimated NUMERIC(8,4) NOT NULL,
    success BOOLEAN NOT NULL,
    metadata JSONB
);
CREATE INDEX idx_api_usage_timestamp ON api_usage(timestamp);
```

Migration: `migrations/2026-05-08-api-usage-table.sql`.

Crea modulo `coach/utils/budget.py` con queste funzioni:

- `get_month_spend_usd() -> float`: somma cost_usd_estimated del mese corrente
- `check_budget_or_raise(estimated_cost_usd: float, purpose: str)`: controlla se aggiungere costo supera soglie. Soglie:
  - <$3: ok, procedi
  - $3-$4: warning, manda Telegram "budget al 60%, ho fatto X chiamate", procedi
  - $4-$4.50: degraded mode, declassa modello da Sonnet a Haiku per analisi non critiche, manda Telegram alert
  - >$4.50: blocca chiamate non critiche, solo emergenze (race week, fatigue_critical), manda Telegram alert "budget al 90%, ho disabilitato analisi automatiche"
  - >$4.80: blocca tutto, solo emergenze, manda Telegram "budget exhausted"
- `log_api_call(model, purpose, input_tokens, output_tokens, success)`: scrive su api_usage. Calcola cost_usd_estimated da pricing table interna:
  - Sonnet 4.6: $3 input / $15 output per MTok
  - Haiku 4.5: $0.80 input / $4 output per MTok
  - Opus 4.7: $15 input / $75 output per MTok (NON usare per analisi automatiche, solo on-demand utente)

### Livello 3 — Model fallback intelligente

Crea wrapper `coach/utils/llm_client.py` con classe `LLMClient`:

```python
class LLMClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    
    def call(self, purpose: str, system: str, messages: list, prefer_model: str = 'sonnet') -> dict:
        """
        Chiama Anthropic con auto-fallback in base a budget.
        purpose: per logging e budget gating
        prefer_model: 'sonnet'/'haiku'/'opus' — viene downgradeato se budget basso
        """
        actual_model = self._select_model(prefer_model)
        budget.check_budget_or_raise(estimated_cost=0.05, purpose=purpose)  # stima conservativa pre-call
        # ... chiamata con retry
        # log_api_call dopo
```

Logica `_select_model`:
- Se `get_month_spend_usd() < $3.50`: rispetta prefer_model
- Se $3.50-$4.50: forza haiku per qualsiasi prefer_model tranne 'opus' (che diventa 'sonnet')
- Se >$4.50: solo haiku per qualsiasi cosa, blocca opus
- Se >$4.80: blocca tutte le chiamate non con purpose='emergency'

### Dashboard budget visibile

Aggiungi al `/status` del bot Telegram una sezione "Budget API" che mostra:
- Spesa attuale del mese
- % di €5 consumato
- N° chiamate effettuate
- Modello in uso (sonnet/haiku/blocked)
- Giorni rimanenti del mese
- Spesa media giornaliera

Crea anche script `scripts/budget_report.py` per report on-demand da CLI.

## Cosa fare — Le 6 feature di coaching

### Feature 1 — Analisi automatica post-sessione

Quando una nuova attività entra nel DB (post sync Garmin), analizza automaticamente. Implementazione:

1. Modifica `coach/ingest/garmin.py` per salvare lista activity_ids appena inseriti durante il sync
2. Crea `coach/coaching/post_session_analysis.py` con funzione `analyze_session(activity_id)`:
   - Recupera attività + payload completo
   - Recupera sessione pianificata corrispondente (match per data + sport)
   - Recupera sessioni storiche stesso tipo (ultime 4)
   - Recupera daily_metrics + readiness del giorno
   - Recupera ultimi 3 debrief soggettivi
   - Costruisce prompt strutturato per Sonnet 4.6 con:
     - System: skill `session_analysis.md` (da creare)
     - Context: dati sessione + pianificato + storico + soggettivo
     - Task: produrre analisi di 5-8 righe in italiano + 1-2 azioni concrete
   - Chiama `LLMClient.call(purpose='session_analysis', prefer_model='sonnet')`
   - Salva analisi su tabella nuova `session_analyses` (id, activity_id, analysis_text, suggested_actions JSONB, created_at)
   - Manda messaggio Telegram all'utente con l'analisi
3. Trigger: nuovo step nel workflow `ingest.yml`:
```yaml
   - name: Post-session analysis
     if: success()
     run: python -m coach.coaching.post_session_analysis --recent
```
4. Skill file `skills/session_analysis.md`: definisce il protocollo. Output strutturato:
   - 1 riga: stato sessione (ottima/buona/sotto le aspettative/problematica)
   - 2-3 righe: analisi di cosa hai osservato (drift HR, pace consistency, RPE coerente con dati, confronto storico)
   - 1-2 righe: pattern personale identificato se presente
   - 1-2 azioni concrete (es. "domani sostituisci recovery con off completo, HRV richiede")
5. Le azioni concrete restano "proposte". Per applicarle, l'agente nel prossimo Claude Code call può chiamare `commit_plan_change`. Vedi Feature 4.

### Feature 2 — Modulazione mid-week (Modello Medium)

Quando `analyze_session` rileva pattern critici (HRV crash, RPE >> previsto, dolore segnalato), genera proposta di modifica al piano dei prossimi 3 giorni. La proposta arriva via Telegram con bottoni inline:
🔍 Ho notato che dopo la sessione di oggi:

HRV crashata (-1.8σ)
RPE 9 vs previsto 6 sulla soglia
Hai segnalato fatica diffusa nel debrief

Propongo:

Domani 8/5: SCAMBIA soglia bici → Z2 60min recovery
9/5 (sabato): mantieni lungo come previsto, ma riduci a 90min
10/5 (domenica): off completo invece di Z2 corsa

[✅ Accetto] [❌ Rifiuto] [💬 Discuto]

Implementazione:
1. Bot Telegram (Worker TS) deve gestire callback_query con action types: `accept_modulation`, `reject_modulation`, `discuss_modulation`
2. Le proposte vivono in tabella nuova `plan_modulations`:
```sql
   CREATE TABLE plan_modulations (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       proposed_at TIMESTAMPTZ DEFAULT NOW(),
       trigger_event TEXT NOT NULL,
       trigger_data JSONB,
       proposed_changes JSONB NOT NULL,
       status TEXT DEFAULT 'proposed',  -- proposed/accepted/rejected/discussing
       resolved_at TIMESTAMPTZ,
       telegram_message_id BIGINT
   );
```
3. Su `accept`: Worker chiama `commit_plan_change` per ogni cambio + aggiorna gcal events
4. Su `reject`: solo update status
5. Su `discuss`: Worker manda messaggio "apri Claude Code per discutere"
6. Skill file `skills/modulation.md` definisce trigger e logiche

### Feature 3 — Domande proattive 2-3x/settimana

Workflow `.github/workflows/proactive_check_in.yml`:
- Cron 3 volte/settimana (martedì, giovedì, sabato alle 18:00 Europe/Rome)
- Sceglie domanda mirata sulla base del contesto attuale
- Manda via Telegram

Implementazione:
1. Skill file `skills/proactive_questions.md` con bank di ~30 domande categorizzate:
   - Spalla/infortunio (sempre attive finché flag injury)
   - Sonno/recovery
   - Motivazione/mental
   - Tecnica (dopo sessioni technique-focused)
   - Pre-gara (in race week)
   - Generale
2. Script `scripts/select_proactive_question.py` chiama Claude (Haiku) per scegliere LA domanda più rilevante in base a:
   - Stato corrente flag
   - Pattern recenti (es. soreness in calo da 3 giorni → domanda su qualità sonno)
   - Tempo dall'ultima domanda di quella categoria
   - Race week status
3. Le risposte tornano via Telegram, parser attuale in Worker le salva con `purpose='proactive_response'` in subjective_log
4. Vengono usate per arricchire il contesto della successiva analisi sessione e weekly review

### Feature 4 — Weekly review enhanced con AI

Modifica skill `weekly_review.md` per integrare Claude Sonnet/Opus quando l'utente la lancia:

1. Fase 0 esistente: sync forzato Garmin (già implementato)
2. Fase 1 (raccolta dati): identica
3. Fase 2 (analisi): l'agente Claude Code chiama Claude API con purpose='weekly_review' usando Sonnet 4.6 per generare analisi più profonda. Input: tutti i dati settimana + tutte le analisi sessione individuali della settimana + tutti i debrief + risposte proattive. Output: diagnosi narrativa lunga di 15-20 righe con pattern identificati
4. Fase 3 (proposta): identica al pattern attuale ma più informata
5. Fase 4 (lezione del giorno): genera con Claude la lezione settimanale (purpose='weekly_review_lesson', usa Haiku per economia)
6. Fase 5 (commit): identica
7. Fase 6 (gcal): identica

L'agente Claude Code esegue queste call API tramite il MCP server. Aggiungi nuovo tool MCP `call_claude_api` che il Worker proxy verso Anthropic con budget tracking.

### Feature 5 — Race week mental coaching

Quando T-7 ≤ giorni alla gara ≤ T-1, attiva un nuovo flow:

1. Una volta al giorno, brief mattutino è arricchito da una sezione "Mental check" generata da Claude con purpose='race_week_mental':
   - Domanda mirata su mood/ansia/eccitazione
   - Tecnica giornaliera di gestione (visualizzazione, respiration, ecc.)
2. T-2: skill `race_week_protocol.md` Fase T-2 invoca call con purpose='race_briefing' per generare briefing personalizzato sul percorso
3. T-1: messaggio sera con tecniche di gestione vigilia (calma, sonno, focus)
4. T-0 mattina: race day brief completo
5. T+1: debrief gara, analisi mentale oltre che fisica

Skill files dedicate:
- `skills/race_mental_coaching.md`
- `skills/race_briefing.md`

### Feature 6 — Memoria longitudinale automatica

L'agente deve mantenere `docs/coaching_observations.md` aggiornato automaticamente con pattern personali identificati.

1. Workflow settimanale (domenica notte 23:00 Europe/Rome): `pattern_extraction.yml`
2. Script `coach/coaching/pattern_extraction.py` chiama Claude (purpose='pattern_extraction', Sonnet) con:
   - Settimana appena passata
   - Storico ultime 4 settimane di analisi
   - Pattern già documentati
3. Output: pattern nuovi identificati o pattern esistenti aggiornati
4. Lo script committa direttamente su `docs/coaching_observations.md` via git
5. Quando l'agente Claude Code legge il `CLAUDE.md`, la sezione 11 ora referenzia anche questo file e l'agente lo consulta automaticamente

Esempi pattern da identificare:
- "Nicolò sottostima sempre RPE in salita di ~1-1.5 punti"
- "Ha pattern di sonno ridotto la sera di domenica (anticipo settimana lavorativa)"
- "Spalla peggiora nei primi 10 giorni dopo trasferta in Croazia, poi torna baseline"
- "Performance Z4 corsa migliore al mattino presto, peggiore dopo le 18"
- "Recupero post-soglia richiede 36-48h, non 24h come standard"

## Aggiornamenti CLAUDE.md richiesti

Aggiungi sezioni:

### §13 — Coaching proattivo
Descrive il flow analisi sessione automatica, modulazione, domande proattive. L'agente Claude Code deve sapere che queste cose esistono e che può consultare `session_analyses` e `plan_modulations` quando serve.

### §14 — Pattern personali (link a coaching_observations.md)
Riferimento a `docs/coaching_observations.md` come "memoria del coach" che cresce nel tempo.

### §2 estensione — Profilo mentale aggiornato
Sulla base intervista 6 maggio (memoria utente):
- Pattern emotivo pre-gara: ansia + eccitazione mista, da canalizzare come energia
- Trasferte Croazia: NON stressanti, opportunità recovery
- Tipologia atleta: endurance pura, prima cedimento muscolare non cardiovascolare
- Motivazione: combinazione di numeri/sensazione/riconoscimento/disciplina, alternare leve
- Sport psychology: assente nel passato, vorrebbe averla, il coach copre il fattibile

## Vincoli e preferenze

- **Budget €5/mese** assoluto: i 3 livelli di protezione devono essere SOLIDI. Test specifici sui limiti
- **Nessuna chiamata API quando l'utente non guadagna valore**: se il sistema può rispondere rule-based, non chiamare Claude. Esempio: il brief mattutino resta rule-based, NON va Claude API
- **Logging completo**: ogni chiamata Claude in api_usage con purpose esplicito, così l'utente può verificare
- **Nessun costo nascosto**: non aggiungere altri SaaS o servizi a pagamento. Solo Anthropic API per il coaching
- **Working style utente**: zip deliverables completi, root cause analysis, rimozione legacy, italiano "tu", asciutto

## Test obbligatori prima di considerare Step 6 chiuso

1. **Test budget cap simulato**: forza scenario `get_month_spend_usd() = $4.60`, lancia analisi sessione, verifica che declassa a Haiku
2. **Test budget exhausted**: forza scenario `$4.85`, verifica che blocca tutte chiamate non emergency
3. **Test failover Sonnet → Haiku → blocked**: verifica che il sistema scala graceful e notifica utente
4. **Test analisi sessione end-to-end**: forza ingest di una nuova attività, verifica che analyze_session triggeri, manda Telegram, salva su DB, costo loggato in api_usage
5. **Test modulation accept/reject**: simula proposta modulation, click su Telegram bottone accept, verifica commit_plan_change chiamato + gcal aggiornato
6. **Test pattern extraction**: lancia manualmente, verifica che committi su docs/coaching_observations.md
7. **Smoke test integrato**: aggiorna `scripts/smoke_test.py` per controllare anche budget, ANTHROPIC_API_KEY, api_usage table

## Output atteso

1. ✅ Tabelle `api_usage`, `session_analyses`, `plan_modulations` create con migrations
2. ✅ `coach/utils/budget.py` + `coach/utils/llm_client.py` implementati con test
3. ✅ Feature 1: post-session analysis automatica funzionante e integrata in ingest workflow
4. ✅ Feature 2: modulation con bottoni Telegram accept/reject/discuss
5. ✅ Feature 3: domande proattive 3x/settimana con scelta intelligente
6. ✅ Feature 4: weekly review arricchita con Claude API
7. ✅ Feature 5: race week mental coaching skills
8. ✅ Feature 6: pattern_extraction settimanale
9. ✅ CLAUDE.md aggiornato (§2 esteso profilo mentale, §13 coaching proattivo, §14 pattern personali)
10. ✅ Skill files nuove: session_analysis.md, modulation.md, proactive_questions.md, race_mental_coaching.md, race_briefing.md
11. ✅ docs/USER_GUIDE.md aggiornato con setup ANTHROPIC_API_KEY + console limit configuration
12. ✅ Smoke test esteso
13. ✅ docs/session_log_2026-05-08.md
14. ✅ Commit pushato su main

## Cosa fare se incontri ostacoli

- **Budget tracking calibrazione**: i prezzi delle Claude API potrebbero essere diversi da quelli che ho stimato. Verifica su https://docs.claude.com/en/docs/about-claude/pricing e adatta. Mantieni margine conservativo
- **MCP tool call_claude_api**: se la complessità è troppa (Worker fa proxy verso Anthropic con auth + budget check), implementa lato Python invece. L'agente Claude Code chiama uno script Python che fa la call.
- **Race week mental coaching**: se non riesci a coprire tutto T-7 → T-0, fai almeno T-3, T-1, T-0 e documenta gli altri come TODO
- **Pattern extraction**: se la qualità dei pattern estratti da Claude è bassa, lascia il sistema attivo ma con nota "in calibrazione, validare manualmente i pattern prima di farli leggere all'agente"

## Setup richiesto utente prima di poter usare il sistema

Documenta in `docs/USER_GUIDE.md` queste azioni:

1. Andare su https://console.anthropic.com → settings → billing
2. Caricare $10 di credito (per stare comodi)
3. Andare su https://console.anthropic.com/settings/limits
4. Impostare monthly spending limit a $5.50
5. Generare API key (https://console.anthropic.com/settings/keys)
6. Aggiungere come secret GitHub: `ANTHROPIC_API_KEY`
7. Aggiungere come secret Cloudflare Worker (entrambi i Workers): `ANTHROPIC_API_KEY`
8. Aggiungerla anche localmente in `.env`

## Roadmap futura (post Step 6)

Da NON implementare ora ma documentare in roadmap:
- TSS estimator + workout export Garmin (Step 7, post-test fitness giugno)
- Vision analysis di video tecnica nuoto/corsa (Step 8, opus 4.7 con vision)
- OAuth nel MCP Worker per accesso da claude.ai mobile (Step 9)

Riprendiamo dopo che hai completato. Quando torno in chat, mandami `docs/session_log_2026-05-08.md` e procediamo.