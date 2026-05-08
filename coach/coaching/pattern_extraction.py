"""Feature 6 — Estrazione pattern longitudinali.

Script settimanale (domenica notte) che analizza le sessioni passate
per trovare pattern ricorrenti. Salva su docs/coaching_observations.md.

Uso: python -m coach.coaching.pattern_extraction
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from coach.utils.budget import BudgetExceededError
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
OBSERVATIONS_FILE = DOCS_DIR / "coaching_observations.md"


def get_current_observations() -> str:
    if OBSERVATIONS_FILE.exists():
        return OBSERVATIONS_FILE.read_text(encoding="utf-8")
    return "# Coaching Observations\n\nNessun pattern identificato ancora.\n"


def extract_patterns(days: int = 28) -> Optional[str]:
    """Analizza le ultime N settimane e aggiorna le observations."""
    sb = get_supabase()
    since = (date.today() - timedelta(days=days)).isoformat()

    # Raccogli dati
    analyses = sb.table("session_analyses").select("activity_id,analysis_text,created_at").gte("created_at", since).execute().data or []
    debrief = sb.table("subjective_log").select("kind,raw_text,logged_at").gte("logged_at", since).execute().data or []
    
    current_obs = get_current_observations()

    context = json.dumps({
        "periodo_analizzato": f"{since} a {date.today().isoformat()}",
        "osservazioni_attuali": current_obs,
        "analisi_recenti": [a.get("analysis_text") for a in analyses],
        "debrief_recenti": [d.get("raw_text") for d in debrief if d.get("raw_text")],
    }, indent=2, ensure_ascii=False)

    system = (
        "Sei un coach di triathlon d'elite. Analizza i log e le sessioni dell'ultimo mese per "
        "identificare pattern longitudinali (es. RPE sottostimato in bici, recupero lento dopo i lunghi, "
        "dolori ricorrenti il martedì). Produci un documento Markdown 'Coaching Observations' aggiornato "
        "che consolidi i pattern vecchi validi e aggiunga quelli nuovi. Sii molto conciso e organizzato "
        "per bullet point."
    )

    try:
        from coach.utils.llm_client import get_client
        client = get_client()
        result = client.call(
            purpose="pattern_extraction",
            system=system,
            messages=[{"role": "user", "content": context}],
            prefer_model="sonnet",
            max_tokens=1500,
            temperature=0.3,
        )
        new_obs = result["text"]
        
        # Salva su file
        OBSERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        OBSERVATIONS_FILE.write_text(new_obs, encoding="utf-8")
        logger.info("Pattern extraction completed and saved")
        return new_obs
        
    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping pattern extraction")
        return None
    except Exception:
        logger.exception("Pattern extraction failed")
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError: pass
    
    print("Avvio estrazione pattern...")
    res = extract_patterns()
    if res:
        print("\n=== Nuove Osservazioni ===\n")
        print(res)
    else:
        print("Estrazione non riuscita o saltata.")


if __name__ == "__main__":
    main()
