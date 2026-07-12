"""Feature 1 — Analisi automatica post-sessione.

Quando una nuova attività entra nel DB (post sync Garmin), analizza
automaticamente con Claude. Salva in session_analyses, manda Telegram.

Uso:
    python -m coach.coaching.post_session_analysis --recent
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

from coach.utils.budget import BudgetExceededError
from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SKILL_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "session_analysis.md"


def _load_skill() -> str:
    """Carica il system prompt dalla skill file."""
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return "Sei un coach di triathlon esperto. Analizza la sessione di allenamento."


def _get_planned_session(sb, activity_date: str, sport: str) -> Optional[dict]:
    """Trova sessione pianificata per data e sport."""
    res = sb.table("planned_sessions").select("*").eq(
        "planned_date", activity_date
    ).eq("sport", sport).limit(1).execute()
    return res.data[0] if res.data else None


def _get_historical(sb, sport: str, current_id: str, limit: int = 4) -> list[dict]:
    """Ultime N attività dello stesso sport, esclusa quella corrente."""
    res = sb.table("activities").select(
        "started_at,duration_s,distance_m,avg_hr,max_hr,avg_pace_s_per_km,avg_power_w,tss,splits"
    ).eq("sport", sport).neq("external_id", current_id).order(
        "started_at", desc=True
    ).limit(limit).execute()
    return res.data or []


def _get_recent_debrief(sb, days: int = 3) -> list[dict]:
    """Ultimi debrief soggettivi."""
    since = (today_rome() - timedelta(days=days)).isoformat()
    res = sb.table("subjective_log").select("*").gte(
        "logged_at", since
    ).order("logged_at", desc=True).limit(5).execute()
    return res.data or []


def _get_daily_metrics(sb, day: str) -> Optional[dict]:
    """Daily metrics per il giorno."""
    res = sb.table("daily_metrics").select("*").eq("date", day).limit(1).execute()
    return res.data[0] if res.data else None


def _get_upcoming_sessions(sb, from_date: str, days: int = 3) -> list[dict]:
    """Prossime sessioni pianificate (per proposta modulazione)."""
    from datetime import date, timedelta
    until = (date.fromisoformat(from_date) + timedelta(days=days)).isoformat()
    res = sb.table("planned_sessions").select(
        "planned_date,sport,session_type,duration_s,description"
    ).gt("planned_date", from_date).lte("planned_date", until).order(
        "planned_date"
    ).execute()
    return res.data or []


def _get_physiology_zones(sb, discipline: str) -> Optional[dict]:
    """Recupera le zone fisiologiche attive per la disciplina."""
    today = today_rome().isoformat()
    res = sb.table("physiology_zones").select("*").or_(
        f"valid_to.is.null,valid_to.gte.{today}"
    ).lte("valid_from", today).eq("discipline", discipline).order(
        "valid_from", desc=True
    ).limit(1).execute()
    return res.data[0] if res.data else None


# Zona attesa per tipo di sessione pianificata (#4): l'analisi confronta col
# session_type, non con un recovery generico.
SESSION_TYPE_ZONE = {
    "recovery": "Z1", "recupero": "Z1", "technique": "Z1", "tecnica": "Z1",
    "easy": "Z2", "endurance": "Z2", "long": "Z2", "lungo": "Z2", "lsd": "Z2", "fondo": "Z2",
    "brick": "Z2",
    "tempo": "Z3", "race_pace": "Z3",
    "threshold": "Z4", "soglia": "Z4",
    "intervals": "Z5", "vo2max": "Z5", "vo2": "Z5", "ripetute": "Z5",
}


def _weather_temp_c(weather: Optional[dict]) -> Optional[float]:
    """Estrae la temperatura in °C dal payload raw di get_activity_weather.

    Garmin restituisce 'temp' come intero; l'unità (F o C) non è documentata
    e può variare per zona/versione API. Euristica robusta a entrambi i casi:
    per un allenamento outdoor un valore >=50 non può essere Celsius, quindi
    è Fahrenheit e va convertito.
    """
    if not weather or not isinstance(weather, dict):
        return None
    raw = weather.get("temp")
    if raw is None:
        return None
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    return round((raw - 32) * 5 / 9, 1) if raw >= 50 else raw


def _our_hr_zone(avg_hr: float, lthr: float) -> str:
    """Classifica una HR media nella NOSTRA zona (LTHR 5-zone, confini contigui)."""
    r = avg_hr / lthr
    if r < 0.81:
        return "Z1"
    if r < 0.89:
        return "Z2"
    if r < 0.95:
        return "Z3"
    if r < 1.0:
        return "Z4"
    return "Z5"


def _compute_zone_compliance(planned: dict, activity: dict) -> Optional[dict]:
    """Confronta target_zones del piano con hr_zones_s effettivi.

    target_zones: {"z2": 0.8, "z4": 0.2}  — proporzioni (somma <= 1)
    hr_zones_s:   {"z1": 300, "z2": 3600, "z4": 120}  — secondi per zona

    Per il nuoto la compliance HR è sempre inaffidabile (senza fascia toracica).
    Per run/bike/brick, hr_zones_s sono i bucket del DEVICE Garmin — soglie
    diverse dalla nostra classificazione LTHR (#4) — quindi lo score qui
    contraddirebbe intensity_context, che confronta invece sulla NOSTRA zona.
    Restituisce sempre None; il chiamante usa swim_pace_context/intensity_context.
    """
    sport = activity.get("sport", "")
    if sport in ("swim", "run", "bike", "brick"):
        return None

    target = planned.get("target_zones")
    actual_raw = activity.get("hr_zones_s")
    if not target or not actual_raw:
        return None

    total_s = sum(actual_raw.values())
    if total_s == 0:
        return None

    actual = {z: round(s / total_s, 3) for z, s in actual_raw.items()}

    deviations = {}
    for zone, tgt in target.items():
        act = actual.get(zone, 0.0)
        deviations[zone] = round(act - tgt, 3)

    # Compliance score: fraction of prescribed intensity actually hit
    overlap = sum(min(actual.get(z, 0), tgt) for z, tgt in target.items())
    target_sum = sum(target.values())
    score = round(overlap / target_sum * 100) if target_sum > 0 else None

    return {
        "score": score,
        "target": target,
        "actual": actual,
        "deviations": deviations,
        "total_duration_s": total_s,
    }


def analyze_session(activity_id: str) -> Optional[dict]:
    """Analizza una singola attività con AI.

    Returns:
        dict con analysis_text e suggested_actions, o None se skippata.
    """
    sb = get_supabase()

    # Check se già analizzata
    existing = sb.table("session_analyses").select("id").eq(
        "activity_id", activity_id
    ).limit(1).execute()
    if existing.data:
        logger.info("Activity %s already analyzed, skipping", activity_id)
        return None

    # Recupera attività
    act_res = sb.table("activities").select("*").eq("external_id", activity_id).limit(1).execute()
    if not act_res.data:
        logger.warning("Activity %s not found", activity_id)
        return None

    activity = act_res.data[0]
    # Bug fix audit E8: data Rome (non slicing UTC) per il lookup di
    # planned_session/metriche del giorno corretto a cavallo di mezzanotte.
    from coach.utils.dt import to_rome_date
    _d = to_rome_date(activity.get("started_at"))
    activity_date = _d.isoformat() if _d else str(activity.get("started_at", ""))[:10]
    sport = activity.get("sport", "other")

    # Raccolta contesto
    planned = _get_planned_session(sb, activity_date, sport)
    historical = _get_historical(sb, sport, activity_id)
    debrief = _get_recent_debrief(sb)
    metrics = _get_daily_metrics(sb, activity_date)
    zone_compliance = _compute_zone_compliance(planned, activity) if planned else None

    # Nuoto: pace vs CSS invece di compliance HR (HR pool inaffidabile)
    swim_pace_context: Optional[str] = None
    if sport == "swim":
        zones_row = _get_physiology_zones(sb, "swim")
        css_s = (zones_row or {}).get("css_pace_s_per_100m")
        # avg_pace_s_per_km per nuoto = s/km; converti in s/100m dividendo per 10
        avg_pace_km = activity.get("avg_pace_s_per_km")
        avg_pace_100m = round(avg_pace_km / 10, 1) if avg_pace_km else None
        if css_s and avg_pace_100m:
            delta = round(avg_pace_100m - css_s, 1)
            interp = (
                "sotto CSS — sprint/Z4+" if delta < -5
                else "± CSS — soglia/Z4" if abs(delta) <= 5
                else f"+{abs(delta)}s/100m sopra CSS — aerobico Z2/Z3"
            )
            swim_pace_context = (
                f"CSS: {css_s}s/100m | Pace media: {avg_pace_100m}s/100m | "
                f"Delta: {delta:+.1f}s/100m ({interp})\n"
                f"NOTA: dati HR pool inaffidabili — valuta compliance solo su pace e RPE."
            )
        else:
            swim_pace_context = (
                "CSS non disponibile o pace non registrata. "
                "NOTA: dati HR pool inaffidabili — valuta su RPE e sensazione."
            )

    # ADAPT-01: classificazione deterministica cedimento (zero LLM)
    from coach.analytics.readiness import classify_fatigue_type
    splits = activity.get("splits") or None
    debrief_rpe = next((int(d["rpe"]) for d in debrief if d.get("rpe") is not None), None)
    fatigue_result = classify_fatigue_type(activity, splits, debrief_rpe)

    # Costruisci prompt. Nel nuoto l'HR della fascia non è indossata: rimuovi i
    # campi HR dall'attività così l'LLM NON giudica su Z3/Z4 fantasma (valuta su
    # pace vs CSS, fornito sotto in swim_pace_context).
    prompt_activity = _clean_for_prompt(activity)
    if sport == "swim":
        for hr_field in ("hr_zones_s", "avg_hr", "max_hr", "hr_drift"):
            prompt_activity.pop(hr_field, None)
    elif sport in ("run", "bike", "brick"):
        # hr_zones_s sono le zone del DEVICE Garmin, non le nostre → fuorvianti
        # (una corsa Z2 a 143bpm cadeva in "Garmin Z3"). Le togliamo e diamo
        # sotto il confronto sulla NOSTRA zona vs il session_type pianificato (#4).
        prompt_activity.pop("hr_zones_s", None)

    # #4: intensità reale (nostra zona) vs zona attesa dal session_type pianificato.
    intensity_context: Optional[str] = None
    if sport in ("run", "bike", "brick"):
        disc = "run" if sport == "brick" else sport
        try:
            zr = _get_physiology_zones(sb, disc) or {}
        except Exception:
            zr = {}
        lthr = zr.get("lthr")
        avg_hr = activity.get("avg_hr")
        st = ((planned or {}).get("session_type") or "").lower()
        exp = SESSION_TYPE_ZONE.get(st)
        if lthr and avg_hr:
            actz = _our_hr_zone(float(avg_hr), float(lthr))
            planned_line = f"Pianificato: {st or 'n/d'}"
            if exp:
                planned_line += f" → zona attesa {exp}"
            intensity_context = (
                f"{planned_line}\n"
                f"Eseguito: HR media {avg_hr} bpm = nostra {actz} (LTHR {int(lthr)}).\n"
                f"Giudica l'intensità su {actz} vs la zona attesa del tipo pianificato, "
                f"NON sui bucket Garmin (hr_zones_s, rimossi perché zone del device)."
            )

    # #4: correzione caldo — un HR alto con temperatura elevata è deriva
    # cardiaca termica, non calo di fitness. Euristica: ~1bpm ogni 2°C oltre
    # i 25°C a parità di sforzo (approssimata, non una soglia fisiologica
    # misurata — va usata come contesto, non come dato esatto).
    heat_note: Optional[str] = None
    if sport in ("run", "bike", "brick"):
        temp_c = _weather_temp_c(activity.get("weather"))
        if temp_c is not None and temp_c > 25:
            expected_bump = round((temp_c - 25) / 2)
            heat_note = (
                f"Temperatura registrata: {temp_c}°C. Con caldo, l'HR sale ~1bpm ogni 2°C oltre i 25° "
                f"a parità di sforzo (deriva cardiaca termica, qui ~+{expected_bump}bpm attesi). "
                f"Scala l'HR osservato di questa quota prima di giudicare zona o calo di fitness."
            )

    context_parts = [
        f"## Attività analizzata\n{json.dumps(prompt_activity, indent=2, default=str)}",
    ]
    if planned:
        context_parts.append(f"## Sessione pianificata\n{json.dumps(_clean_for_prompt(planned), indent=2, default=str)}")
    if zone_compliance:
        context_parts.append(
            f"## Compliance zone (confronto piano vs eseguito)\n"
            f"Score: {zone_compliance['score']}% — "
            f"target {zone_compliance['target']} / effettivo {zone_compliance['actual']}\n"
            f"Deviazioni per zona: {zone_compliance['deviations']}"
        )
    if intensity_context:
        context_parts.append(f"## Intensità: nostra zona vs piano\n{intensity_context}")
    if heat_note:
        context_parts.append(f"## Correzione caldo\n{heat_note}")
    if swim_pace_context:
        context_parts.append(f"## Nuoto: Pace vs CSS\n{swim_pace_context}")
    if historical:
        context_parts.append(f"## Storico ultime {len(historical)} sessioni {sport}\n{json.dumps([_clean_for_prompt(h) for h in historical], indent=2, default=str)}")
    if metrics:
        context_parts.append(f"## Metriche giornaliere\n{json.dumps(_clean_for_prompt(metrics), indent=2, default=str)}")
    if debrief:
        context_parts.append(f"## Debrief soggettivi recenti\n{json.dumps([_clean_for_prompt(d) for d in debrief], indent=2, default=str)}")

    user_message = "\n\n".join(context_parts)

    # Chiamata AI — routing automatico via PURPOSE_ROUTING (session_analysis → Gemini free)
    try:
        from coach.utils.llm_client import get_client_for_purpose
        client = get_client_for_purpose("session_analysis")
        result = client.call(
            purpose="session_analysis",
            system=_load_skill(),
            messages=[{"role": "user", "content": user_message}],
            max_tokens=800,
            temperature=0.3,
        )
    except BudgetExceededError:
        logger.warning("Budget exceeded, skipping session analysis for %s", activity_id)
        return None
    except Exception:
        logger.exception("LLM call failed for session analysis %s", activity_id)
        return None

    # Bug fix audit E7: non salvare/inviare un'analisi vuota (Gemini può
    # restituire "" su risposta troncata/safety). result può anche mancare campi.
    if not result or not (result.get("text") or "").strip():
        logger.warning("Analisi sessione vuota per %s, skip salvataggio", activity_id)
        return None

    analysis_text = result["text"]

    # Salva su DB
    actions = _extract_actions(analysis_text)
    if zone_compliance:
        actions.append({"zone_compliance": zone_compliance})
    record = {
        "activity_id": activity_id,
        "analysis_text": analysis_text,
        "fatigue_type": fatigue_result.failure_type or "insufficient_data",
        "fatigue_confidence": fatigue_result.confidence,
        "sport": sport,
        "suggested_actions": actions,
        "model_used": result.get("model"),
        "cost_usd": result.get("cost_usd"),
    }
    # M5: race rara tra job concorrenti (es. backfill manuale + ingest) sullo
    # stesso activity_id — il check "already existing" sopra non è atomico
    # col insert. Con lo UNIQUE su activity_id, il secondo insert fallisce
    # invece di duplicare l'analisi: lo trattiamo come skip, non errore.
    try:
        sb.table("session_analyses").insert(record).execute()
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            logger.info("Activity %s analizzata concorrentemente, skip", activity_id)
            return None
        raise

    # Manda Telegram
    _send_analysis_telegram(activity, analysis_text)

    # Valuta se serve modulazione mid-week
    try:
        from coach.coaching.modulation import (
            should_trigger_modulation,
            propose_modulation,
            generate_modulation_proposal,
        )
        if should_trigger_modulation(analysis_text, metrics):
            upcoming = _get_upcoming_sessions(sb, activity_date)
            changes = generate_modulation_proposal(analysis_text, metrics or {}, upcoming)
            if changes:
                flags = (metrics or {}).get("flags") or []
                propose_modulation(
                    trigger_event="post_session_critical",
                    trigger_data={
                        "analysis_excerpt": analysis_text[:300],
                        "flags": flags,
                        "hrv_z": (metrics or {}).get("hrv_z_score"),
                    },
                    proposed_changes=changes,
                )
    except Exception:
        logger.warning("Modulation check failed for %s", activity_id, exc_info=True)

    logger.info("Session analysis saved for %s (cost: $%.4f)", activity_id, result["cost_usd"])
    return record


def analyze_recent(days: int = 2) -> int:
    """Analizza attività recenti non ancora analizzate.

    Args:
        days: quanti giorni indietro guardare (default 2, usare >2 per backfill)

    Returns:
        Numero di attività analizzate.
    """
    sb = get_supabase()
    since = (today_rome() - timedelta(days=days)).isoformat()

    # Attività recenti
    activities = sb.table("activities").select("external_id").gte(
        "started_at", since
    ).execute()

    if not activities.data:
        logger.info("No recent activities to analyze")
        return 0

    count = 0
    for act in activities.data:
        ext_id = act.get("external_id")
        if not ext_id:
            continue
        try:
            result = analyze_session(ext_id)
        except Exception:
            # Un'attività malformata non deve abortire il batch: le restanti
            # vanno comunque analizzate (stesso pattern E5 usato altrove).
            logger.exception("analyze_session fallita per %s, continuo con le altre", ext_id)
            continue
        if result:
            count += 1

    return count


def _clean_for_prompt(d: dict) -> dict:
    """Rimuove campi pesanti dal dict per prompt (raw_payload, id, created_at)."""
    skip = {"raw_payload", "id", "created_at", "updated_at"}
    return {k: v for k, v in d.items() if k not in skip and v is not None}


def _extract_actions(text: str) -> list[dict]:
    """Estrae azioni suggerite dal testo (heuristic: righe con → o •)."""
    actions = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("→", "•", "- ")) and len(line) > 10:
            actions.append({"action": line.lstrip("→•- ").strip()})
    return actions


def _send_analysis_telegram(activity: dict, analysis: str) -> None:
    """Manda analisi sessione via Telegram."""
    sport_emoji = {"swim": "🏊", "bike": "🚴", "run": "🏃", "strength": "💪"}.get(
        activity.get("sport", ""), "🏋️"
    )
    duration_min = int(activity.get("duration_s") or 0) // 60

    msg = (
        f"{sport_emoji} <b>Analisi sessione</b> — {activity.get('sport', '?')} {duration_min}min\n\n"
        f"{analysis}"
    )
    try:
        from coach.utils.telegram_logger import send_and_log_message
        send_and_log_message(
            msg,
            purpose="session_analysis",
            context_data={"activity_id": activity.get("id"), "sport": activity.get("sport")},
        )
    except Exception:
        # Bug fix audit E9: exc_info=True per poter diagnosticare uno stop invii
        # (token mancante, messaggio troppo lungo, HTTP 400, ...).
        logger.warning("Failed to send session analysis to Telegram", exc_info=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--recent", action="store_true", help="Analizza attività recenti non analizzate")
    parser.add_argument("--days", type=int, default=2, help="Giorni indietro per --recent (default 2, usa 90+ per backfill)")
    parser.add_argument("--activity-id", type=str, help="Analizza una attività specifica")
    args = parser.parse_args()

    if args.activity_id:
        result = analyze_session(args.activity_id)
        if result:
            print(result["analysis_text"])
    elif args.recent:
        from coach.utils.health import record_health
        try:
            n = analyze_recent(days=args.days)
        except Exception as e:  # noqa: BLE001
            record_health("post_session_analysis", success=False, error=str(e))
            raise
        record_health("post_session_analysis", success=True, metadata={"analyzed": n})
        print(f"Analizzate {n} sessioni")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
