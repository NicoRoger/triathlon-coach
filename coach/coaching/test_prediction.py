"""Fase 2.6 — Pre-test prediction.

24h prima del test fitness pianificato, predice il valore atteso del nuovo
FTP/CSS/threshold con confidence interval, salva in `predictions` table.
Quando il test viene eseguito e detectato da fitness_test_processor.py,
outcome_verification.py calcola il delta automaticamente.

Predizione rule-based (no LLM):
- Baseline: ultimo valore noto da physiology_zones
- Correzione bias: usa prediction_accuracy view per il tipo di test
- Aggiustamento per training applicato (delta CTL ultimo intervallo)
- Confidence interval ±5% se prima predizione, restringe con più dati

Output:
- prediction inserita in DB (predictions table)
- notifica Telegram opzionale: "Domani test FTP. Predizione: 215W ±5W"
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from coach.coaching.outcome_verification import record_prediction
from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# Test type -> prediction_type + column physiology_zones
TEST_TYPE_MAPPING = {
    "bike": ("ftp", "ftp_w"),
    "run": ("threshold_pace", "threshold_pace_s_per_km"),
    "swim": ("css", "css_pace_s_per_100m"),
}


# ============================================================================
# Loaders
# ============================================================================

def _get_upcoming_tests(sb, today: date, days_ahead: int = 2) -> list[dict]:
    """Test pianificati nei prossimi N giorni (default 2 → predice 24-48h prima)."""
    until = today + timedelta(days=days_ahead)
    res = (
        sb.table("planned_sessions")
        .select("id,planned_date,sport,session_type,description")
        .eq("session_type", "fitness_test")
        .gte("planned_date", today.isoformat())
        .lte("planned_date", until.isoformat())
        .execute()
    )
    return res.data or []


def _get_last_zone(sb, discipline: str, column: str) -> Optional[float]:
    """Ultimo valore noto della disciplina (chiuso o aperto)."""
    res = (
        sb.table("physiology_zones")
        .select(f"{column},valid_from")
        .eq("discipline", discipline)
        .not_.is_(column, "null")
        .order("valid_from", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data or res.data[0].get(column) is None:
        return None
    return float(res.data[0][column])


def _get_ctl_change(sb, since_days: int = 42) -> Optional[float]:
    """Variazione CTL dal periodo del precedente test.

    Più CTL accumulato → predizione FTP più alta.
    """
    today = today_rome()
    since = (today - timedelta(days=since_days)).isoformat()
    res = (
        sb.table("daily_metrics")
        .select("date,ctl")
        .gte("date", since)
        .order("date", desc=False)
        .execute()
    )
    if not res.data or len(res.data) < 2:
        return None
    first_ctl = next((r.get("ctl") for r in res.data if r.get("ctl") is not None), None)
    last_ctl = next((r.get("ctl") for r in reversed(res.data) if r.get("ctl") is not None), None)
    if first_ctl is None or last_ctl is None:
        return None
    return last_ctl - first_ctl


def _get_bias_correction(sb, prediction_type: str) -> Optional[float]:
    """Bias medio storico per quel tipo di prediction.

    Se historical mean delta_pct = -3% → il sistema sottostima del 3%, quindi
    moltiplica le predizioni future per 1.03.
    """
    try:
        res = sb.table("prediction_accuracy").select("*").eq(
            "prediction_type", prediction_type
        ).limit(1).execute()
        if res.data and res.data[0].get("n", 0) >= 4:
            mean_pct = res.data[0].get("mean_delta_pct")
            if mean_pct is not None:
                return -float(mean_pct) / 100  # se actual è sopra predicted, futura predizione *(1 + bias/100)
    except Exception:
        pass
    return None


# ============================================================================
# Prediction engines
# ============================================================================

def _predict_ftp(baseline: float, ctl_delta: Optional[float], bias_corr: Optional[float]) -> tuple[float, float, float, float, str]:
    """Predici nuovo FTP (Watt).

    Heuristic: +0.5% FTP per ogni +1 CTL accumulato (saturazione 15%).
    """
    pred = baseline
    rationale_parts = [f"baseline FTP = {baseline:.0f}W"]
    if ctl_delta is not None:
        gain_pct = max(min(ctl_delta * 0.005, 0.15), -0.10)
        pred = baseline * (1 + gain_pct)
        rationale_parts.append(f"delta CTL {ctl_delta:+.1f} → {gain_pct*100:+.1f}%")
    if bias_corr is not None:
        pred *= (1 + bias_corr)
        rationale_parts.append(f"bias correction {bias_corr*100:+.1f}%")
    confidence = 0.6 if bias_corr is not None else 0.5
    band = pred * 0.05  # ±5W per 100W
    return round(pred), round(pred - band), round(pred + band), confidence, "; ".join(rationale_parts)


def _predict_threshold_pace(baseline: float, ctl_delta: Optional[float], bias_corr: Optional[float]) -> tuple[float, float, float, float, str]:
    """Predici nuovo threshold pace (s/km). Più basso = più veloce.

    +1 CTL → -0.5 s/km (saturazione -15 s/km).
    """
    pred = baseline
    rationale_parts = [f"baseline pace = {baseline:.0f}s/km"]
    if ctl_delta is not None:
        improvement = max(min(ctl_delta * 0.5, 15), -10)
        pred = baseline - improvement
        rationale_parts.append(f"delta CTL {ctl_delta:+.1f} → {-improvement:+.1f}s/km")
    if bias_corr is not None:
        pred *= (1 + bias_corr)
        rationale_parts.append(f"bias correction {bias_corr*100:+.1f}%")
    confidence = 0.6 if bias_corr is not None else 0.5
    band = pred * 0.03  # ±3% pace
    return round(pred), round(pred - band), round(pred + band), confidence, "; ".join(rationale_parts)


def _predict_css(baseline: float, ctl_delta: Optional[float], bias_corr: Optional[float]) -> tuple[float, float, float, float, str]:
    """Predici nuovo CSS (s/100m). Più basso = più veloce.

    +1 CTL swim → -0.2 s/100m (saturazione -5 s/100m).
    """
    pred = baseline
    rationale_parts = [f"baseline CSS = {baseline:.0f}s/100m"]
    if ctl_delta is not None:
        improvement = max(min(ctl_delta * 0.2, 5), -3)
        pred = baseline - improvement
        rationale_parts.append(f"delta CTL {ctl_delta:+.1f} → {-improvement:+.1f}s/100m")
    if bias_corr is not None:
        pred *= (1 + bias_corr)
        rationale_parts.append(f"bias correction {bias_corr*100:+.1f}%")
    confidence = 0.55 if bias_corr is not None else 0.45
    band = pred * 0.04
    return round(pred), round(pred - band), round(pred + band), confidence, "; ".join(rationale_parts)


PREDICTORS = {
    "ftp":            _predict_ftp,
    "threshold_pace": _predict_threshold_pace,
    "css":            _predict_css,
}


# ============================================================================
# Main entry
# ============================================================================

def generate_pre_test_predictions(today: Optional[date] = None,
                                  notify: bool = True) -> list[dict]:
    """Per ogni test pianificato 24-48h ahead, registra una prediction.

    Returns:
        Lista dei test predetti con valori.
    """
    sb = get_supabase()
    today = today or today_rome()
    upcoming = _get_upcoming_tests(sb, today, days_ahead=2)
    predictions: list[dict] = []

    for test in upcoming:
        sport = test["sport"]
        if sport not in TEST_TYPE_MAPPING:
            continue
        pred_type, col = TEST_TYPE_MAPPING[sport]

        baseline = _get_last_zone(sb, sport, col)
        if baseline is None:
            logger.info("[%s] no baseline → skip prediction", sport)
            continue

        # Verifica che non sia già stata fatta una prediction per questa data
        existing = (
            sb.table("predictions")
            .select("id")
            .eq("prediction_type", pred_type)
            .eq("target_date", test["planned_date"])
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.info("[%s] prediction already exists for %s → skip", pred_type, test["planned_date"])
            continue

        ctl_delta = _get_ctl_change(sb, since_days=42)
        bias_corr = _get_bias_correction(sb, pred_type)
        predictor = PREDICTORS[pred_type]
        pred_v, range_low, range_high, conf, rationale = predictor(baseline, ctl_delta, bias_corr)

        pid = record_prediction(
            prediction_type=pred_type,
            target_date=test["planned_date"],
            predicted_value=pred_v,
            predicted_range_low=range_low,
            predicted_range_high=range_high,
            confidence=conf,
            model_version="test_pred_v1",
            reasoning_summary=rationale,
            source="test_scheduler",
            related_entity_id=test["id"],
            related_entity_type="planned_session",
            metadata={"sport": sport, "baseline": baseline, "ctl_delta": ctl_delta},
        )
        predictions.append({
            "prediction_id": pid,
            "sport": sport,
            "prediction_type": pred_type,
            "predicted": pred_v,
            "range": [range_low, range_high],
            "confidence": conf,
            "test_date": test["planned_date"],
        })

        if notify:
            _notify_test_prediction(sport, pred_type, pred_v, range_low, range_high, conf, test["planned_date"])

    return predictions


def _notify_test_prediction(sport: str, pred_type: str, value: float,
                            low: float, high: float, conf: float, test_date: str) -> None:
    """Manda notifica Telegram opzionale con la prediction (Gemini-free, rule-based)."""
    unit = {"ftp": "W", "threshold_pace": "s/km", "css": "s/100m"}.get(pred_type, "")
    icon = {"bike": "🚴", "run": "🏃", "swim": "🏊"}.get(sport, "🧪")
    msg = (
        f"{icon} <b>Pre-test prediction</b>\n\n"
        f"Test {pred_type.upper()} ({sport}) il {test_date}.\n"
        f"Predizione: <b>{int(value)}{unit}</b> (range {int(low)}-{int(high)}, confidence {int(conf*100)}%)\n\n"
        f"<i>Il sistema calibrerà il modello quando il test sarà completato.</i>"
    )
    try:
        from coach.utils.telegram_logger import send_and_log_message
        send_and_log_message(msg, purpose="test_prediction",
                             context_data={"sport": sport, "pred_type": pred_type})
    except Exception:
        logger.warning("Failed to send test prediction notification", exc_info=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    preds = generate_pre_test_predictions()
    if not preds:
        logger.info("No tests in 48h → no predictions generated")
    for p in preds:
        logger.info("Predicted: %s = %s (range %s, conf %.2f)",
                    p["prediction_type"], p["predicted"], p["range"], p["confidence"])


if __name__ == "__main__":
    main()
