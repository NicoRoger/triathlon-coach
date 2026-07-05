"""Compute daily_metrics: PMC + readiness + flags. Esegue dopo ogni ingest.

Idempotente: ricalcola sempre dall'inizio della finestra rilevante.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from coach.analytics.pmc import (
    DailyTSS,
    aggregate_daily_tss,
    compute_pmc_for_today,
    compute_pmc_series,
)
from coach.analytics.readiness import (
    SubjectiveState,
    TrainingState,
    WellnessHistory,
    compute_readiness,
    hrv_z_score,
)
from coach.utils.dt import today_rome
from coach.utils.health import record_health
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _fetch_activities_window(sb, start: date) -> list[dict]:
    res = sb.table("activities").select(
        "id,started_at,sport,tss,duration_s,avg_hr"
    ).gte("started_at", start.isoformat()).execute()
    return res.data or []


def _fetch_wellness_window(sb, start: date, end: date) -> list[dict]:
    """Wellness in [start, end]. Upper bound necessario in backfill: senza,
    la baseline HRV 28d includerebbe dati FUTURI rispetto al giorno ricalcolato."""
    res = (
        sb.table("daily_wellness").select("*")
        .gte("date", start.isoformat())
        .lte("date", end.isoformat())
        .execute()
    )
    return sorted(res.data or [], key=lambda r: r["date"])


def _fetch_lthr_by_sport(sb) -> dict[str, int]:
    """LTHR attivo per disciplina da physiology_zones (valid_to IS NULL).

    Usato dal fallback hrTSS in aggregate_daily_tss al posto del default
    env/160. Le discipline (swim/bike/run) coincidono con activities.sport.
    """
    try:
        res = sb.table("physiology_zones").select(
            "discipline,lthr,valid_from,valid_to"
        ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("physiology_zones non leggibile, fallback LTHR env/default")
        return {}
    rows = [
        r for r in (res.data or [])
        if r.get("valid_to") is None and r.get("lthr") is not None
    ]
    # In caso di più righe attive per disciplina, vince la valid_from più recente
    rows.sort(key=lambda r: str(r.get("valid_from") or ""))
    out: dict[str, int] = {}
    for r in rows:
        out[r["discipline"]] = int(r["lthr"])
    return out


def _fetch_recent_subjective(sb, day: date) -> dict:
    """Ultime 24h di subjective log (bounded a `day`: in backfill non deve
    leggere righe future rispetto al giorno ricalcolato)."""
    since = (day - timedelta(days=1)).isoformat()
    until = (day + timedelta(days=1)).isoformat()
    res = (
        sb.table("subjective_log").select("*")
        .gte("logged_at", since)
        .lte("logged_at", until)
        .execute()
    )
    rows = res.data or []
    out = {
        "motivation": None,
        "soreness": None,
        "illness_flag": False,
        "injury_flag": False,
        "illness_recent_days": 0,
    }
    for r in rows:
        if r.get("motivation") is not None:
            out["motivation"] = r["motivation"]
        if r.get("soreness") is not None:
            out["soreness"] = r["soreness"]
        if r.get("illness_flag"):
            out["illness_flag"] = True
        if r.get("injury_flag"):
            out["injury_flag"] = True

    # Check illness past 5 days
    since_5 = (day - timedelta(days=5)).isoformat()
    res2 = sb.table("subjective_log").select("logged_at").eq(
        "illness_flag", True
    ).gte("logged_at", since_5).lte("logged_at", until).execute()
    if res2.data:
        last = max(r["logged_at"] for r in res2.data)
        # Days since
        from datetime import datetime as dt, timezone
        last_dt = dt.fromisoformat(last.replace("Z", "+00:00")).date()
        out["illness_recent_days"] = (day - last_dt).days

    return out


def compute_for(day: date, history_days: int = 90) -> dict:
    """Calcola daily_metrics per `day` e fa upsert."""
    sb = get_supabase()
    window_start = day - timedelta(days=history_days)

    activities = _fetch_activities_window(sb, window_start)
    daily_tss = aggregate_daily_tss(activities, lthr_by_sport=_fetch_lthr_by_sport(sb))

    # Seed PMC: CTL/ATL del giorno prima della finestra (se già calcolati).
    # Senza seed la serie parte da 0 e la finestra 90gg porta ~11.7% di errore.
    initial_ctl = initial_atl = 0.0
    seed_res = (
        sb.table("daily_metrics").select("ctl,atl")
        .eq("date", (window_start - timedelta(days=1)).isoformat())
        .execute()
    )
    seed_row = (seed_res.data or [None])[0]
    if seed_row and seed_row.get("ctl") is not None and seed_row.get("atl") is not None:
        initial_ctl = float(seed_row["ctl"])
        initial_atl = float(seed_row["atl"])
        # Ancora la serie a window_start (TSS=0) così il decay dal seed è
        # continuo anche se la prima attività è giorni dopo (o assente).
        if not any(t.day == window_start for t in daily_tss):
            daily_tss = sorted(
                daily_tss + [DailyTSS(day=window_start, tss=0.0)],
                key=lambda t: t.day,
            )

    pmc_series = compute_pmc_series(daily_tss, initial_ctl=initial_ctl, initial_atl=initial_atl)

    today_pmc = next((p for p in pmc_series if p.day == day), None)
    # Giorni senza attività (rest day, mattina prima della sessione): il punto
    # per `day` manca dalla serie → estrapola a TSS=0 fino a `day` invece di
    # scrivere ctl/atl/tsb NULL.
    if today_pmc is None and pmc_series and pmc_series[-1].day < day:
        today_pmc = compute_pmc_for_today(
            daily_tss, today=day, initial_ctl=initial_ctl, initial_atl=initial_atl
        )

    # HRV z-score
    wellness_rows = _fetch_wellness_window(sb, day - timedelta(days=28), day)
    today_iso = day.isoformat()
    today_wellness = next((r for r in wellness_rows if r["date"] == today_iso), {})

    # Storico HRV ESCLUDENDO oggi (per identità di data, non per valore).
    # Bug fix audit B1: escludere per valore rimuoveva ogni giorno con HRV uguale a
    # oggi (frequente su HRV stabile), distorcendo media/SD della baseline.
    hist_rows = [r for r in wellness_rows if r["date"] != today_iso]
    hrv_history = [r["hrv_rmssd"] for r in hist_rows if r.get("hrv_rmssd") is not None]

    z = None
    baseline_28 = None
    baseline_sd = None
    if today_wellness.get("hrv_rmssd") is not None and len(hrv_history) >= 7:
        import statistics
        baseline_28 = statistics.fmean(hrv_history)
        # SD campionaria (stdev), coerente con hrv_z_score — non pstdev.
        baseline_sd = statistics.stdev(hrv_history) if len(hrv_history) > 1 else 0
        z = hrv_z_score(today_wellness["hrv_rmssd"], hrv_history)

    # Readiness: z-score dei giorni PRECEDENTI (oggi escluso) per il check
    # "2 giorni consecutivi" (§5.1). Bug fix audit B2: includere oggi qui faceva
    # scattare fatigue_warning dopo 1 solo giorno invece di 2.
    # Allineamento calendario: l'elemento [-1] DEVE essere ieri (day-1). Si
    # costruisce la catena di date consecutive che termina a ieri; se ieri
    # manca la lista resta vuota (l'ultima riga wellness non è "ieri").
    recent_z_scores = []
    if len(hrv_history) >= 7:
        hrv_by_date = {
            r["date"]: r["hrv_rmssd"]
            for r in hist_rows if r.get("hrv_rmssd") is not None
        }
        chain: list[float] = []
        d = day - timedelta(days=1)
        while len(chain) < 5 and d.isoformat() in hrv_by_date:
            chain.append(hrv_by_date[d.isoformat()])
            d -= timedelta(days=1)
        for v in reversed(chain):
            z_past = hrv_z_score(v, hrv_history)
            if z_past is not None:
                recent_z_scores.append(z_past)

    wh = WellnessHistory(
        hrv_today=today_wellness.get("hrv_rmssd"),
        hrv_history_28d=hrv_history,
        hrv_recent_z_scores=recent_z_scores,
        sleep_score_today=today_wellness.get("sleep_score"),
        sleep_avg_7d=None,  # TODO se serve
        body_battery_morning=today_wellness.get("body_battery_max"),
        resting_hr_today=today_wellness.get("resting_hr"),
        resting_hr_baseline=None,
    )
    # Bug fix audit B3: passare None (non 0) quando manca il PMC, altrimenti
    # _score_tsb tratta tsb=0 come "ottimale" (100) in un giorno cold-start.
    ts = TrainingState(
        ctl=today_pmc.ctl if today_pmc else None,
        atl=today_pmc.atl if today_pmc else None,
        tsb=today_pmc.tsb if today_pmc else None,
        days_since_hard_session=None,
    )
    subj_data = _fetch_recent_subjective(sb, day)
    ss = SubjectiveState(**subj_data)

    readiness = compute_readiness(wh, ts, ss)

    # Recupera i dati Garmin training load dalla daily_wellness
    garmin_acute = today_wellness.get("training_load_acute") if today_wellness else None
    garmin_chronic = today_wellness.get("training_load_chronic") if today_wellness else None
    garmin_balance = None
    if garmin_acute is not None and garmin_chronic is not None:
        # Coerente col TSB nostro: positivo = fresco, negativo = stanco
        garmin_balance = round(garmin_chronic - garmin_acute, 2)
    garmin_status = today_wellness.get("training_status") if today_wellness else None

    metrics = {
        "date": day.isoformat(),
        # PMC nostro (TSS-based) — null finché non popoliamo zone fisiologiche
        "ctl": round(today_pmc.ctl, 2) if today_pmc else None,
        "atl": round(today_pmc.atl, 2) if today_pmc else None,
        "tsb": round(today_pmc.tsb, 2) if today_pmc else None,
        "daily_tss": round(today_pmc.daily_tss, 2) if today_pmc else None,
        # PMC Garmin (training load proprietario) — funzionante da subito
        "garmin_acute_load": round(garmin_acute, 2) if garmin_acute is not None else None,
        "garmin_chronic_load": round(garmin_chronic, 2) if garmin_chronic is not None else None,
        "garmin_load_balance": garmin_balance,
        "garmin_training_readiness": today_wellness.get("training_readiness_score") if today_wellness else None,
        "garmin_training_status": garmin_status,
        # HRV
        "hrv_z_score": round(z, 2) if z is not None else None,
        "hrv_baseline_28d": round(baseline_28, 2) if baseline_28 is not None else None,
        "hrv_baseline_28d_sd": round(baseline_sd, 2) if baseline_sd is not None else None,
        # Readiness
        "readiness_score": readiness.score,
        "readiness_label": readiness.label,
        "readiness_factors": readiness.factors,
        "flags": readiness.flags,
    }
    sb.table("daily_metrics").upsert(metrics, on_conflict="date").execute()
    return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        m = compute_for(today_rome())
        logger.info("daily_metrics: %s", m)
        record_health("analytics_daily", success=True)
    except Exception as e:  # noqa: BLE001
        logger.exception("Analytics daily failed")
        record_health("analytics_daily", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
