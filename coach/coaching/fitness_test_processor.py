"""Fitness Test Auto-Detection — Blocco 1.

Detects fitness tests from recent activities matched against planned_sessions
with session_type='fitness_test'. Extracts results, computes zones, updates
physiology_zones DB and CLAUDE.md.

Uso: python -m coach.coaching.fitness_test_processor --check-recent
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

CLAUDE_MD_PATH = Path(__file__).resolve().parent.parent.parent / "CLAUDE.md"

SPORT_MAP = {"bike": "bike", "run": "run", "swim": "swim"}

TEST_CYCLE_ORDER = ["ftp_bike_20min", "ftp_bike_ramp", "threshold_run_30min", "css_swim_400_200", "lthr_run"]
TEST_CYCLE_NEXT = {
    "ftp_bike_20min": "threshold_run_30min",
    "ftp_bike_ramp": "threshold_run_30min",
    "threshold_run_30min": "css_swim_400_200",
    "css_swim_400_200": "lthr_run",
    "lthr_run": "ftp_bike_20min",
}


class FitnessTestProcessor:
    def __init__(self):
        self.sb = get_supabase()

    def process_fitness_test(self, activity: dict, planned_session: dict) -> dict:
        structured = planned_session.get("structured") or {}
        test_type = structured.get("test_type")
        activity_id = activity.get("id") or activity.get("external_id")

        if not test_type:
            return {"status": "skip", "reason": "no test_type in structured"}

        existing = self.sb.table("physiology_zones").select("id").eq(
            "test_activity_id", str(activity_id)
        ).limit(1).execute()
        if existing.data:
            logger.info("Already processed: activity %s", activity_id)
            return {"status": "skip", "reason": "already_processed"}

        extractor = {
            "ftp_bike_20min": self._extract_ftp_bike_20min,
            "ftp_bike_ramp": self._extract_ftp_bike_ramp,
            "threshold_run_30min": self._extract_threshold_run,
            "css_swim_400_200": self._extract_css_swim,
            "lthr_run": self._extract_lthr,
        }.get(test_type)

        if not extractor:
            return {"status": "error", "reason": f"unknown test_type: {test_type}"}

        result = extractor(activity, structured)

        if result is None:
            result = self._try_fallback_extraction(activity, structured)

        if result is None:
            self._notify_telegram(
                test_type, 0, {}, success=False,
                error_msg=f"splits non disponibili nel payload Garmin. "
                          f"Apri Claude.ai e scrivi: \"{structured.get('garmin_activity_name', test_type)} test today: [valore]\"",
            )
            return {"status": "fallback_failed", "test_type": test_type}

        zone_system = structured.get("zone_system", "coggan_7zone")
        zones = self._compute_zones(zone_system, result)

        sport = _test_type_to_sport(test_type)
        activity_date = str(activity.get("started_at", ""))[:10]

        self._upsert_physiology_zones(
            sport=sport,
            result=result,
            zones=zones,
            test_type=test_type,
            test_date=activity_date,
            source_activity_id=str(activity_id),
            zone_system=zone_system,
        )

        claude_md_field = structured.get("claude_md_field")
        claude_md_ok = False
        if claude_md_field:
            claude_md_ok = self._update_claude_md(claude_md_field, result, test_type, activity_date)

        self._notify_telegram(test_type, result, zones, success=True)

        return {
            "status": "processed",
            "test_type": test_type,
            "result": result,
            "zones": zones,
            "claude_md_updated": claude_md_ok,
        }

    # ── Extractors ─────────────────────────────────────────────────────────

    def _extract_ftp_bike_20min(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index", 1)
        if splits and isinstance(splits, list) and len(splits) > idx:
            avg_power = splits[idx].get("avg_power_w") or splits[idx].get("averageSpeed")
            if avg_power:
                return round(float(avg_power) * 0.95, 1)
        return None

    def _extract_ftp_bike_ramp(self, activity: dict, structured: dict) -> Optional[float]:
        max_power = activity.get("max_power_w") or activity.get("np_w")
        if max_power:
            return round(float(max_power) * 0.75, 1)
        return None

    def _extract_threshold_run(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index", 1)
        if splits and isinstance(splits, list) and len(splits) > idx:
            pace = splits[idx].get("avg_pace_s_per_km") or splits[idx].get("averagePace")
            if pace:
                return round(float(pace), 1)
        return None

    def _extract_css_swim(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        if not splits or not isinstance(splits, list) or len(splits) < 2:
            return None

        t400 = None
        t200 = None
        for s in splits:
            dist = s.get("distance_m") or s.get("distance") or 0
            time_s = s.get("duration_s") or s.get("movingDuration") or s.get("elapsedDuration") or 0
            dist = float(dist)
            time_s = float(time_s)
            if 350 <= dist <= 450 and t400 is None:
                t400 = time_s
            elif 180 <= dist <= 250 and t200 is None:
                t200 = time_s

        if t400 is not None and t200 is not None:
            css_per_100m = (t400 - t200) / 2
            return round(css_per_100m, 1)
        return None

    def _extract_lthr(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index", 1)
        if splits and isinstance(splits, list) and len(splits) > idx:
            avg_hr = splits[idx].get("avg_hr") or splits[idx].get("averageHR")
            if avg_hr:
                return round(float(avg_hr) * 0.98)
        return None

    def _try_fallback_extraction(self, activity: dict, structured: dict) -> Optional[float]:
        extraction = structured.get("extraction") or {}
        fallback = extraction.get("fallback")
        if not fallback:
            return None

        field = fallback.get("field")
        formula = fallback.get("formula", "value")
        value = activity.get(field)
        if value is None:
            return None

        value = float(value)
        result = _eval_formula(formula, value)
        return round(result, 1) if result is not None else None

    # ── Zone calculators ───────────────────────────────────────────────────

    def _compute_zones(self, zone_system: str, result: float) -> dict:
        calculators = {
            "coggan_7zone": self._compute_coggan_7zone,
            "pace_5zone": self._compute_pace_5zone,
            "css_3zone": self._compute_css_3zone,
            "lthr_5zone": self._compute_lthr_5zone,
        }
        calc = calculators.get(zone_system)
        if not calc:
            logger.warning("Unknown zone_system: %s", zone_system)
            return {}
        return calc(result)

    @staticmethod
    def _compute_coggan_7zone(ftp_w: float) -> dict:
        return {
            "Z1_recovery": f"<{round(ftp_w * 0.55)}W",
            "Z2_endurance": f"{round(ftp_w * 0.56)}-{round(ftp_w * 0.75)}W",
            "Z3_tempo": f"{round(ftp_w * 0.76)}-{round(ftp_w * 0.90)}W",
            "Z4_threshold": f"{round(ftp_w * 0.91)}-{round(ftp_w * 1.05)}W",
            "Z5_vo2max": f"{round(ftp_w * 1.06)}-{round(ftp_w * 1.20)}W",
            "Z6_anaerobic": f"{round(ftp_w * 1.21)}-{round(ftp_w * 1.50)}W",
            "Z7_neuromuscular": f">{round(ftp_w * 1.50)}W",
        }

    @staticmethod
    def _compute_pace_5zone(threshold_pace_s_km: float) -> dict:
        tp = threshold_pace_s_km
        return {
            "Z1_recovery": f">{_fmt_pace(tp * 1.25)}/km",
            "Z2_endurance": f"{_fmt_pace(tp * 1.15)}-{_fmt_pace(tp * 1.25)}/km",
            "Z3_tempo": f"{_fmt_pace(tp * 1.05)}-{_fmt_pace(tp * 1.15)}/km",
            "Z4_threshold": f"{_fmt_pace(tp * 0.97)}-{_fmt_pace(tp * 1.05)}/km",
            "Z5_vo2max": f"<{_fmt_pace(tp * 0.97)}/km",
        }

    @staticmethod
    def _compute_css_3zone(css_s_100m: float) -> dict:
        return {
            "CSS_minus5": f"{_fmt_swim_pace(css_s_100m + 5)}/100m (endurance)",
            "CSS": f"{_fmt_swim_pace(css_s_100m)}/100m (threshold)",
            "CSS_plus5": f"{_fmt_swim_pace(max(css_s_100m - 5, 30))}/100m (VO2max)",
        }

    @staticmethod
    def _compute_lthr_5zone(lthr: float) -> dict:
        lthr = int(lthr)
        return {
            "Z1_recovery": f"<{round(lthr * 0.81)} bpm",
            "Z2_aerobic": f"{round(lthr * 0.81)}-{round(lthr * 0.89)} bpm",
            "Z3_tempo": f"{round(lthr * 0.90)}-{round(lthr * 0.95)} bpm",
            "Z4_threshold": f"{round(lthr * 0.96)}-{round(lthr * 1.00)} bpm",
            "Z5_above": f">{lthr} bpm",
        }

    # ── Persistence ────────────────────────────────────────────────────────

    def _upsert_physiology_zones(
        self, sport: str, result: float, zones: dict,
        test_type: str, test_date: str, source_activity_id: str,
        zone_system: str,
    ) -> None:
        field_map = {
            "ftp_bike_20min": ("ftp_w", "bike"),
            "ftp_bike_ramp": ("ftp_w", "bike"),
            "threshold_run_30min": ("threshold_pace_s_per_km", "run"),
            "css_swim_400_200": ("css_pace_s_per_100m", "swim"),
            "lthr_run": ("lthr", "run"),
        }
        db_field, discipline = field_map.get(test_type, (None, sport))
        if not db_field:
            return

        record = {
            "discipline": discipline,
            "valid_from": test_date,
            db_field: result,
            "test_activity_id": source_activity_id,
            "method": test_type,
            "notes": json.dumps({"zones": zones, "zone_system": zone_system}),
        }

        self.sb.table("physiology_zones").upsert(
            record, on_conflict="discipline,valid_from"
        ).execute()
        logger.info("Physiology zones upserted: %s %s=%s", discipline, db_field, result)

    def _update_claude_md(self, field: str, value: float, test_type: str, test_date: str) -> bool:
        try:
            content = CLAUDE_MD_PATH.read_text(encoding="utf-8")

            if field == "threshold_pace_per_km":
                display_value = _fmt_pace(value)
            elif field == "css_attuale_per_100m":
                display_value = _fmt_swim_pace(value)
            else:
                display_value = str(round(value))

            pattern = rf"({re.escape(field)}:\s*).*"
            new_line = rf"\g<1>{display_value} (test {test_date})"
            updated, count = re.subn(pattern, new_line, content)

            if count == 0:
                logger.warning("CLAUDE.md field '%s' not found", field)
                return False

            CLAUDE_MD_PATH.write_text(updated, encoding="utf-8")
            logger.info("CLAUDE.md updated: %s → %s", field, display_value)
            return True
        except Exception:
            logger.exception("Failed to update CLAUDE.md")
            return False

    def _notify_telegram(self, test_type: str, result: float, zones: dict, success: bool, error_msg: str = "") -> None:
        try:
            from coach.utils.telegram_logger import send_and_log_message
        except ImportError:
            logger.warning("telegram_logger not available")
            return

        if success:
            zone_lines = "\n".join(f"  {k}: {v}" for k, v in zones.items())
            next_test = TEST_CYCLE_NEXT.get(test_type, "?")
            msg = (
                f"<b>Test {_test_display_name(test_type)} processato</b>\n\n"
                f"Risultato: <b>{_format_result(test_type, result)}</b>\n"
                f"Zone aggiornate:\n{zone_lines}\n\n"
                f"Prossimo test consigliato: tra 6 settimane\n"
                f"Prossimo nel ciclo: {_test_display_name(next_test)}"
            )
        else:
            msg = (
                f"<b>Test {_test_display_name(test_type)} — elaborazione fallita</b>\n\n"
                f"{error_msg}\n\n"
                f"<i>Il coach aggiornerà le zone manualmente.</i>"
            )

        send_and_log_message(msg, purpose="generic", parent_workflow="ingest.yml")


# ── Helpers ────────────────────────────────────────────────────────────────

def _test_type_to_sport(test_type: str) -> str:
    if "bike" in test_type:
        return "bike"
    if "run" in test_type or "lthr" in test_type:
        return "run"
    if "swim" in test_type or "css" in test_type:
        return "swim"
    return "other"


def _eval_formula(formula: str, value: float) -> Optional[float]:
    formula = formula.strip()
    m = re.match(r"value\s*\*\s*([\d.]+)", formula)
    if m:
        return value * float(m.group(1))
    if formula == "value":
        return value
    return None


def _fmt_pace(seconds_per_km: float) -> str:
    mins = int(seconds_per_km) // 60
    secs = int(seconds_per_km) % 60
    return f"{mins}:{secs:02d}"


def _fmt_swim_pace(seconds_per_100m: float) -> str:
    mins = int(seconds_per_100m) // 60
    secs = int(seconds_per_100m) % 60
    return f"{mins}:{secs:02d}"


def _test_display_name(test_type: str) -> str:
    names = {
        "ftp_bike_20min": "FTP Bici 20min",
        "ftp_bike_ramp": "FTP Bici Ramp",
        "threshold_run_30min": "Soglia Corsa 30min",
        "css_swim_400_200": "CSS Nuoto 400+200",
        "lthr_run": "LTHR Corsa",
    }
    return names.get(test_type, test_type)


def _format_result(test_type: str, result: float) -> str:
    if "ftp" in test_type:
        return f"{round(result)}W"
    if "threshold" in test_type:
        return f"{_fmt_pace(result)}/km"
    if "css" in test_type:
        return f"{_fmt_swim_pace(result)}/100m"
    if "lthr" in test_type:
        return f"{round(result)} bpm"
    return str(result)


# ── CLI entry point ────────────────────────────────────────────────────────

def check_recent() -> list[dict]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()
    processor = FitnessTestProcessor()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    activities = sb.table("activities").select(
        "id,external_id,started_at,sport,duration_s,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,avg_pace_s_per_100m,tss,splits"
    ).gte("started_at", cutoff).in_(
        "sport", ["bike", "run", "swim"]
    ).order("started_at", desc=True).limit(10).execute().data or []

    results = []
    for activity in activities:
        activity_date = str(activity.get("started_at", ""))[:10]
        sport = activity.get("sport")

        planned = sb.table("planned_sessions").select("*").eq(
            "planned_date", activity_date
        ).eq("sport", sport).eq(
            "session_type", "fitness_test"
        ).limit(1).execute().data

        if planned:
            logger.info("Matched planned fitness test: %s %s", sport, activity_date)
            result = processor.process_fitness_test(activity, planned[0])
            results.append(result)
            continue

        name = (activity.get("notes") or activity.get("external_id") or "").lower()
        keywords = ["ftp", "css", "threshold", "soglia", "test", "ramp"]
        if any(kw in name for kw in keywords):
            logger.info("Keyword match (no planned_session): %s — flagging for manual review", name)
            try:
                from coach.utils.telegram_logger import send_and_log_message
                send_and_log_message(
                    f"<b>Possibile test fitness rilevato</b>\n\n"
                    f"Attività: {activity.get('external_id')}\n"
                    f"Sport: {sport}, Data: {activity_date}\n\n"
                    f"<i>Nessuna sessione pianificata con session_type='fitness_test'. "
                    f"Apri Claude.ai per aggiornare le zone manualmente.</i>",
                    purpose="generic",
                    parent_workflow="ingest.yml",
                )
            except Exception:
                logger.exception("Failed to send keyword match notification")
            results.append({"status": "keyword_match_manual_review", "activity": activity.get("external_id")})

    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--check-recent", action="store_true")
    args = parser.parse_args()

    if args.check_recent:
        results = check_recent()
        for r in results:
            print(json.dumps(r, default=str))
    else:
        print("Usage: python -m coach.coaching.fitness_test_processor --check-recent")


if __name__ == "__main__":
    main()
