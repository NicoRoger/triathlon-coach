"""Fase 3.1 — Hypothesis testing framework.

Permette di formulare ipotesi sulla risposta dell'atleta e testarle
come esperimenti controllati su 2+ mesocicli alternati.

Workflow tipico:
1. propose_hypothesis(...) → status='proposed'
2. setup_experiment(...)   → status='setup', definisce arms + start_date
3. activate_experiment(id) → status='running', mesocicli vengono pianificati
4. analyze_experiment(id)  → status='analyzing', confronta metric tra arms
5. conclude_experiment(id) → status='validated/rejected/inconclusive'

Esempio:
    h = propose_hypothesis(
        hypothesis="L'atleta risponde meglio a polarized 80/20 vs piramidale",
        intervention="polarized 80/20",
        control="pyramidal default",
        metric="ctl_weekly",
        success_threshold=3.0,  # +3 CTL points di vantaggio per validare
        expected_effect="+5% CTL fine mesociclo build",
    )

L'analysis è rule-based (welch t-test approx + effect size).
Per sample size molto piccoli (n<8), il sistema accetta "inconclusive"
e mantiene status weak_belief invece di validate.

Costo: ZERO LLM. Solo query Supabase + statistica.
"""
from __future__ import annotations

import logging
import math
import statistics
from datetime import date, timedelta
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Lifecycle: propose / setup / activate / analyze / conclude
# ============================================================================

def propose_hypothesis(
    hypothesis: str,
    intervention: str,
    control: str,
    metric: str,
    success_threshold: float,
    expected_effect: Optional[str] = None,
    rationale: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Registra una nuova ipotesi in status 'proposed'. Ritorna id."""
    sb = get_supabase()
    row = {
        "status": "proposed",
        "hypothesis": hypothesis,
        "intervention": intervention,
        "control": control,
        "metric": metric,
        "success_threshold": success_threshold,
        "expected_effect": expected_effect,
        "rationale": rationale,
        "metadata": metadata,
    }
    row = {k: v for k, v in row.items() if v is not None}
    res = sb.table("hypothesis_tests").insert(row).execute()
    hid = res.data[0]["id"]
    logger.info("Hypothesis proposed: %s id=%s", hypothesis[:60], hid)
    return hid


def setup_experiment(
    hypothesis_id: str,
    arms: dict,
    start_date: date | str,
    end_date: date | str,
    related_mesocycle_ids: Optional[list[str]] = None,
) -> None:
    """Sposta ipotesi in 'setup' con definizione arms e date.

    arms: {"A": {"distribution": "polarized_8020", "weeks": [1,2,3]},
           "B": {"distribution": "pyramidal", "weeks": [5,6,7]}}
    """
    sb = get_supabase()
    if isinstance(start_date, date):
        start_date = start_date.isoformat()
    if isinstance(end_date, date):
        end_date = end_date.isoformat()
    sb.table("hypothesis_tests").update({
        "status": "setup",
        "arms": arms,
        "start_date": start_date,
        "end_date": end_date,
        "related_mesocycle_ids": related_mesocycle_ids or [],
    }).eq("id", hypothesis_id).execute()
    logger.info("Hypothesis %s setup: arms=%s, %s→%s",
                hypothesis_id, list(arms.keys()), start_date, end_date)


def activate_experiment(hypothesis_id: str) -> None:
    """Lo status passa a 'running'. Chiamato quando il primo mesociclo del
    setup è committato in planned_sessions."""
    sb = get_supabase()
    sb.table("hypothesis_tests").update({"status": "running"}).eq("id", hypothesis_id).execute()
    logger.info("Hypothesis %s activated (running)", hypothesis_id)


def abort_experiment(hypothesis_id: str, reason: str) -> None:
    """Aborta un esperimento (es. infortunio, cambio gara, dati corrotti)."""
    sb = get_supabase()
    sb.table("hypothesis_tests").update({
        "status": "aborted",
        "result_summary": f"Aborted: {reason}",
        "resolved_at": today_rome().isoformat(),
    }).eq("id", hypothesis_id).execute()
    logger.info("Hypothesis %s aborted: %s", hypothesis_id, reason)


# ============================================================================
# Analysis
# ============================================================================

def _fetch_metric_values(sb, metric: str, start: str, end: str, mesocycle_ids: list[str] | None = None) -> list[float]:
    """Recupera valori della metric nel range. Specifico per ogni metric type."""
    values: list[float] = []
    if metric == "ctl_weekly":
        res = (
            sb.table("daily_metrics")
            .select("date,ctl")
            .gte("date", start)
            .lte("date", end)
            .order("date")
            .execute()
        )
        for r in res.data or []:
            if r.get("ctl") is not None:
                values.append(float(r["ctl"]))
    elif metric == "compliance_pct":
        # Compliance settimana per settimana nel range
        d0 = date.fromisoformat(start)
        d1 = date.fromisoformat(end)
        cur = d0
        while cur <= d1:
            monday = cur - timedelta(days=cur.weekday())
            sunday = monday + timedelta(days=6)
            res = (
                sb.table("planned_sessions").select("status")
                .gte("planned_date", monday.isoformat())
                .lte("planned_date", sunday.isoformat())
                .execute()
            )
            if res.data:
                completed = sum(1 for s in res.data if s.get("status") == "completed")
                total = len(res.data)
                values.append(round(completed / total * 100, 1))
            cur = sunday + timedelta(days=1)
    elif metric == "rpe_avg":
        res = (
            sb.table("subjective_log")
            .select("rpe,logged_at")
            .gte("logged_at", start)
            .lte("logged_at", end + "T23:59:59Z")
            .not_.is_("rpe", "null")
            .execute()
        )
        for r in res.data or []:
            values.append(float(r["rpe"]))
    elif metric == "readiness_score":
        res = (
            sb.table("daily_metrics")
            .select("date,readiness_score")
            .gte("date", start)
            .lte("date", end)
            .order("date")
            .execute()
        )
        for r in res.data or []:
            if r.get("readiness_score") is not None:
                values.append(float(r["readiness_score"]))
    else:
        logger.warning("Unknown metric for hypothesis analysis: %s", metric)
    return values


def _welch_t_test(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """Welch t-test approssimato (non assume varianza uguale).

    Returns: (t_stat, p_value_approx, effect_size_cohens_d)
    P-value approssimato via 2 * (1 - normal_cdf(|t|)) come fallback senza scipy.
    Per sample piccoli (n<8) il p-value è poco affidabile — usare con cautela.
    """
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0, 0.0
    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    var_a = statistics.variance(a) if len(a) > 1 else 0
    var_b = statistics.variance(b) if len(b) > 1 else 0
    n_a, n_b = len(a), len(b)
    se = math.sqrt(var_a / n_a + var_b / n_b) if (var_a + var_b) > 0 else 1e-9
    t = (mean_a - mean_b) / se
    # Approx p-value via normal cdf (per t-test piccoli sample è solo indicativo)
    # P(|Z| > |t|) = 2 * (1 - Φ(|t|))
    z = abs(t)
    # Φ(z) via erfc approximation
    p = math.erfc(z / math.sqrt(2))
    # Cohen's d (pooled stddev)
    pooled_sd = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)) if (n_a + n_b - 2) > 0 else 0
    d = (mean_a - mean_b) / pooled_sd if pooled_sd > 0 else 0
    return round(t, 3), round(p, 4), round(d, 3)


def analyze_experiment(hypothesis_id: str) -> dict:
    """Confronta arms, calcola effetto, decide validated/rejected/inconclusive.

    Returns: dict con summary, effect, confidence, n_observations.
    """
    sb = get_supabase()
    res = sb.table("hypothesis_tests").select("*").eq("id", hypothesis_id).limit(1).execute()
    if not res.data:
        raise ValueError(f"Hypothesis {hypothesis_id} not found")
    h = res.data[0]
    arms = h.get("arms") or {}
    if len(arms) < 2:
        raise ValueError("Hypothesis arms must have at least 2 variants")
    metric = h["metric"]
    success_threshold = float(h.get("success_threshold") or 0)

    # Per ogni arm raccoglie i valori della metric nel periodo definito
    arm_values: dict[str, list[float]] = {}
    for arm_name, arm_def in arms.items():
        # arm_def può avere week_ranges o date_ranges
        ranges = arm_def.get("date_ranges") or []
        if not ranges and arm_def.get("start") and arm_def.get("end"):
            ranges = [{"start": arm_def["start"], "end": arm_def["end"]}]
        if not ranges and arm_def.get("weeks"):
            # weeks come list di numeri di settimana relativi a h.start_date
            base = date.fromisoformat(h["start_date"])
            for w in arm_def["weeks"]:
                wstart = base + timedelta(days=(w - 1) * 7)
                wend = wstart + timedelta(days=6)
                ranges.append({"start": wstart.isoformat(), "end": wend.isoformat()})

        values: list[float] = []
        for r in ranges:
            values.extend(_fetch_metric_values(sb, metric, r["start"], r["end"]))
        arm_values[arm_name] = values

    # Confronto pairwise tra arm "intervention" e "control" (default: prime 2)
    arm_names = list(arms.keys())
    a_name, b_name = arm_names[0], arm_names[1]
    a_vals, b_vals = arm_values[a_name], arm_values[b_name]
    if not a_vals or not b_vals:
        result = {
            "status": "inconclusive",
            "result_summary": f"Dati insufficienti (arm {a_name}: n={len(a_vals)}, arm {b_name}: n={len(b_vals)})",
            "effect_observed": 0.0,
            "confidence": 0.0,
            "n_observations": len(a_vals) + len(b_vals),
        }
    else:
        mean_a = statistics.mean(a_vals)
        mean_b = statistics.mean(b_vals)
        effect = mean_a - mean_b
        t, p, d = _welch_t_test(a_vals, b_vals)
        n_total = len(a_vals) + len(b_vals)

        # Decision logic:
        # - abs(effect) >= success_threshold AND p < 0.10 → validated
        # - abs(effect) >= success_threshold AND n_total < 8 → weak validation (confidence 0.55)
        # - abs(effect) < success_threshold AND n_total >= 10 → rejected
        # - altrimenti inconclusive
        if abs(effect) >= success_threshold and p < 0.10 and n_total >= 8:
            status = "validated"
            confidence = max(0.7, min(0.95, 1 - p))
            summary = (
                f"Intervention '{a_name}' superiore a '{b_name}' di {effect:+.2f} {metric} "
                f"(target ≥{success_threshold}, p={p}, Cohen d={d}, n={n_total}). VALIDATED."
            )
        elif abs(effect) >= success_threshold and n_total < 8:
            status = "inconclusive"
            confidence = 0.55
            summary = (
                f"Effetto osservato {effect:+.2f} {metric} a favore di '{a_name}' "
                f"(sample piccolo n={n_total}, p={p}). Promosso a WEAK belief, "
                f"da ri-testare con più dati."
            )
        elif abs(effect) < success_threshold and n_total >= 10:
            status = "rejected"
            confidence = 0.6
            summary = (
                f"Differenza {effect:+.2f} {metric} sotto soglia ({success_threshold}) "
                f"con n={n_total}. Nessuna evidenza di effetto significativo. REJECTED."
            )
        else:
            status = "inconclusive"
            confidence = 0.4
            summary = (
                f"Effetto {effect:+.2f} {metric} (target {success_threshold}), p={p}, n={n_total}. "
                f"Dati ambigui — INCONCLUSIVE."
            )

        result = {
            "status": status,
            "result_summary": summary,
            "effect_observed": round(effect, 3),
            "confidence": confidence,
            "n_observations": n_total,
            "p_value": p,
            "cohens_d": d,
            "arm_means": {a_name: round(mean_a, 3), b_name: round(mean_b, 3)},
        }

    # Persist
    sb.table("hypothesis_tests").update({
        "status": result["status"],
        "result_summary": result["result_summary"],
        "effect_observed": result.get("effect_observed"),
        "confidence": result.get("confidence"),
        "n_observations": result.get("n_observations"),
        "p_value": result.get("p_value"),
        "resolved_at": today_rome().isoformat(),
        "metadata": {
            **(h.get("metadata") or {}),
            "analysis": {
                "cohens_d": result.get("cohens_d"),
                "arm_means": result.get("arm_means"),
            },
        },
    }).eq("id", hypothesis_id).execute()
    logger.info("Hypothesis %s analyzed: status=%s effect=%s n=%s",
                hypothesis_id, result["status"], result.get("effect_observed"), result.get("n_observations"))
    return result


def list_active_hypotheses() -> list[dict]:
    """Tutte le ipotesi in running / analyzing."""
    sb = get_supabase()
    res = (
        sb.table("hypothesis_tests")
        .select("*")
        .in_("status", ["running", "analyzing", "setup"])
        .order("created_at", desc=False)
        .execute()
    )
    return res.data or []


def main() -> None:
    """CLI: --analyze <id> | --list."""
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--analyze", type=str, help="Analizza hypothesis_id")
    p.add_argument("--list", action="store_true", help="Lista esperimenti attivi")
    args = p.parse_args()
    if args.list:
        active = list_active_hypotheses()
        print(f"Active hypotheses: {len(active)}")
        for h in active:
            print(f"  - [{h['status']}] {h['hypothesis']}")
    elif args.analyze:
        r = analyze_experiment(args.analyze)
        print(f"Result: {r}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
