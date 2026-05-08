# Training Journal

> Diario delle decisioni di pianificazione e razionali. Aggiornato dall'agente
> dopo review settimanale e dopo cambi piano significativi.

## Convenzioni
- Una entry per data (YYYY-MM-DD) o per evento
- Tono: nota tecnica, non prosa lunga
- Cita sempre i numeri al momento della decisione

---

<!-- Le entry vengono appese qui sotto. La più recente in cima. -->

## 2026-05-06 — Weekly review + plan settimana 07-13/05

**Settimana analizzata:** 29/04 → 05/05.

**Numeri:**
- 5 sessioni / 4h38' / 12.7km corsa / 5.4km nuoto / 42.7km bici
- HRV trend: crash z=-3.56 il 25/04 → recupero progressivo → +2.16 oggi (supercompensazione)
- Resting HR 56 → 48 (-8 bpm in 14gg)
- Garmin acute/chronic 392/227 = ratio 1.73 (sopra Gabbett 1.5)
- Spalla/fascite: nessun dolore segnalato

**Diagnosi:**
1. Adattamento positivo (HRV ↑, rHR ↓), ma ACWR Garmin 1.73 = soglia rischio. Prossima settimana NON deve essere altro carico crescente.
2. Continuità infortuni ottima ma volumi corsa/nuoto ancora bassi. Vincolo fascite +10% → cap 14km settimana.
3. Sonno irregolare (5.2-8.6h, media 6.7h) = punto debole se carico cresce.

**Decisione settimana 07-13/05:**
- Volume target ~5h45-6h (+15-20% vs settimana scorsa, contenuto su bici per evitare impact su fascite)
- Distribuzione: 100% Z1-Z2, polarized di fatto (no Z3+ in fase ricostruzione T-17 da Lavarone)
- Schema: gio nuoto / ven corsa / sab lungo bici / dom off / lun corsa / mar nuoto / mer bici
- Corsa cumulato: 14km (entro vincolo +10%)
- Sessioni dom 10 → mer 13 lasciate con descrizione TBD, da raffinare a metà settimana

**Riferimenti applicati:** Seiler 2010 (polarized), Gabbett 2016 (ACWR ≤ 1.5), Cook & Purdam 2009 (gestione tendinopatia in fase reattiva), CLAUDE.md §3 (fase ricostruzione T-17), §5.2 (mappatura flag), §5.4 (commit con conferma).

**Caveat sistema:**
- TSS attività non popolato → CTL/ATL/TSB null su daily_metrics. Da risolvere a livello pipeline (zone fisiologiche su DB ancora vuote).
- Subjective log entries quasi tutti `free_note` non parsati → RPE/soreness/motivation rimangono vuoti. Parser debrief da rivedere.
- Mesocycles tabella vuota → planned sessions inserite senza FK mesocycle_id.

**Commit:** 7 righe in `planned_sessions` (07/05 → 13/05) via `scripts/commit_week_2026_05_07.py`.
