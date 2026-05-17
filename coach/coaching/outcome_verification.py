"""Fase 2.1 — Outcome verification engine.

Chiude il loop di apprendimento:
    prediction → outcome → error → calibration → belief update

Workflow:
- Cron settimanale (domenica notte) scansiona `predictions` con
  `resolved=FALSE AND target_date <= today`
- Per ogni prediction unresolved → cerca il valore effettivo (per type)
- Calcola delta, delta_pct, in_range
- Inserisce in `outcomes`, marca prediction.resolved=TRUE

Tipi supportati:
- ctl_weekly: CTL al target_date da daily_metrics
- race_time: tempo gara (input manuale via Telegram post-gara)
- ftp / threshold_pace / css: dal nuovo physiology_zones.valid_from = target_date
- readiness_score: da daily_metrics.readiness_score al target_date
- recovery_duration_h: ore tra activity con TSS>X e prossimo HRV z >= 0
- compliance_pct: % planned_sessions vs activities nella settimana
- weekly_volume_min: somma duration_s settimana / 60

Side effect: dopo aver verificato, chiama `update_athlete_beliefs()` per
aggiornare il file `docs/athlete_beliefs.md` con i bias longitudinali.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
BELIEFS_FILE = DOCS_DIR / "athlete_beliefs.md"


# ============================================================================
# Prediction recording — helpers usati da altri moduli
# ============================================================================

def record_prediction(
    prediction_type: str,
    target_date: date | str,
    predicted_value: float,
    confidence: Optional[float] = None,
    predicted_range_low: Optional[float] = None,
    predicted_range_high: Optional[float] = None,
    model_version: Optional[str] = None,
    reasoning_summary: Optional[str] = None,
    source: Optional[str] = None,
    related_entity_id: Optional[str] = None,
    related_entity_type: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Registra una prediction nel DB. Ritorna l'id."""
    sb = get_supabase()
    if isinstance(target_date, date):
        target_date = target_date.isoformat()
    row = {
        "prediction_type": prediction_type,
        "target_date": target_date,
        "predicted_value": predicted_value,
        "predicted_range_low": predicted_range_low,
        "predicted_range_high": predicted_range_high,
        "confidence": confidence,
        "model_version": model_version,
        "reasoning_summary": reasoning_summary,
        "source": source,
        "related_entity_id": related_entity_id,
        "related_entity_type": related_entity_type,
        "metadata": metadata,
    }
    row = {k: v for k, v in row.items() if v is not None}
    res = sb.table("predictions").insert(row).execute()
    pid = res.data[0]["id"]
    logger.info(
        "Prediction recorded: %s target=%s value=%s confidence=%s id=%s",
        prediction_type, target_date, predicted_value, confidence, pid,
    )
    return pid


# ============================================================================
# Actual value resolvers — uno per ogni prediction_type
# ============================================================================

def _resolve_ctl_weekly(sb, pred: dict) -> Optional[float]:
    """CTL al target_date da daily_metrics."""
    res = (
        sb.table("daily_metrics")
        .select("ctl")
        .eq("date", pred["target_date"])
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0].get("ctl") is None:
        return None
    return float(res.data[0]["ctl"])


def _resolve_readiness(sb, pred: dict) -> Optional[float]:
    res = (
        sb.table("daily_metrics")
        .select("readiness_score")
        .eq("date", pred["target_date"])
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0].get("readiness_score") is None:
        return None
    return float(res.data[0]["readiness_score"])


def _resolve_zone_value(sb, pred: dict, column: str, discipline: str) -> Optional[float]:
    """FTP / threshold_pace_s_per_km / css_pace_s_per_100m / lthr.

    Cerca physiology_zones con valid_from = target_date e disciplina coerente.
    """
    res = (
        sb.table("physiology_zones")
        .select(column)
        .eq("discipline", discipline)
        .eq("valid_from", pred["target_date"])
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0].get(column) is None:
        # Fallback: il valore valid_from più recente <= target_date+7gg
        target = date.fromisoformat(pred["target_date"])
        cutoff = (target + timedelta(days=7)).isoformat()
        fb = (
            sb.table("physiology_zones")
            .select(f"{column},valid_from")
            .eq("discipline", discipline)
            .gte("valid_from", pred["target_date"])
            .lte("valid_from", cutoff)
            .order("valid_from", desc=False)
            .limit(1)
            .execute()
        )
        if fb.data and fb.data[0].get(column) is not None:
            return float(fb.data[0][column])
        return None
    return float(res.data[0][column])


def _resolve_ftp(sb, pred: dict) -> Optional[float]:
    return _resolve_zone_value(sb, pred, "ftp_w", "bike")


def _resolve_threshold_pace(sb, pred: dict) -> Optional[float]:
    return _resolve_zone_value(sb, pred, "threshold_pace_s_per_km", "run")


def _resolve_css(sb, pred: dict) -> Optional[float]:
    return _resolve_zone_value(sb, pred, "css_pace_s_per_100m", "swim")


def _resolve_weekly_volume(sb, pred: dict) -> Optional[float]:
    """weekly_volume_min: somma duration_s/60 in [target_date - 6, target_date]."""
    target = date.fromisoformat(pred["target_date"])
    start = (target - timedelta(days=6)).isoformat()
    end = target.isoformat()
    res = (
        sb.table("activities")
        .select("duration_s")
        .gte("started_at", f"{start}T00:00:00Z")
        .lte("started_at", f"{end}T23:59:59Z")
        .execute()
    )
    total_s = sum((r.get("duration_s") or 0) for r in (res.data or []))
    if total_s == 0:
        return None
    return total_s / 60


def _resolve_compliance(sb, pred: dict) -> Optional[float]:
    """compliance_pct: (n_completed / n_planned) * 100 nella settimana del target."""
    target = date.fromisoformat(pred["target_date"])
    # Settimana lun-dom contenente target_date
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)
    planned = sb.table("planned_sessions").select("planned_date,status").gte(
        "planned_date", monday.isoformat()
    ).lte("planned_date", sunday.isoformat()).execute()
    if not planned.data:
        return None
    n_planned = len(planned.data)
    n_completed = sum(1 for s in planned.data if s.get("status") == "completed")
    return round(n_completed / n_planned * 100, 1)


# Race_time e recovery_duration_h sono input-manuale e non risolvibili automaticamente
def _resolve_race_time(sb, pred: dict) -> Optional[float]:
    """Cerca actual_time_s su races.id = related_entity_id."""
    if not pred.get("related_entity_id"):
        return None
    res = (
        sb.table("races")
        .select("actual_time_s")
        .eq("id", pred["related_entity_id"])
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0].get("actual_time_s") is None:
        return None
    return float(res.data[0]["actual_time_s"])


RESOLVERS = {
    "ctl_weekly":           _resolve_ctl_weekly,
    "readiness_score":      _resolve_readiness,
    "ftp":                  _resolve_ftp,
    "threshold_pace":       _resolve_threshold_pace,
    "css":                  _resolve_css,
    "weekly_volume_min":    _resolve_weekly_volume,
    "compliance_pct":       _resolve_compliance,
    "race_time":            _resolve_race_time,
}


# ============================================================================
# Outcome verification main loop
# ============================================================================

def verify_pending_predictions(today: Optional[date] = None) -> dict:
    """Scansiona predictions unresolved con target_date <= today, popola outcomes.

    Returns:
        dict con counts: {checked, resolved, unresolvable}
    """
    sb = get_supabase()
    if today is None:
        today = today_rome()

    res = (
        sb.table("predictions")
        .select("*")
        .eq("resolved", False)
        .lte("target_date", today.isoformat())
        .order("target_date", desc=False)
        .execute()
    )
    rows = res.data or []
    counts = {"checked": len(rows), "resolved": 0, "unresolvable": 0}

    for pred in rows:
        ptype = pred["prediction_type"]
        resolver = RESOLVERS.get(ptype)
        if resolver is None:
            logger.warning("No resolver for prediction_type=%s id=%s", ptype, pred["id"])
            counts["unresolvable"] += 1
            continue
        try:
            actual = resolver(sb, pred)
        except Exception:
            logger.exception("Resolver failed for prediction %s (type=%s)", pred["id"], ptype)
            counts["unresolvable"] += 1
            continue
        if actual is None:
            logger.info("Actual value still unavailable for prediction %s (type=%s)",
                        pred["id"], ptype)
            counts["unresolvable"] += 1
            continue
        predicted = float(pred["predicted_value"])
        delta = actual - predicted
        delta_pct = round(delta / predicted * 100, 3) if predicted else None
        in_range = None
        if pred.get("predicted_range_low") is not None and pred.get("predicted_range_high") is not None:
            in_range = (float(pred["predicted_range_low"]) <= actual <= float(pred["predicted_range_high"]))

        try:
            sb.table("outcomes").insert({
                "prediction_id": pred["id"],
                "actual_value": actual,
                "delta": delta,
                "delta_pct": delta_pct,
                "in_range": in_range,
                "resolution_source": "auto_cron",
            }).execute()
            sb.table("predictions").update({"resolved": True}).eq("id", pred["id"]).execute()
            counts["resolved"] += 1
            logger.info(
                "Outcome resolved: type=%s id=%s predicted=%s actual=%s delta_pct=%s in_range=%s",
                ptype, pred["id"], predicted, actual, delta_pct, in_range,
            )
        except Exception:
            logger.exception("Failed to insert outcome for prediction %s", pred["id"])
            counts["unresolvable"] += 1

    return counts


# ============================================================================
# Athlete beliefs update from prediction_accuracy view
# ============================================================================

BELIEFS_HEADER = """# Athlete Beliefs

> Aggiornato automaticamente da `outcome_verification.py` ogni domenica notte.
> Contiene ciò che il sistema ha **imparato** sull'atleta confrontando le
> proprie predizioni con i risultati effettivi.
>
> Status legend: hypothesis (n<4) · weak (n>=4, conf>0.55) ·
> validated (n>=8, conf>0.7) · strong (stable >6 mesi).
"""


def update_athlete_beliefs() -> None:
    """Aggiorna docs/athlete_beliefs.md leggendo prediction_accuracy view."""
    sb = get_supabase()
    try:
        res = sb.rpc("execute_sql", {"query": "SELECT * FROM prediction_accuracy"}).execute()
        accuracy_rows = res.data or []
    except Exception:
        # Fallback: usa direttamente le tabelle (Supabase PostgREST non espone view RPC sempre)
        try:
            res = sb.table("prediction_accuracy").select("*").execute()
            accuracy_rows = res.data or []
        except Exception:
            logger.warning("prediction_accuracy view not queryable; skipping beliefs update")
            return

    lines = [BELIEFS_HEADER, ""]
    lines.append(f"_Last update: {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")

    if not accuracy_rows:
        lines.append("## Calibrazione predizioni")
        lines.append("")
        lines.append("Nessun outcome ancora verificato. Il sistema impara dopo qualche settimana.")
    else:
        lines.append("## Calibrazione predizioni (bias longitudinali)")
        lines.append("")
        lines.append("| Tipologia | n | Bias medio % | StdDev % | In-range % | Status |")
        lines.append("|-----------|---|--------------|----------|------------|--------|")
        for r in accuracy_rows:
            n = int(r.get("n", 0))
            status = _belief_status(n, r.get("mean_abs_delta_pct"))
            lines.append(
                f"| `{r['prediction_type']}` | {n} | "
                f"{r.get('mean_delta_pct', '—')} | "
                f"{r.get('stddev_delta_pct', '—')} | "
                f"{_pct(r.get('in_range_rate'))} | "
                f"{status} |"
            )

    BELIEFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BELIEFS_FILE.write_text("\n".join(lines), encoding="utf-8")
    logger.info("athlete_beliefs.md updated (%d accuracy rows)", len(accuracy_rows))


def _belief_status(n: int, mean_abs_delta_pct: Optional[float]) -> str:
    """Belief lifecycle (semplificato; versione completa in Fase 4)."""
    if n < 4:
        return "hypothesis"
    if mean_abs_delta_pct is None:
        return "weak"
    if n >= 8 and mean_abs_delta_pct < 10:
        return "validated"
    if n >= 4 and mean_abs_delta_pct < 15:
        return "weak"
    return "exploratory"


def _pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{round(float(v) * 100, 1)}%"
    except Exception:
        return str(v)


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    counts = verify_pending_predictions()
    logger.info("Outcome verification: %s", counts)
    update_athlete_beliefs()
    logger.info("Athlete beliefs updated.")


if __name__ == "__main__":
    main()
