"""Verifica live dei valori analytics dal DB di produzione (HRV, PMC, Readiness, Risk).

Script informativo: stampa 4 sezioni leggibili per ispezione visiva dei fix B1/B3/B4.
Nessun exit automatico — l'operatore legge l'output e decide.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()  # DEVE precedere ogni import coach.* (lru_cache constraint)

from coach.utils.supabase_client import get_supabase
from coach.utils.dt import today_rome, to_rome_date
from coach.analytics.readiness import hrv_z_score

logger = logging.getLogger(__name__)


# ============================================================================
# Sezione HRV — verifica ANALYTICS-01 / fix B1
# ============================================================================
def _verify_hrv(sb, today_iso: str) -> None:
    """Ricalcola baseline HRV 28d escludendo oggi per DATA (fix B1)."""
    print("=== HRV Analytics ===")
    try:
        since = (date.fromisoformat(today_iso) - timedelta(days=28)).isoformat()
        res = (
            sb.table("daily_wellness")
            .select("date,hrv_rmssd")
            .gte("date", since)
            .execute()
        )
        rows = res.data or []

        # Esclusione per DATA, non per valore — questa è la verifica del fix B1
        hist_rows = [r for r in rows if r["date"] != today_iso]
        today_row = next((r for r in rows if r["date"] == today_iso), None)

        hrv_history = [
            r["hrv_rmssd"]
            for r in hist_rows
            if r.get("hrv_rmssd") is not None
        ]

        if len(hrv_history) < 7:
            print(f"Dati storici insufficienti (< 7 giorni HRV — ne ho {len(hrv_history)})")
        elif today_row is None or today_row.get("hrv_rmssd") is None:
            print(f"Nessun dato HRV per oggi ({today_iso})")
            mean = statistics.fmean(hrv_history)
            sd = statistics.pstdev(hrv_history)
            print(
                f"Baseline 28d: media={mean:.1f}ms, SD={sd:.1f}ms "
                f"({len(hrv_history)} giorni, oggi escluso)"
            )
        else:
            hrv_today_val = today_row["hrv_rmssd"]
            mean = statistics.fmean(hrv_history)
            sd = statistics.pstdev(hrv_history)
            z = hrv_z_score(hrv_today_val, hrv_history)

            print(
                f"Baseline 28d: media={mean:.1f}ms, SD={sd:.1f}ms "
                f"({len(hrv_history)} giorni, oggi escluso)"
            )

            if z is None:
                print("Z-score oggi: N/A (dati insufficienti)")
                print("Flag: nessuno")
            else:
                # Soglie CLAUDE.md §5.1
                if z < -2.0:
                    flag_label = "fatigue_critical"
                    flag_arrow = "CRITICO"
                elif z < -1.0:
                    flag_label = "fatigue_warning"
                    flag_arrow = "WARNING"
                else:
                    flag_label = "nessuno"
                    flag_arrow = "OK"

                print(f"Z-score oggi: {z:+.2f}σ → {flag_arrow}")
                print(f"Flag: {flag_label}")

    except Exception as exc:
        print(f"ERRORE sezione HRV: {exc}")
    print()


# ============================================================================
# Sezione PMC — verifica ANALYTICS-03 / fix B3
# ============================================================================
def _verify_pmc(sb, today_iso: str) -> None:
    """Stampa CTL/ATL/TSB da daily_metrics. None = fix B3 corretto; 0.00 = bug."""
    print("=== PMC ===")
    try:
        res = (
            sb.table("daily_metrics")
            .select("date,ctl,atl,tsb")
            .eq("date", today_iso)
            .execute()
        )
        row = res.data[0] if res.data else None

        if row is None:
            print(f"Nessun record daily_metrics per oggi ({today_iso})")
        else:
            ctl = row.get("ctl")
            atl = row.get("atl")
            tsb = row.get("tsb")

            if ctl is None and atl is None and tsb is None:
                print(f"CTL: None | ATL: None | TSB: None")
                print(
                    "PMC non disponibile (test FTP/soglia non ancora eseguiti — vedi Phase 2)"
                )
            else:
                tsb_str = f"{tsb:+.1f}" if tsb is not None else "None"
                ctl_str = f"{ctl:.1f}" if ctl is not None else "None"
                atl_str = f"{atl:.1f}" if atl is not None else "None"
                print(f"CTL: {ctl_str} | ATL: {atl_str} | TSB: {tsb_str}")

    except Exception as exc:
        print(f"ERRORE sezione PMC: {exc}")
    print()


# ============================================================================
# Sezione Readiness — verifica ANALYTICS-04
# ============================================================================
def _verify_readiness(sb, today_iso: str) -> None:
    """Stampa readiness score + label da daily_metrics."""
    print("=== Readiness ===")
    try:
        res = (
            sb.table("daily_metrics")
            .select("date,readiness_score,readiness_label")
            .eq("date", today_iso)
            .execute()
        )
        row = res.data[0] if res.data else None

        if row is None:
            print("Nessun dato readiness per oggi")
        else:
            score = row.get("readiness_score")
            label = row.get("readiness_label")

            if score is None and label is None:
                print("Nessun dato readiness per oggi")
            else:
                score_str = f"{score}/100" if score is not None else "None/100"
                label_str = label if label is not None else "(None)"
                print(f"Score: {score_str} | Label: {label_str}")

    except Exception as exc:
        print(f"ERRORE sezione Readiness: {exc}")
    print()


# ============================================================================
# Sezione Risk volume bucketing — verifica ANALYTICS-05 / fix B4
# ============================================================================
def _verify_risk_volumes(sb) -> None:
    """Stampa volume per disciplina questa settimana con date Europe/Rome (fix B4)."""
    print("=== Risk: Volume Bucketing (settimana corrente) ===")
    try:
        today = today_rome()
        this_week_start = today - timedelta(days=today.weekday())
        since = (today - timedelta(days=14)).isoformat()

        res = (
            sb.table("activities")
            .select("started_at,sport,duration_s")
            .gte("started_at", f"{since}T00:00:00Z")
            .execute()
        )

        by_sport: dict[str, float] = {}
        for a in res.data or []:
            # to_rome_date: verifica del fix B4 — usa timezone invece di slicing
            d = to_rome_date(a.get("started_at"))
            if d is not None and d >= this_week_start:
                sport = a.get("sport") or "unknown"
                duration_min = (a.get("duration_s") or 0) / 60
                by_sport[sport] = by_sport.get(sport, 0.0) + duration_min

        if not by_sport:
            print(f"Nessuna attività questa settimana (da {this_week_start}) (date: Europe/Rome)")
        else:
            parts = [f"{sport}: {mins:.0f}min" for sport, mins in sorted(by_sport.items())]
            print(" | ".join(parts) + " (date: Europe/Rome)")

    except Exception as exc:
        print(f"ERRORE sezione Risk: {exc}")
    print()


# ============================================================================
# main
# ============================================================================
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sb = get_supabase()
    today_iso = today_rome().isoformat()

    logger.info("verify_analytics.py — dati al %s", today_iso)
    print()

    _verify_hrv(sb, today_iso)
    _verify_pmc(sb, today_iso)
    _verify_readiness(sb, today_iso)
    _verify_risk_volumes(sb)


if __name__ == "__main__":
    main()
