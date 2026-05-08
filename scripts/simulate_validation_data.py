import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from coach.utils.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKUP_FILE = "backup_scenario_state.json"
MOCK_TAG = "MOCK_SCENARIO"

def get_date_range(days_back=21):
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days_back + 1)]

def backup_daily_data(sb, dates) -> None:
    logger.info("Backing up daily_metrics and daily_wellness...")
    backup = {"daily_metrics": [], "daily_wellness": []}
    
    res_metrics = sb.table("daily_metrics").select("*").in_("date", dates).execute()
    backup["daily_metrics"] = res_metrics.data
    
    res_wellness = sb.table("daily_wellness").select("*").in_("date", dates).execute()
    backup["daily_wellness"] = res_wellness.data
    
    with open(BACKUP_FILE, "w") as f:
        json.dump(backup, f, indent=2)
    logger.info(f"Backup saved to {BACKUP_FILE} ({len(backup['daily_metrics'])} metrics, {len(backup['daily_wellness'])} wellness)")

def restore_daily_data(sb) -> None:
    if not os.path.exists(BACKUP_FILE):
        logger.warning(f"No backup file {BACKUP_FILE} found. Skipping daily restore.")
        return
    
    with open(BACKUP_FILE, "r") as f:
        backup = json.load(f)
    
    if backup.get("daily_metrics"):
        logger.info(f"Restoring {len(backup['daily_metrics'])} daily_metrics...")
        sb.table("daily_metrics").upsert(backup["daily_metrics"]).execute()
        
    if backup.get("daily_wellness"):
        logger.info(f"Restoring {len(backup['daily_wellness'])} daily_wellness...")
        sb.table("daily_wellness").upsert(backup["daily_wellness"]).execute()
        
    os.remove(BACKUP_FILE)
    logger.info("Daily data restored and backup file deleted.")

def cleanup_mock_data(sb) -> None:
    logger.info("Cleaning up mock activities, logs, and races...")
    
    # Clean activities
    res_act = sb.table("activities").delete().like("external_id", f"{MOCK_TAG}%").execute()
    logger.info(f"Deleted {len(res_act.data)} mock activities.")
    
    # Clean subjective log
    res_log = sb.table("subjective_log").delete().like("raw_text", f"%{MOCK_TAG}%").execute()
    logger.info(f"Deleted {len(res_log.data)} mock subjective logs.")
    
    # Clean races
    res_races = sb.table("races").delete().like("notes", f"%{MOCK_TAG}%").execute()
    logger.info(f"Deleted {len(res_races.data)} mock races.")
    
    restore_daily_data(sb)

def apply_scenario_1(sb):
    """Steady State: progressione normale, TSB neutro/leggermente negativo."""
    dates = get_date_range(21)
    backup_daily_data(sb, dates)
    
    metrics_to_upsert = []
    today = date.today()
    for i in range(21, -1, -1):
        d = today - timedelta(days=i)
        # Simulate a steady build: CTL goes from 40 to 46
        ctl = 40.0 + (6.0 * (21 - i) / 21.0)
        atl = ctl + 5.0 # TSB slightly negative
        tsb = ctl - atl
        metrics_to_upsert.append({
            "date": d.isoformat(),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "daily_tss": 50 if i % 7 != 0 else 100, # Long run on weekends
            "hrv_z_score": 0.2, # Good HRV
            "readiness_score": 85,
            "readiness_label": "ready",
            "flags": []
        })
    sb.table("daily_metrics").upsert(metrics_to_upsert).execute()
    logger.info("Scenario 1 applied: Steady state metrics injected.")

def apply_scenario_2(sb):
    """Crash & Burn: Fatica acuta, HRV -2.5, TSB -30."""
    dates = get_date_range(2)
    backup_daily_data(sb, dates)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    metrics = [
        {
            "date": yesterday.isoformat(),
            "ctl": 45.0, "atl": 70.0, "tsb": -25.0,
            "hrv_z_score": -2.1,
            "readiness_score": 30,
            "readiness_label": "rest",
            "flags": ["fatigue_critical"]
        },
        {
            "date": today.isoformat(),
            "ctl": 46.0, "atl": 76.0, "tsb": -30.0,
            "hrv_z_score": -2.5,
            "readiness_score": 20,
            "readiness_label": "rest",
            "flags": ["fatigue_critical"]
        }
    ]
    sb.table("daily_metrics").upsert(metrics).execute()
    
    wellness = [
        {"date": yesterday.isoformat(), "sleep_score": 40, "body_battery_max": 30},
        {"date": today.isoformat(), "sleep_score": 35, "body_battery_max": 25}
    ]
    sb.table("daily_wellness").upsert(wellness).execute()
    
    sb.table("subjective_log").insert({
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "kind": "morning",
        "raw_text": f"{MOCK_TAG} gambe di legno, mi sento svuotato, ho dormito malissimo",
        "motivation": 3
    }).execute()
    logger.info("Scenario 2 applied: Crash & Burn injected.")

def apply_scenario_3(sb):
    """The Curveball: Imprevisto logistico (la base è simile allo scenario 1, l'imprevisto lo chiede l'utente)."""
    apply_scenario_1(sb)
    logger.info("Scenario 3 applied: Base steady state injected (ask Claude about the trip).")

def apply_scenario_4(sb):
    """Il Falso Positivo: Dati oggettivi ottimi, RPE pessimo."""
    dates = get_date_range(2)
    backup_daily_data(sb, dates)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    metrics = [
        {
            "date": yesterday.isoformat(),
            "ctl": 45.0, "atl": 50.0, "tsb": -5.0,
            "hrv_z_score": 0.5, "readiness_score": 90, "readiness_label": "ready", "flags": []
        },
        {
            "date": today.isoformat(),
            "ctl": 45.5, "atl": 55.0, "tsb": -9.5,
            "hrv_z_score": 0.1, "readiness_score": 85, "readiness_label": "ready", "flags": []
        }
    ]
    sb.table("daily_metrics").upsert(metrics).execute()
    
    # Crea un'attività finta ieri
    res = sb.table("activities").insert({
        "external_id": f"{MOCK_TAG}_act1",
        "source": "manual",
        "sport": "bike",
        "started_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "duration_s": 3600,
        "np_w": 250, # Ottimo
        "tss": 85,
        "notes": f"Workout perfetto su carta ({MOCK_TAG})"
    }).execute()
    
    act_id = res.data[0]["id"]
    
    # Crea il log negativo
    sb.table("subjective_log").insert({
        "logged_at": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(),
        "activity_id": act_id,
        "kind": "post_session",
        "rpe": 9,
        "raw_text": f"{MOCK_TAG} sensazioni orribili, non stavo in piedi. I watt c'erano ma che fatica inutile.",
        "soreness": 5
    }).execute()
    logger.info("Scenario 4 applied: Falso positivo injected.")

def apply_scenario_5(sb):
    """Race Week: Gara tra 7 giorni."""
    dates = get_date_range(2)
    backup_daily_data(sb, dates)
    # Impostiamo CTL buono
    metrics = [{
        "date": date.today().isoformat(),
        "ctl": 60.0, "atl": 60.0, "tsb": 0.0,
        "hrv_z_score": 0.5, "readiness_score": 95, "readiness_label": "ready", "flags": []
    }]
    sb.table("daily_metrics").upsert(metrics).execute()
    
    race_date = date.today() + timedelta(days=7)
    sb.table("races").insert({
        "name": "Lavarone Cross Sprint",
        "race_date": race_date.isoformat(),
        "distance": "sprint",
        "priority": "A",
        "notes": f"Gara obiettivo ({MOCK_TAG})"
    }).execute()
    logger.info(f"Scenario 5 applied: Race A inserted at {race_date}.")

def main():
    parser = argparse.ArgumentParser(description="Simulate validation data for Triathlon Coach AI.")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3, 4, 5], help="Scenario number to apply.")
    parser.add_argument("--cleanup", action="store_true", help="Remove all mock data and restore backups.")
    
    args = parser.parse_args()
    sb = get_supabase()
    
    if args.cleanup:
        cleanup_mock_data(sb)
    elif args.scenario:
        # Pulisce sempre i residui prima di applicare uno scenario
        if os.path.exists(BACKUP_FILE) or len(sb.table("activities").select("id").like("external_id", f"{MOCK_TAG}%").execute().data) > 0:
            logger.info("Found existing mock data. Cleaning up before applying new scenario...")
            cleanup_mock_data(sb)
            
        if args.scenario == 1:
            apply_scenario_1(sb)
        elif args.scenario == 2:
            apply_scenario_2(sb)
        elif args.scenario == 3:
            apply_scenario_3(sb)
        elif args.scenario == 4:
            apply_scenario_4(sb)
        elif args.scenario == 5:
            apply_scenario_5(sb)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
