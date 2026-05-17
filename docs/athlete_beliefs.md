# Athlete Beliefs

> Aggiornato automaticamente da `outcome_verification.py` ogni domenica notte.
> Contiene ciò che il sistema ha **imparato** sull'atleta confrontando le
> proprie predizioni con i risultati effettivi.
>
> **Status legend**:
> - `hypothesis` (n<4) → solo esplorativo, mai applicato in proposte
> - `weak` (n≥4, conf>0.55) → citato con caveat
> - `validated` (n≥8, conf>0.7) → applicabile in proposte
> - `strong` (stabile >6 mesi) → applicato per default

---

## Calibrazione predizioni

_Verrà popolato dopo i primi outcome verificati. Servono ~3-4 settimane
di sistema in funzione perché ci siano abbastanza dati._

| Tipologia | n | Bias medio % | StdDev % | In-range % | Status |
|-----------|---|--------------|----------|------------|--------|
| ctl_weekly | 0 | — | — | — | nessun dato |
| ftp | 0 | — | — | — | nessun dato |
| threshold_pace | 0 | — | — | — | nessun dato |
| css | 0 | — | — | — | nessun dato |
| race_time | 0 | — | — | — | nessun dato |

---

## Beliefs strutturali (manuale)

_Spazio per beliefs note sull'atleta che NON vengono dai dati di calibrazione
ma da osservazioni longitudinali del coach + pattern extraction._

### Risposte fisiologiche

- _(da popolare con pattern_extraction)_

### Preferenze training

- _(da popolare con pattern_extraction)_

### Vincoli specifici

- Spalla destra (borsite): nuoto solo Z1-Z2 con focus tecnica, niente serie intense
- Fascite plantare sinistra: max +10% volume corsa/settimana
- Storia elite 2021-2022: vedi `docs/elite_training_reference.md` come target lungo termine
