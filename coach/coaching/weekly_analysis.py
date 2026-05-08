"""Feature 4 — Weekly review enhanced con AI analysis.

L'agente Claude Code chiama questo script per generare analisi AI più profonda.
Uso: python -m coach.coaching.weekly_analysis
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from coach.utils.budget import BudgetExceededError
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def generate_weekly_analysis(days: int = 7) -> str:
    sb = get_supabase()
    since = (date.today() - timedelta(days=days)).isoformat()

    metrics = sb.table("daily_metrics").select("*").gte("date", since).order("date").execute().data or []
    activities = sb.table("activities").select("started_at,sport,duration_s,distance_m,avg_hr,avg_power_w,tss,splits").gte("started_at", since).execute().data or []
    analyses = sb.table("session_analyses").select("analysis_text,created_at").gte("created_at", since).execute().data or []
    debrief = sb.table("subjective_log").select("kind,raw_text,rpe,soreness,motivation,logged_at").gte("logged_at", since).execute().data or []

    context = json.dumps({
        "periodo": f"{since} → {date.today().isoformat()}",
        "metriche_giornaliere": [{k: v for k, v in m.items() if v is not None and k not in ("id", "created_at", "updated_at")} for m in metrics],
        "attivita": [{k: v for k, v in a.items() if v is not None} for a in activities],
        "analisi_sessioni": [a.get("analysis_text", "") for a in analyses],
        "debrief_soggettivi": [{k: v for k, v in d.items() if v is not None} for d in debrief],
    }, indent=2, default=str, ensure_ascii=False)

    skill_path = Path(__file__).resolve().parent.parent.parent / "skills" / "weekly_review.md"
    system = skill_path.read_text(encoding="utf-8") if skill_path.exists() else "Sei un coach di triathlon. Analizza la settimana."

    try:
        from coach.utils.llm_client import get_client
        client = get_client()
        result = client.call(
            purpose="weekly_review",
            system=system + "\n\nGenera un'analisi narrativa di 15-20 righe in italiano della settimana appena trascorsa. Identifica pattern, trend, e punti di azione.",
            messages=[{"role": "user", "content": context}],
            prefer_model="sonnet",
            max_tokens=1200,
            temperature=0.4,
        )
        return result["text"]
    except BudgetExceededError:
        return "⚠️ Budget API raggiunto — analisi AI non disponibile. Procedi con la review rule-based."
    except Exception:
        logger.exception("Weekly analysis failed")
        return "⚠️ Analisi AI fallita. Procedi con la review manuale."


def generate_weekly_lesson() -> str:
    """Genera la 'lezione del giorno' settimanale con Haiku per economia."""
    try:
        from coach.utils.llm_client import get_client
        client = get_client()
        result = client.call(
            purpose="weekly_review_lesson",
            system="Sei un coach di triathlon esperto. Genera una breve lezione settimanale (5-8 righe) su un aspetto dell'allenamento triathlon. Scrivi in italiano, tono diretto e pratico.",
            messages=[{"role": "user", "content": f"Genera la lezione della settimana. Data: {date.today().isoformat()}. Argomento: scegli tra nutrizione gara, gestione fatica, periodizzazione, tecnica, recupero, mental training."}],
            prefer_model="haiku",
            max_tokens=400,
            temperature=0.7,
        )
        return result["text"]
    except (BudgetExceededError, Exception):
        return ""


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError: pass
    analysis = generate_weekly_analysis()
    print(analysis)


if __name__ == "__main__":
    main()
