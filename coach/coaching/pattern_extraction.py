"""Feature 6 — Estrazione pattern longitudinali.

Script settimanale (domenica notte) che analizza le sessioni passate
per trovare pattern ricorrenti. Salva su docs/coaching_observations.md.

Step 8 (Blocco 3.1): aggiunta estrazione biometrica rule-based (zero LLM).
Pattern biometrici estratti deterministicamente, poi passati al LLM come
contesto aggiuntivo per l'estrazione qualitativa.

Uso: python -m coach.coaching.pattern_extraction
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from coach.utils.budget import BudgetExceededError
from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
OBSERVATIONS_FILE = DOCS_DIR / "coaching_observations.md"

MAX_OBSERVATIONS_CHARS = 6_000


def get_current_observations() -> str:
    if not OBSERVATIONS_FILE.exists():
        return "# Coaching Observations\n\nNessun pattern identificato ancora.\n"
    content = OBSERVATIONS_FILE.read_text(encoding="utf-8")
    if len(content) <= MAX_OBSERVATIONS_CHARS:
        return content
    tail = content[-MAX_OBSERVATIONS_CHARS:]
    cut = tail.find("\n")
    tail = tail[cut + 1:] if cut >= 0 else tail
    return f"[...osservazioni precedenti troncate ({len(content)} → {MAX_OBSERVATIONS_CHARS} chars)...]\n\n{tail}"


# ============================================================================
# Blocco 3.1 — Biometric pattern extraction (rule-based, zero LLM cost)
# ============================================================================

def extract_biometric_patterns(days: int = 28) -> dict:
    """Estrae pattern biometrici rule-based dagli ultimi N giorni.

    Returns dict con sezioni:
      - rpe_distribution: media RPE per sport, bias rilevati
      - recovery_patterns: tempo medio di recupero HRV post-intenso
      - sleep_performance_correlation: correlazione qualitativa sonno→performance
      - weekday_patterns: pattern giorno-della-settimana (HRV, RPE, compliance)
      - hr_zone_drift: stima drift zone HR da sessioni con intensità nota
    """
    sb = get_supabase()
    today = today_rome()
    since = (today - timedelta(days=days)).isoformat()

    activities = sb.table("activities").select(
        "started_at,sport,tss,duration_s,avg_hr,max_hr"
    ).gte("started_at", since).order("started_at").execute().data or []

    wellness = sb.table("daily_wellness").select(
        "date,hrv_rmssd,sleep_score,body_battery_max,resting_hr"
    ).gte("date", since).order("date").execute().data or []

    debrief = sb.table("subjective_log").select(
        "logged_at,rpe,kind,motivation,soreness"
    ).gte("logged_at", since).execute().data or []

    metrics = sb.table("daily_metrics").select(
        "date,ctl,atl,tsb,readiness_score,daily_tss"
    ).gte("date", since).order("date").execute().data or []

    patterns: dict = {}

    # --- RPE per sport ---
    rpe_by_sport: dict[str, list[int]] = defaultdict(list)
    for d in debrief:
        if d.get("rpe") is not None and d.get("kind") in ("post_session", "evening_debrief"):
            sport = _guess_sport_from_date(d.get("logged_at", "")[:10], activities)
            rpe_by_sport[sport].append(int(d["rpe"]))

    if rpe_by_sport:
        rpe_summary = {}
        for sport, rpes in rpe_by_sport.items():
            avg = statistics.fmean(rpes)
            rpe_summary[sport] = {"media": round(avg, 1), "n": len(rpes), "max": max(rpes)}
        patterns["rpe_per_sport"] = rpe_summary

    # --- Recovery: HRV il giorno dopo una sessione dura (TSS>60 o RPE>=7) ---
    hard_days = set()
    for a in activities:
        if (a.get("tss") or 0) >= 60:
            hard_days.add(a["started_at"][:10])
    for d in debrief:
        if (d.get("rpe") or 0) >= 7:
            hard_days.add(d["logged_at"][:10])

    wellness_by_date = {w["date"]: w for w in wellness}
    recovery_deltas = []
    for hd in hard_days:
        day_after = (date.fromisoformat(hd) + timedelta(days=1)).isoformat()
        day_before = (date.fromisoformat(hd) - timedelta(days=1)).isoformat()
        hrv_after = (wellness_by_date.get(day_after) or {}).get("hrv_rmssd")
        hrv_before = (wellness_by_date.get(day_before) or {}).get("hrv_rmssd")
        if hrv_after is not None and hrv_before is not None and hrv_before > 0:
            delta_pct = ((hrv_after - hrv_before) / hrv_before) * 100
            recovery_deltas.append(round(delta_pct, 1))

    if recovery_deltas:
        patterns["recovery_hrv_post_hard"] = {
            "media_delta_pct": round(statistics.fmean(recovery_deltas), 1),
            "n_sessioni": len(recovery_deltas),
            "nota": "negativo = HRV scende dopo duro, tipico" if statistics.fmean(recovery_deltas) < 0 else "positivo = buon recupero",
        }

    # --- Sleep → performance correlation ---
    sleep_perf_pairs = []
    for m in metrics:
        w = wellness_by_date.get(m["date"])
        if w and w.get("sleep_score") is not None and m.get("daily_tss") is not None and m["daily_tss"] > 0:
            sleep_perf_pairs.append((w["sleep_score"], m["daily_tss"]))

    if len(sleep_perf_pairs) >= 7:
        high_sleep = [tss for s, tss in sleep_perf_pairs if s >= 80]
        low_sleep = [tss for s, tss in sleep_perf_pairs if s < 65]
        if high_sleep and low_sleep:
            patterns["sleep_tss_correlation"] = {
                "tss_medio_sonno_alto": round(statistics.fmean(high_sleep), 1),
                "tss_medio_sonno_basso": round(statistics.fmean(low_sleep), 1),
                "n_giorni": len(sleep_perf_pairs),
            }

    # --- Weekday patterns ---
    weekday_names = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
    hrv_by_weekday: dict[int, list[float]] = defaultdict(list)
    for w in wellness:
        if w.get("hrv_rmssd") is not None:
            wd = date.fromisoformat(w["date"]).weekday()
            hrv_by_weekday[wd].append(w["hrv_rmssd"])

    if any(len(v) >= 3 for v in hrv_by_weekday.values()):
        wd_hrv = {}
        for wd, vals in hrv_by_weekday.items():
            if len(vals) >= 2:
                wd_hrv[weekday_names[wd]] = round(statistics.fmean(vals), 1)
        if wd_hrv:
            best_day = max(wd_hrv, key=wd_hrv.get)  # type: ignore[arg-type]
            worst_day = min(wd_hrv, key=wd_hrv.get)  # type: ignore[arg-type]
            patterns["weekday_hrv"] = {
                "medie": wd_hrv,
                "miglior_giorno": best_day,
                "peggior_giorno": worst_day,
            }

    # --- Motivation patterns ---
    mot_vals = [d["motivation"] for d in debrief if d.get("motivation") is not None]
    if len(mot_vals) >= 5:
        patterns["motivation"] = {
            "media": round(statistics.fmean(mot_vals), 1),
            "trend": "stabile" if max(mot_vals) - min(mot_vals) <= 3 else "variabile",
        }

    return patterns


def _guess_sport_from_date(day_iso: str, activities: list[dict]) -> str:
    """Heuristic: trova lo sport dell'attività più vicina a quel giorno."""
    for a in activities:
        if a.get("started_at", "")[:10] == day_iso:
            return a.get("sport", "unknown")
    return "unknown"


# ============================================================================
# LLM-based extraction (enhanced with biometric context)
# ============================================================================

def extract_patterns(days: int = 28) -> Optional[str]:
    """Analizza le ultime N settimane e aggiorna le observations."""
    sb = get_supabase()
    today = today_rome()
    since = (today - timedelta(days=days)).isoformat()

    analyses = sb.table("session_analyses").select("activity_id,analysis_text,created_at").gte("created_at", since).execute().data or []
    debrief = sb.table("subjective_log").select("kind,raw_text,logged_at").gte("logged_at", since).execute().data or []

    current_obs = get_current_observations()
    biometric = extract_biometric_patterns(days)

    context = json.dumps({
        "periodo_analizzato": f"{since} a {today.isoformat()}",
        "osservazioni_attuali": current_obs,
        "pattern_biometrici_rule_based": biometric,
        "analisi_recenti": [a.get("analysis_text") for a in analyses],
        "debrief_recenti": [d.get("raw_text") for d in debrief if d.get("raw_text")],
    }, indent=2, ensure_ascii=False)

    system = (
        "Sei un coach di triathlon d'elite. Analizza i log e le sessioni dell'ultimo mese per "
        "identificare pattern longitudinali (es. RPE sottostimato in bici, recupero lento dopo i lunghi, "
        "dolori ricorrenti il martedì). Hai anche dei pattern biometrici estratti automaticamente — "
        "integra quelli significativi nel documento. "
        "Produci un documento Markdown 'Coaching Observations' aggiornato "
        "che consolidi i pattern vecchi validi e aggiunga quelli nuovi. Organizza in sezioni:\n"
        "## Pattern di recupero\n## Pattern per sport\n## Pattern soggettivi\n"
        "## Pattern biometrici\n## Pattern settimanali\n## Fattori contestuali\n"
        "Sii molto conciso, bullet point."
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

        OBSERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        OBSERVATIONS_FILE.write_text(new_obs, encoding="utf-8")
        logger.info("Pattern extraction completed and saved")
        return new_obs

    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping LLM pattern extraction")
        # Fallback: salva almeno i pattern biometrici
        if biometric:
            _save_biometric_only(biometric, today)
        return None
    except Exception:
        logger.exception("Pattern extraction failed")
        if biometric:
            _save_biometric_only(biometric, today)
        return None


def _save_biometric_only(biometric: dict, today: date) -> None:
    """Fallback: salva pattern biometrici senza LLM se budget esaurito."""
    lines = [
        "# Coaching Observations",
        "",
        f"*Aggiornato automaticamente il {today.isoformat()} (solo biometrico, LLM non disponibile)*",
        "",
        "## Pattern biometrici (rule-based)",
        "",
    ]
    for key, val in biometric.items():
        lines.append(f"### {key.replace('_', ' ').title()}")
        if isinstance(val, dict):
            for k, v in val.items():
                lines.append(f"- **{k}**: {v}")
        lines.append("")

    OBSERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    OBSERVATIONS_FILE.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Biometric-only observations saved (LLM unavailable)")


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
