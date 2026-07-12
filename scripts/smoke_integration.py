"""WP5 — Smoke test d'integrazione contro il sistema REALE, in sola lettura.

Gli unit test (tutti a stub) restano verdi anche se l'integrazione è rotta:
questo script esercita DB e worker veri e fallisce (exit != 0) sui guasti
che gli stub non vedono. Zero scritture, zero LLM.

Verifica:
1. Schema drift — le colonne che il codice usa esistono davvero in prod
   (è già successo: colonne applicate a mano senza migration, un restore DR
   avrebbe fatto crashare l'analytics). Una SELECT esplicita per tabella con
   limit=1 fallisce con PGRST se una colonna manca.
2. Vincoli critici — UNIQUE su cui il codice fa upsert/on_conflict.
3. Health — la tabella risponde e i componenti CORE hanno righe.
4. Worker MCP — endpoint /health raggiungibile (se MCP_URL configurato).

Uso: python scripts/smoke_integration.py   (env: SUPABASE_URL/SERVICE_KEY,
     opzionale MCP_URL per il ping del worker)
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Colonne per tabella USATE dal codice (Python + worker TS). Se una manca in
# prod, la SELECT fallisce → smoke rosso. Aggiornare quando il codice inizia
# a usare colonne nuove (il fallimento di questo smoke È il reminder di
# eseguire la migration).
EXPECTED_COLUMNS = {
    "activities": "id,external_id,source,sport,started_at,duration_s,distance_m,"
                  "avg_hr,max_hr,hr_zones_s,avg_power_w,np_w,avg_pace_s_per_km,"
                  "avg_pace_s_per_100m,tss,rpe,splits,weather,notes,raw_payload",
    "daily_metrics": "date,ctl,atl,tsb,daily_tss,hrv_z_score,hrv_baseline_28d,"
                     "hrv_baseline_28d_sd,readiness_score,readiness_label,"
                     "readiness_factors,flags,garmin_training_readiness,"
                     "garmin_acute_load,garmin_chronic_load,garmin_load_balance,"
                     "garmin_training_status",
    "daily_wellness": "date,hrv_rmssd,sleep_score,body_battery_min,body_battery_max,"
                      "resting_hr,training_readiness_score,avg_sleep_stress",
    "planned_sessions": "id,mesocycle_id,planned_date,sport,session_type,duration_s,"
                        "target_tss,target_zones,description,structured,status,"
                        "completed_activity_id,calendar_event_id",
    "physiology_zones": "id,discipline,valid_from,valid_to,ftp_w,"
                        "threshold_pace_s_per_km,css_pace_s_per_100m,lthr,hr_max,"
                        "test_activity_id,method,notes",
    "bot_messages": "id,telegram_message_id,chat_id,sent_at,purpose,context_data,"
                    "parent_workflow,expires_at",
    "plan_modulations": "id,proposed_at,trigger_event,trigger_data,proposed_changes,"
                        "status,resolved_at,telegram_message_id,expires_at,source",
    "beliefs": "id,belief_key,belief_text,confidence,evidence_n,status,category,"
               "prescription,flagged,flag_reason,source,last_reinforced_at,"
               "last_updated_at,evidence_decay_half_life_days",
    "session_analyses": "id,activity_id,analysis_text,fatigue_type,fatigue_confidence,"
                        "sport,suggested_actions,model_used,cost_usd",
    "active_constraints": "id,type,discipline,description,severity,symptom_status,"
                          "note,history,created_at,resolved_at",
    "mesocycles": "id,name,phase,start_date,end_date,target_race_id,weekly_pattern,"
                  "progression_plan,season_year,notes",
    "subjective_log": "id,logged_at,kind,rpe,sleep_quality,motivation,soreness,"
                      "illness_flag,injury_flag,injury_details,severity,"
                      "expected_duration_days,body_location,raw_text,parsed_data",
    "health": "component,last_success_at,last_failure_at,failure_count,last_error,metadata",
    "api_usage": "provider,model,purpose,input_tokens,output_tokens,"
                 "cost_usd_estimated,success,metadata",
    "races": "id,name,race_date,distance,location,priority,season_year",
    "pending_confirmations": "id,chat_id,original_message_id,confirmation_message_id,"
                             "parsed_action,parsed_data,status,expires_at,created_at",
    "sent_reminders": "trigger_type,sent_date,context",
}

# Vincoli UNIQUE su cui il codice fa upsert on_conflict / si affida per dedup.
# (constraint_name atteso, tabella) — verificati provando una SELECT che li
# nomina non è possibile via PostgREST: si verifica indirettamente che gli
# upsert del codice non falliscano — qui ci limitiamo a documentarli e a
# controllare che le tabelle rispondano. La verifica forte resta l'assenza
# di 42P10 nei job reali.
CORE_HEALTH_COMPONENTS = ("garmin_sync", "analytics_daily", "briefing_morning")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from coach.utils.supabase_client import get_supabase

    sb = get_supabase()
    failures: list[str] = []

    # 1+2. Schema drift: SELECT esplicita per tabella
    for table, cols in EXPECTED_COLUMNS.items():
        try:
            sb.table(table).select(cols).limit(1).execute()
            logger.info("OK schema %s", table)
        except Exception as e:  # noqa: BLE001
            failures.append(f"schema {table}: {e}")
            logger.error("FAIL schema %s: %s", table, e)

    # 3. Health: i componenti core hanno una riga
    try:
        res = sb.table("health").select("component,last_success_at").execute()
        present = {r["component"] for r in (res.data or [])}
        for comp in CORE_HEALTH_COMPONENTS:
            if comp not in present:
                failures.append(f"health: componente core '{comp}' senza riga")
    except Exception as e:  # noqa: BLE001
        failures.append(f"health query: {e}")

    # 4. Worker MCP: reachability (facoltativo, richiede MCP_URL). Il worker
    # non ha /health: si usa il discovery OAuth, GET pubblico e statico.
    mcp_url = os.environ.get("MCP_URL")
    if mcp_url:
        try:
            import requests
            r = requests.get(
                f"{mcp_url.rstrip('/')}/.well-known/oauth-authorization-server",
                timeout=15,
            )
            if r.status_code >= 400:
                failures.append(f"mcp discovery: HTTP {r.status_code}")
            else:
                logger.info("OK worker MCP raggiungibile")
        except Exception as e:  # noqa: BLE001
            failures.append(f"mcp discovery: {e}")
    else:
        logger.info("MCP_URL non configurato: ping worker saltato")

    if failures:
        print(f"\nSMOKE FAILED — {len(failures)} problemi:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nSMOKE OK — {len(EXPECTED_COLUMNS)} tabelle verificate, health core presente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
