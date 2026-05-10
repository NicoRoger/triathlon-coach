"""Smoke test: verifica connettività e configurazione di base.

Esegui dopo setup iniziale (Step 11 di SETUP.md). Tutti gli step devono passare.
"""
from __future__ import annotations

import os
import sys

import requests

CHECKS = []


def check(name: str):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("Env vars")
def check_env():
    required = [
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"Mancanti: {missing}")


@check("Supabase ping")
def check_supabase():
    from coach.utils.supabase_client import get_supabase
    sb = get_supabase()
    res = sb.table("health").select("component").limit(1).execute()
    if not res.data:
        raise RuntimeError("health table vuota — applicare schema.sql?")
        
    res_api = sb.table("api_usage").select("id").limit(1).execute()
    res_sa = sb.table("session_analyses").select("id").limit(1).execute()
    res_pm = sb.table("plan_modulations").select("id").limit(1).execute()
    res_ps = sb.table("planned_sessions").select("id").limit(1).execute()
    res_dw = sb.table("daily_wellness").select("date").limit(1).execute()
    res_dm = sb.table("daily_metrics").select("date").limit(1).execute()
    res_sl = sb.table("subjective_log").select("id").limit(1).execute()


@check("Telegram bot reachable")
def check_telegram():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    resp.raise_for_status()
    if not resp.json().get("ok"):
        raise RuntimeError("Telegram getMe failed")


@check("Telegram send")
def check_send():
    from coach.planning.briefing import send_to_telegram
    send_to_telegram("🧪 <b>Smoke test</b> — sistema operativo")


@check("Garmin secret present")
def check_garmin_secret():
    if not os.environ.get("GARMIN_SESSION_JSON"):
        raise RuntimeError("GARMIN_SESSION_JSON non settato")


@check("Strava secret present")
def check_strava_secret():
    for v in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"):
        if not os.environ.get(v):
            raise RuntimeError(f"{v} non settato")

@check("Budget under limits")
def check_budget():
    from coach.utils.budget import get_month_spend_usd, BUDGET_HARD_CAP
    spend = get_month_spend_usd()
    if spend > BUDGET_HARD_CAP:
        raise RuntimeError(f"Budget superato: ${spend}/${BUDGET_HARD_CAP}")

@check("Health freshness")
def check_health():
    from coach.utils.supabase_client import get_supabase
    from datetime import datetime, timezone
    sb = get_supabase()
    res = sb.table("health").select("*").execute()
    now = datetime.now(timezone.utc)
    
    thresholds = {
        "garmin_sync": 12,
        "briefing_morning": 30,
        "analytics_daily": 12,
        "dr_snapshot": 36,
    }
    
    for row in res.data or []:
        comp = row["component"]
        thr = thresholds.get(comp)
        if thr and row.get("last_success_at"):
            last = datetime.fromisoformat(row["last_success_at"].replace("Z", "+00:00"))
            age = (now - last).total_seconds() / 3600
            if age > thr:
                raise RuntimeError(f"{comp} troppo vecchio: {age:.1f}h")


def main() -> int:
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"✅ {name}")
        except Exception as e:  # noqa: BLE001
            print(f"❌ {name}: {e}")
            failed += 1
    print()
    if failed:
        print(f"FAIL: {failed}/{len(CHECKS)}")
        return 1
    print(f"OK: {len(CHECKS)}/{len(CHECKS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
