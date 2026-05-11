# Skill: Analisi Video Tecnica

## Quando attivare
- L'atleta carica un video via Telegram e chiede "analizza video" o "feedback tecnico"
- L'atleta chiede di analizzare un video di tecnica nuoto/corsa/bici
- Durante una weekly review, se ci sono video recenti da analizzare

## Input necessario
1. Sport del video (nuoto, corsa, bici)
2. Contesto: è un drill? una serie? gara? open water?
3. Storico analisi precedenti per la disciplina: `query_subjective_log` con `kind=video_analysis`

## Protocollo di analisi per disciplina

### Nuoto (priorità massima — l'atleta ha debolezza tecnica post-pausa)
Analizza:
1. **Posizione del corpo**: allineamento, posizione della testa, rolling
2. **Bracciata**: entry angle, catch, pull-through, recovery
3. **Respirazione**: timing, rotazione testa, impatto sulla bracciata
4. **Gambata**: frequenza, ampiezza, effetto propulsivo vs resistenza
5. **Coordinazione**: timing bracciata-gambe-respirazione

⚠️ **VINCOLO SPALLA DX**: Non suggerire mai drill che stressano la spalla (no paddle, no elastic band pull). Solo drill tecnici leggeri.

### Corsa
Analizza:
1. **Cadenza e appoggio**: forefoot/midfoot/heel strike, tempo contatto suolo
2. **Postura**: inclinazione tronco, posizione braccia, oscillazione verticale
3. **Fluidità**: simmetria, tensione inutile
4. **Specifica cross**: adattamento terreno irregolare (se video trail/cross)

⚠️ **VINCOLO FASCITE**: Non suggerire drill ad alto impatto (no hill sprints, no plyometrics aggressivi). Solo drill tecnici e propriocettivi.

### Bici
Analizza:
1. **Posizione in sella**: angolo busto, altezza sella, posizione mani
2. **Pedalata**: rotondità, punto morto, efficienza
3. **Specifica MTB/cross**: posizione tecnica in discesa, gestione ostacoli

## Output format

```
📹 ANALISI TECNICA — {sport} ({data})

🔍 Osservazioni principali:
1. [PRIORITÀ 1 — cosa migliorare per primo]
2. [PRIORITÀ 2]
3. [PRIORITÀ 3]

✅ Punti di forza:
- [cosa funziona bene]

🎯 Piano correzione (3 sessioni):
- Sessione 1: [drill specifico, 10-15 min]
- Sessione 2: [progressione]
- Sessione 3: [integrazione in sessione completa]

📊 Confronto con analisi precedente:
- [miglioramento/peggioramento/stabile su punto X]
```

## Integrazione

- Salva l'analisi in `subjective_log` con `kind=video_analysis` e `parsed_data` contenente sport, punti chiave, drill suggeriti
- I pattern tecnici estratti vengono inclusi automaticamente da `pattern_extraction.py` nella sezione "Pattern per sport"
- Le analisi sono accessibili via MCP tool `query_subjective_log(kind='video_analysis')`

## Budget
- L'analisi video richiede Claude API con capacità vision
- Costo stimato: ~$0.05-0.15 per analisi (dipende da durata video)
- Rispetta il budget cap: non analizzare più di 2 video/settimana in automatico
- Se budget degraded: skip analisi automatica, manda solo conferma salvataggio
