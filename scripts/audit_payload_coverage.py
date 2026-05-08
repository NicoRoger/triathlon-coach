"""Audit raw_payload coverage: trova campi Garmin non mappati in colonne native.

Task 0.2 di Step 5.1. Per ogni tabella con raw_payload (daily_wellness, activities):
1. Campiona 5 righe recenti
2. Estrae ricorsivamente TUTTI i path nel JSON
3. Verifica se viene mappato in una colonna nativa
4. Output: tabella path → colonna_native | NON_MAPPATO

Salva in docs/audit_garmin_completeness_2026-05-07.md
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Aggiungi root al path per import coach.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Colonne native per tabella (escluse quelle di sistema)
NATIVE_COLUMNS = {
    "daily_wellness": {
        "hrv_rmssd", "hrv_status",
        "sleep_score", "sleep_total_s", "sleep_deep_s", "sleep_rem_s", "sleep_efficiency",
        "body_battery_min", "body_battery_max", "stress_avg",
        "resting_hr",
        "training_status", "training_load_acute", "training_load_chronic",
        "vo2max_run", "vo2max_bike",
        "training_readiness_score", "avg_sleep_stress",
    },
    "activities": {
        "external_id", "source", "sport",
        "started_at", "duration_s", "distance_m", "elevation_gain_m",
        "avg_hr", "max_hr", "hr_zones_s",
        "avg_power_w", "np_w", "avg_pace_s_per_km", "avg_pace_s_per_100m",
        "tss", "if_value", "rpe",
        "notes",
        "splits", "weather",
    },
}

# Mapping noto: path JSON → colonna nativa
# Questo è il cuore dell'audit: mappa i path noti dal payload Garmin
# alle colonne in cui il dato viene effettivamente estratto.
KNOWN_MAPPINGS = {
    "daily_wellness": {
        # user_summary top-level
        "bodyBatteryLowestValue": "body_battery_min",
        "bodyBatteryHighestValue": "body_battery_max",
        "averageStressLevel": "stress_avg",
        "restingHeartRate": "resting_hr",
        # sleep
        "sleep.avgOvernightHrv": "hrv_rmssd",
        "sleep.hrvStatus": "hrv_status",
        "sleep.dailySleepDTO.sleepScores.overall.value": "sleep_score",
        "sleep.dailySleepDTO.sleepTimeSeconds": "sleep_total_s",
        "sleep.dailySleepDTO.deepSleepSeconds": "sleep_deep_s",
        "sleep.dailySleepDTO.remSleepSeconds": "sleep_rem_s",
        "sleep.dailySleepDTO.awakeSleepSeconds": "sleep_efficiency",  # usato per calcolo
        # hrv
        "hrv.hrvSummary.lastNightAvg": "hrv_rmssd",
        "hrv.hrvSummary.status": "hrv_status",
        # max_metrics
        "max_metrics.generic.vo2MaxValue": "vo2max_run",
        "max_metrics.generic.vo2MaxPreciseValue": "vo2max_run",
        "max_metrics.cycling.vo2MaxValue": "vo2max_bike",
        "max_metrics.cycling.vo2MaxPreciseValue": "vo2max_bike",
        # training_status
        "training_status.mostRecentTrainingStatus.latestTrainingStatusData.*.trainingStatus": "training_status",
        "training_status.mostRecentTrainingStatus.latestTrainingStatusData.*.acuteTrainingLoadDTO.dailyTrainingLoadAcute": "training_load_acute",
        "training_status.mostRecentTrainingStatus.latestTrainingStatusData.*.acuteTrainingLoadDTO.dailyTrainingLoadChronic": "training_load_chronic",
    },
    "activities": {
        "activityId": "external_id",
        "activityType.typeKey": "sport",
        "startTimeGMT": "started_at",
        "duration": "duration_s",
        "distance": "distance_m",
        "elevationGain": "elevation_gain_m",
        "averageHR": "avg_hr",
        "maxHR": "max_hr",
        "averageSpeed": "avg_pace_s_per_km",  # calcolato
        "avgPower": "avg_power_w",
        "normPower": "np_w",
        "trainingStressScore": "tss",
        "intensityFactor": "if_value",
        "hrTimeInZone_1": "hr_zones_s",
        "hrTimeInZone_2": "hr_zones_s",
        "hrTimeInZone_3": "hr_zones_s",
        "hrTimeInZone_4": "hr_zones_s",
        "hrTimeInZone_5": "hr_zones_s",
    },
}


def extract_paths(obj: Any, prefix: str = "") -> set[str]:
    """Estrae ricorsivamente tutti i path da un oggetto JSON."""
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            full_path = f"{prefix}.{key}" if prefix else key
            paths.add(full_path)
            paths.update(extract_paths(value, full_path))
    elif isinstance(obj, list) and obj:
        # Campiona il primo elemento per struttura
        paths.update(extract_paths(obj[0], f"{prefix}[0]"))
    return paths


def classify_path(path: str, table: str) -> str:
    """Classifica un path come mappato a colonna nativa o NON_MAPPATO."""
    mappings = KNOWN_MAPPINGS.get(table, {})

    # Check diretto
    if path in mappings:
        return mappings[path]

    # Check con wildcard (per strutture con device ID)
    for pattern, col in mappings.items():
        if "*" in pattern:
            parts = pattern.split("*")
            if len(parts) == 2 and path.startswith(parts[0]) and path.endswith(parts[1]):
                return col

    # Check se il path è un antenato di un mapping noto (struttura intermedia)
    for mapped_path in mappings:
        clean = mapped_path.replace("*.", "")
        if clean.startswith(path + "."):
            return f"(parent di {mappings[mapped_path]})"

    return "NON_MAPPATO"


def audit_table(sb, table: str, sample_size: int = 5) -> list[dict]:
    """Audita una tabella: campiona raw_payload, estrae path, classifica."""
    res = sb.table(table).select("raw_payload").order(
        "created_at", desc=True
    ).limit(sample_size).execute()

    if not res.data:
        logger.warning("Nessun dato in %s", table)
        return []

    # Unione di tutti i path trovati
    all_paths: set[str] = set()
    for row in res.data:
        payload = row.get("raw_payload")
        if payload:
            all_paths.update(extract_paths(payload))

    # Classifica
    results = []
    for path in sorted(all_paths):
        # Ignora path troppo profondi (array index) e path di sistema
        if "[0]" in path:
            clean = path.replace("[0]", ".*")
        else:
            clean = path
        classification = classify_path(clean, table)
        results.append({
            "path": path,
            "mapped_to": classification,
        })

    return results


def generate_report(wellness_audit: list[dict], activities_audit: list[dict]) -> str:
    """Genera il report markdown."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Audit Completezza Garmin — {now}",
        "",
        "> Generato da `scripts/audit_payload_coverage.py` (Task 0.2 Step 5.1)",
        "",
        "## Metodologia",
        "",
        "- Campionati 5 record recenti per tabella",
        "- Estratti ricorsivamente tutti i path JSON dal `raw_payload`",
        "- Classificato ogni path come mappato a colonna nativa o NON_MAPPATO",
        "",
        "---",
        "",
        "## daily_wellness — raw_payload coverage",
        "",
        "| Path JSON | Mappato a | Stato |",
        "|-----------|-----------|-------|",
    ]

    wellness_mapped = 0
    wellness_total = 0
    for item in wellness_audit:
        status = "✅" if item["mapped_to"] != "NON_MAPPATO" else "❌"
        if not item["mapped_to"].startswith("(parent"):
            wellness_total += 1
            if item["mapped_to"] != "NON_MAPPATO":
                wellness_mapped += 1
        lines.append(f"| `{item['path']}` | {item['mapped_to']} | {status} |")

    lines.extend([
        "",
        f"**Copertura wellness:** {wellness_mapped}/{wellness_total} "
        f"leaf path mappati ({wellness_mapped/max(wellness_total,1)*100:.0f}%)",
        "",
        "---",
        "",
        "## activities — raw_payload coverage",
        "",
        "| Path JSON | Mappato a | Stato |",
        "|-----------|-----------|-------|",
    ])

    act_mapped = 0
    act_total = 0
    for item in activities_audit:
        status = "✅" if item["mapped_to"] != "NON_MAPPATO" else "❌"
        if not item["mapped_to"].startswith("(parent"):
            act_total += 1
            if item["mapped_to"] != "NON_MAPPATO":
                act_mapped += 1
        lines.append(f"| `{item['path']}` | {item['mapped_to']} | {status} |")

    lines.extend([
        "",
        f"**Copertura activities:** {act_mapped}/{act_total} "
        f"leaf path mappati ({act_mapped/max(act_total,1)*100:.0f}%)",
        "",
        "---",
        "",
        "## Decision matrix — Endpoint non chiamati",
        "",
        "| Endpoint/path Garmin | Estratto attualmente? | Valore per il coach | Decisione |",
        "|----------------------|----------------------|---------------------|-----------| ",
        "| `get_training_readiness(date)` | NO | Alto: score Garmin proprietario per readiness | **DA AGGIUNGERE** |",
        "| `get_activity_splits(id)` | NO | Alto: split per km/lap, pace consistency | **DA AGGIUNGERE** |",
        "| `get_activity_weather(id)` | NO | Alto in race week: meteo gara | **DA AGGIUNGERE** |",
        "| `sleep.dailySleepDTO.averageSleepStress` | NO (nel payload ma non estratto) | Alto: stress notturno = recovery quality | **DA AGGIUNGERE** |",
        "| `get_body_battery(start, end)` | Solo min/max | Medio: time series orario | DA VALUTARE |",
        "| `get_stress_data(date)` | Solo avg | Medio: curva stress oraria | DA VALUTARE |",
        "| `get_race_predictor()` | NO | Medio: cross-validation con race_prediction | DA VALUTARE |",
        "| `get_endurance_score(date)` | NO | Medio: endurance score | DA VALUTARE |",
        "| `download_activity(id, dl_fmt)` | NO | Variabile: FIT/GPX per analisi profilo | DA VALUTARE (storage) |",
        "| `get_respiration_data(date)` | NO | Basso | SKIP |",
        "| `get_steps_data(date)` | NO | Basso: non rilevante triathlon | SKIP |",
        "| `get_floors(date)` | NO | Basso | SKIP |",
        "| `get_intensity_minutes(start, end)` | NO | Basso: ridondante con TSS | SKIP |",
        "| `get_pulse_ox(date)` | NO | Basso: solo alta quota | SKIP |",
        "| `get_hill_score(date)` | NO | Basso | SKIP |",
        "| `get_personal_record()` | NO | Basso: nice-to-have | SKIP |",
        "| `get_devices()` | NO | Basso: diagnostico | SKIP |",
        "| `get_solar_data(date)` | NO | Basso | SKIP |",
        "| `get_heart_rates(date)` | NO | Basso: ridondante | SKIP |",
        "| `get_spo2_data(date)` | NO | Basso | SKIP |",
        "",
        "### Criterio decisionale",
        "",
        "- **DA AGGIUNGERE**: aiuta direttamente decisioni del coach (sessione di oggi, race plan, gestione infortuni, predizione gara)",
        "- **DA VALUTARE**: interessante ma non urgente, implementare in iterazione successiva",
        "- **SKIP**: rumore, ridondante o non rilevante per il contesto di coaching triathlon",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sb = get_supabase()

    logger.info("Auditing daily_wellness...")
    wellness_audit = audit_table(sb, "daily_wellness")

    logger.info("Auditing activities...")
    activities_audit = audit_table(sb, "activities")

    report = generate_report(wellness_audit, activities_audit)

    output_path = Path(__file__).resolve().parent.parent / "docs" / "audit_garmin_completeness_2026-05-07.md"
    output_path.write_text(report, encoding="utf-8")
    logger.info("Report salvato in %s", output_path)

    # Stampa anche a console
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
