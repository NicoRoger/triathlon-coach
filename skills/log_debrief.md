---
name: log_debrief
description: Parsa la risposta libera del debrief serale dell'atleta in struttura DB e in narrativa per il journal. Usa quando il messaggio Telegram della sera contiene RPE/sensazioni multiple.
---

# Log Debrief

## Quando usare
Trigger:
- Atleta risponde dopo `/debrief` o spontaneamente la sera con multiple info
- Messaggio Telegram contiene almeno 2 di: RPE, dolori, motivazione, sonno previsto

## Procedura
1. Estrai dal testo libero:
   - `rpe` (1-10) — cerca "RPE 7" o "7/10" o numerico contestuale
   - `motivation` (1-10) — cerca "motivazione X" o frasi tipo "carica", "stanco"
   - `sleep_quality` o `sleep_planned`
   - `soreness` (0-10) — cerca "indolenzito", "gambe pesanti"
   - `injury_flag` + location — keyword: ginocchio/caviglia/etc
   - `illness_flag` — keyword: malato/febbre/raffreddore/tosse
2. Insert in `subjective_log` con `kind='evening_debrief'`
3. Scrivi una riga di narrativa per `docs/training_journal.md`:
   - Formato: `### YYYY-MM-DD\n- {summary}\n`
4. Se emergono pattern (3+ giorni stessa lamentela), flag esplicito all'atleta

## Esempio parsing
Input: "RPE 7, gambe pesanti seconda metà, no dolori, energia bassa, dormo presto"

Output strutturato:
```json
{
  "kind": "evening_debrief",
  "rpe": 7,
  "soreness": 6,
  "motivation": 4,
  "raw_text": "...",
  "parsed_data": {
    "fatigue_pattern": "second_half_legs_heavy",
    "sleep_intent": "early"
  }
}
```

Journal append:
```
### 2025-04-29
- Sessione RPE 7. Gambe pesanti seconda metà (TSS settimanale +14% vs media: monitorare). Niente dolori. Energia bassa, sonno anticipato.
```

## Output verso atleta
Conferma breve:
> ✅ Salvato. Domani brief alle 06:30. Buon riposo.

Se emergono flag (es. soreness >7 da 3+ giorni o injury):
> ⚠️ Notato: gambe pesanti per il 4° giorno consecutivo. Domani ti propongo Z2 al posto del lungo. Va bene?

## Cosa NON fare
- Non chiedere chiarimenti se manca un campo non critico (motivation, sleep_quality)
- Non assumere RPE 5 se non specificato — lascia null
