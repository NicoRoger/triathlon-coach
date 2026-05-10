# LLM Usage Policy

Questa policy riduce il consumo automatico di token mantenendo qualità sulle interazioni ad alto valore.

## Default: `COACH_LLM_MODE=quality`

Permette chiamate LLM solo per:

- `weekly_review`
- `weekly_interactive`
- `race_briefing`
- `race_week_critical`
- `emergency`
- `fatigue_critical`
- `pattern_extraction`

Disabilita di default:

- `session_analysis`
- `modulation_proposal`
- `weekly_review_lesson`

## Modalità disponibili

| Modalità | Uso |
| --- | --- |
| `quality` | Default. Mantiene review/race/pattern, taglia automazioni non essenziali. |
| `minimal` | Solo review/race/emergenze. |
| `full` | Riattiva anche analisi sessione, modulazione AI e lesson. |
| `off` | Nessuna chiamata LLM. |

## Override puntuali

```bash
COACH_LLM_ENABLED_PURPOSES=session_analysis
COACH_LLM_DISABLED_PURPOSES=pattern_extraction
```

Gli override sono comma-separated e prevalgono sulla modalità.

## Regola operativa

Le decisioni safety e le modifiche al piano restano rule-based. L'LLM serve per sintesi narrativa, diagnosi settimanale, pattern longitudinali e race briefing.
