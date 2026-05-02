---
name: query_metrics
description: Estrai e analizza metriche storiche dal DB Supabase. Usa quando l'atleta chiede "come sono messo", "trend ultimi X giorni", "confronta", o ogni volta che serve un dato oggettivo per supportare un'analisi.
---

# Query Metrics

## Quando usare
- Domanda diretta su numeri (CTL/TSB/HRV/etc.)
- Trend o confronto temporale
- Prima di proporre modifiche al piano (sempre cita dati)
- Dopo `propose_plan_change` per giustificare il razionale

## Dati disponibili
Tabelle Supabase accessibili via MCP `get_recent_metrics`, `get_activity_history`,
`query_subjective_log`:

- `daily_metrics`: ctl, atl, tsb, daily_tss, hrv_z_score, readiness_score, flags
- `activities`: tutte le sessioni completate
- `daily_wellness`: HRV grezzo, sonno, body battery
- `subjective_log`: RPE, malattie, infortuni, note

## Procedura
1. Identifica l'orizzonte temporale richiesto (default 14 giorni)
2. Chiama il tool MCP appropriato
3. **Non recitare numeri grezzi**: sintetizza in trend, confronti, anomalie
4. **Cita sempre la finestra**: "ultimi 14 giorni", "settimana scorsa"
5. Identifica pattern: incrementi/decrementi >10%, flag attivi, gap di dati

## Output atteso
Risposta breve (3-6 righe), poi opzionalmente dettaglio se richiesto.
Esempio:
> Negli ultimi 14 giorni CTL è salito da 62 a 71 (+15%), TSB attualmente -8 (zona allenante). HRV stabile vicino baseline (z-score medio +0.2). Una sessione bici con RPE 9 il 22 aprile vale la pena annotare. Vuoi che zoomi su una disciplina?

## Cosa NON fare
- Non proporre cambi al piano in questo task — solo lettura
- Non inventare interpretazioni se i dati sono incompleti (`gap di sync` esplicito)
