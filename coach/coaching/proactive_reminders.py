"""Fase 1.6 — Proactive Telegram reminders.

Il sistema invita l'atleta ad aprire Claude.ai per le azioni che richiedono
human-in-the-loop (weekly review, mesocycle generation, race briefing, ecc.).

Architettura:
- Ogni trigger è una funzione `_check_<name>(today, sb)` che ritorna:
    None: nessun reminder
    dict: {trigger_type, text, context}
- Il main loop applica tutti i trigger, deduplica via `sent_reminders` table
  (unique constraint su trigger_type + sent_date), invia Telegram, logga.

Tutti i trigger sono **rule-based** (zero LLM). Il testo del reminder è
templatizzato per coerenza, ma può essere arricchito via Gemini se necessario
(es. contextualizzazione con dati biometrici recenti).

Cron: ogni 30 min via .github/workflows/proactive-reminders.yml
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional, Callable
from zoneinfo import ZoneInfo

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

ROME_TZ = ZoneInfo("Europe/Rome")


# ============================================================================
# Triggers (ogni funzione ritorna dict o None)
# ============================================================================

def _check_weekly_review(now: datetime, sb, ignore_time_window: bool = False) -> Optional[dict]:
    """Domenica tra 18:00 e 19:30 (Europe/Rome): reminder weekly review."""
    if not ignore_time_window:
        if now.weekday() != 6:  # 6 = sunday
            return None
        if not (time(18, 0) <= now.time() <= time(19, 30)):
            return None
    return {
        "trigger_type": "weekly_review",
        "text": (
            "📋 <b>Weekly review</b>\n\n"
            "È domenica — apri Claude.ai e digita:\n"
            "<code>fai la weekly review</code>\n\n"
            "Il sistema raccoglie tutti i dati settimana e propone il piano successivo. "
            "Ti basta confermare con 'ok'."
        ),
        "context": {},
    }


def _check_open_modulations(now: datetime, sb, ignore_time_window: bool = False) -> Optional[dict]:
    """Mercoledì o sabato mattina: se ci sono modulazioni in attesa, ricorda di rivederle."""
    if not ignore_time_window:
        if now.weekday() not in (2, 5):  # mer, sab
            return None
        if not (time(8, 30) <= now.time() <= time(10, 0)):
            return None
    res = sb.table("plan_modulations").select("id").eq("status", "proposed").execute()
    n = len(res.data or [])
    if n == 0:
        return None
    return {
        "trigger_type": "open_modulations",
        "text": (
            f"⚡ <b>{n} modulazion{'i' if n > 1 else 'e'} in attesa</b>\n\n"
            f"Apri Claude.ai per rivederle:\n"
            f"<code>mostra le modulazioni aperte</code>\n\n"
            f"Approva o rifiuta direttamente da qui con i bottoni del messaggio originale, "
            f"oppure discutile col coach in chat."
        ),
        "context": {"count": n},
    }


def _check_mesocycle_ending(now: datetime, sb, ignore_time_window: bool = False) -> Optional[dict]:
    """7gg prima della fine del mesociclo corrente: ricorda di pianificare il prossimo.

    Nota: questo trigger è già state-based (cerca mesocycle in scadenza), nessun
    time check da bypassare. ignore_time_window è accettato per uniformità.
    """
    today = now.date()
    target = today + timedelta(days=7)
    res = (
        sb.table("mesocycles")
        .select("id,name,phase,end_date")
        .gte("end_date", today.isoformat())
        .lte("end_date", target.isoformat())
        .order("end_date", desc=False)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    m = res.data[0]
    days_left = (date.fromisoformat(m["end_date"]) - today).days
    return {
        "trigger_type": "mesocycle_ending",
        "text": (
            f"🔄 <b>Mesociclo in chiusura</b>\n\n"
            f"Il mesociclo <i>{m['name']}</i> (fase {m['phase']}) finisce tra {days_left}gg.\n\n"
            f"Apri Claude.ai e pianifica il prossimo:\n"
            f"<code>proponi il prossimo mesociclo</code>"
        ),
        "context": {"mesocycle_id": m["id"], "days_left": days_left},
    }


def _check_weekly_plan_empty(now: datetime, sb, ignore_time_window: bool = False) -> Optional[dict]:
    """Lunedì mattina: se la settimana corrente ha < 3 planned_sessions, il commit
    della weekly review di domenica è probabilmente fallito. Notifica.

    Safety net contro il bug "weekly review non scrive su calendario".
    """
    if not ignore_time_window:
        if now.weekday() != 0:  # lun
            return None
        if not (time(7, 0) <= now.time() <= time(11, 0)):
            return None
    today = now.date()
    sunday = today + timedelta(days=6)
    res = (
        sb.table("planned_sessions")
        .select("id,planned_date")
        .gte("planned_date", today.isoformat())
        .lte("planned_date", sunday.isoformat())
        .execute()
    )
    n = len(res.data or [])
    if n >= 3:
        return None
    return {
        "trigger_type": "weekly_plan_empty",
        "text": (
            f"⚠️ <b>Settimana corrente: solo {n} sessioni pianificate</b>\n\n"
            f"La weekly review di domenica potrebbe non aver committato tutto. "
            f"Apri Claude.ai e digita:\n"
            f"<code>verifica e completa il piano della settimana</code>\n\n"
            f"In alternativa: <code>fai la weekly review</code> per riproporlo da zero."
        ),
        "context": {"sessions_found": n, "week_start": today.isoformat()},
    }


def _check_test_due(now: datetime, sb, ignore_time_window: bool = False) -> Optional[dict]:
    """Ogni lunedì: se l'ultimo test fitness > 42gg, ricorda di pianificarlo."""
    if not ignore_time_window:
        if now.weekday() != 0:  # lun
            return None
        if not (time(9, 0) <= now.time() <= time(11, 0)):
            return None
    res = (
        sb.table("physiology_zones")
        .select("discipline,valid_from")
        .is_("valid_to", "null")
        .order("valid_from", desc=True)
        .execute()
    )
    if not res.data:
        # Nessuna zone mai inserita — promemoria per primo test
        return {
            "trigger_type": "test_due",
            "text": (
                "🧪 <b>Test fitness mai eseguito</b>\n\n"
                "Non ci sono zone fisiologiche nel sistema. Apri Claude.ai:\n"
                "<code>pianifica il primo test FTP</code>"
            ),
            "context": {"reason": "no_zones"},
        }
    today = now.date()
    overdue = []
    for row in res.data:
        try:
            days_since = (today - date.fromisoformat(row["valid_from"])).days
            if days_since > 42:
                overdue.append({"discipline": row["discipline"], "days": days_since})
        except Exception:
            continue
    if not overdue:
        return None
    disciplines = ", ".join(f"{o['discipline']} ({o['days']}gg)" for o in overdue)
    return {
        "trigger_type": "test_due",
        "text": (
            f"🧪 <b>Test fitness da rifare</b>\n\n"
            f"Discipline con ultimo test > 6 settimane: {disciplines}\n\n"
            f"Apri Claude.ai:\n"
            f"<code>pianifica il prossimo test FTP</code>"
        ),
        "context": {"overdue": overdue},
    }


def _check_race_proximity(now: datetime, sb, ignore_time_window: bool = False) -> list[dict]:
    """Per ogni gara A/B futura, controlla soglie T-14, T-7, T-2, T+1.

    Se ignore_time_window=True, espande la finestra a tutte le gare entro 120gg
    e produce un reminder generico per testare il flusso.
    """
    today = now.date()
    triggers = []
    horizon_days = 120 if ignore_time_window else 20
    res = (
        sb.table("races")
        .select("id,name,race_date,priority,distance")
        .gte("race_date", (today - timedelta(days=2)).isoformat())
        .lte("race_date", (today + timedelta(days=horizon_days)).isoformat())
        .in_("priority", ["A", "B"])
        .execute()
    )
    if ignore_time_window:
        # Modalità test: 1 reminder generico per ogni gara futura entro 120gg
        for race in res.data or []:
            race_date = date.fromisoformat(race["race_date"])
            days = (race_date - today).days
            triggers.append({
                "trigger_type": f"race_test_{race['id']}",
                "text": (
                    f"🧪 <b>[TEST] Race proximity reminder</b>\n\n"
                    f"Gara <b>{race['name']}</b> ({race['priority']}) tra {days}gg "
                    f"({race['race_date']}).\n\n"
                    f"In produzione, scatteranno reminder a T-14, T-7, T-2, T+1."
                ),
                "context": {"race_id": race["id"], "days": days, "test_mode": True},
            })
        return triggers
    for race in res.data or []:
        race_date = date.fromisoformat(race["race_date"])
        days = (race_date - today).days
        race_name = race["name"]
        if days == 14:
            triggers.append({
                "trigger_type": f"race_t14_{race['id']}",
                "text": (
                    f"🏁 <b>Race week T-14: {race_name}</b>\n\n"
                    f"Mancano 2 settimane. Apri Claude.ai:\n"
                    f"<code>race briefing per {race_name}</code>\n\n"
                    f"Inizia a pianificare logistica, materiale, nutrition."
                ),
                "context": {"race_id": race["id"], "days": days},
            })
        elif days == 7:
            triggers.append({
                "trigger_type": f"race_t7_{race['id']}",
                "text": (
                    f"🏁 <b>Race week T-7: {race_name}</b>\n\n"
                    f"Inizio taper. Apri Claude.ai:\n"
                    f"<code>attiva race week protocol</code>\n\n"
                    f"Il sistema entra in modalità race week."
                ),
                "context": {"race_id": race["id"], "days": days},
            })
        elif days == 2:
            triggers.append({
                "trigger_type": f"race_t2_{race['id']}",
                "text": (
                    f"🎯 <b>T-2: {race_name}</b>\n\n"
                    f"Apri Claude.ai per il briefing tattico:\n"
                    f"<code>preparami il briefing gara</code>\n\n"
                    f"Checklist materiale, pacing, nutrition testata, mental prep."
                ),
                "context": {"race_id": race["id"], "days": days},
            })
        elif days == -1:
            triggers.append({
                "trigger_type": f"race_t_plus1_{race['id']}",
                "text": (
                    f"🏆 <b>Race + 1: {race_name}</b>\n\n"
                    f"Apri Claude.ai per l'analisi post-gara:\n"
                    f"<code>analisi post-gara di {race_name}</code>\n\n"
                    f"Serve: tempo finale, splits, sensazioni, cosa rifaresti e cosa no. "
                    f"Il sistema calibra le predizioni future sui dati reali."
                ),
                "context": {"race_id": race["id"], "days": days},
            })
    return triggers


def _check_peak_mesocycle_missing(now: datetime, sb, ignore_time_window: bool = False) -> list[dict]:
    """30gg prima race A: se non esiste mesociclo peak nel range race-30 → race, warning.

    Se ignore_time_window=True, controlla anche gare oltre i 35gg (test).
    """
    today = now.date()
    triggers = []
    res = (
        sb.table("races")
        .select("id,name,race_date")
        .gte("race_date", (today + timedelta(days=28)).isoformat())
        .lte("race_date", (today + timedelta(days=35)).isoformat())
        .eq("priority", "A")
        .execute()
    )
    for race in res.data or []:
        race_date = date.fromisoformat(race["race_date"])
        # Cerca mesociclo peak nei prossimi 30gg
        peak_res = (
            sb.table("mesocycles")
            .select("id")
            .eq("phase", "peak")
            .lte("start_date", race_date.isoformat())
            .gte("end_date", today.isoformat())
            .execute()
        )
        if peak_res.data:
            continue
        triggers.append({
            "trigger_type": f"peak_missing_{race['id']}",
            "text": (
                f"⚠️ <b>Manca 1 mese a {race['name']}</b>\n\n"
                f"Non c'è un mesociclo peak pianificato. Apri Claude.ai:\n"
                f"<code>pianifica mesociclo peak verso {race['name']}</code>"
            ),
            "context": {"race_id": race["id"]},
        })
    return triggers


# ============================================================================
# Main loop
# ============================================================================

TRIGGERS_SINGLE: list[Callable[[datetime, object], Optional[dict]]] = [
    _check_weekly_review,
    _check_open_modulations,
    _check_mesocycle_ending,
    _check_test_due,
    _check_weekly_plan_empty,
]

TRIGGERS_MULTI: list[Callable[[datetime, object], list[dict]]] = [
    _check_race_proximity,
    _check_peak_mesocycle_missing,
]


def _already_sent_today(sb, trigger_type: str, sent_date: str) -> bool:
    res = (
        sb.table("sent_reminders")
        .select("id")
        .eq("trigger_type", trigger_type)
        .eq("sent_date", sent_date)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _log_sent(sb, trigger_type: str, sent_date: str, message_id: Optional[int], context: dict) -> None:
    sb.table("sent_reminders").insert({
        "trigger_type": trigger_type,
        "sent_date": sent_date,
        "message_id": message_id,
        "context": context,
    }).execute()


def run_proactive_reminders(
    ignore_time_window: bool = False,
    dry_run: bool = False,
    skip_dedup: bool = False,
) -> int:
    """Esegue tutti i trigger, invia i nuovi reminder, deduplica via sent_reminders.

    Args:
        ignore_time_window: se True bypassa i check giorno/ora dei trigger (test).
        dry_run: se True stampa cosa farebbe senza inviare/loggare nulla.
        skip_dedup: se True ignora sent_reminders table (test, manda anche se già fatto).

    Returns:
        Numero di reminder inviati (o che sarebbero inviati se dry_run=True).
    """
    sb = get_supabase()
    now = datetime.now(ROME_TZ)
    today_iso = today_rome().isoformat()
    sent = 0

    # Housekeeping: scadi le modulazioni 'proposed' troppo vecchie (mai accettate/
    # rifiutate) o che propongono modifiche per date già passate. Tiene pulito
    # get_weekly_context ed evita reminder ripetuti su proposte obsolete
    # (BUG-011 follow-up). expire_past_modulations prima girava solo come side
    # effect di una NUOVA proposta: senza trigger critici nel frattempo, una
    # modulazione per una data già passata restava "aperta" fino a
    # STALE_MODULATION_DAYS (4gg) invece di sparire appena la data passa.
    if not dry_run:
        try:
            from coach.coaching.modulation import expire_stale_modulations, expire_past_modulations
            expire_past_modulations()
            expire_stale_modulations()
        except Exception:
            logger.exception("expire_stale_modulations failed")

    if ignore_time_window:
        logger.warning("⚠️  IGNORE_TIME_WINDOW attivo — modalità TEST")
    if dry_run:
        logger.warning("⚠️  DRY_RUN attivo — nessun messaggio verrà effettivamente inviato")

    candidates: list[dict] = []
    for fn in TRIGGERS_SINGLE:
        try:
            r = fn(now, sb, ignore_time_window=ignore_time_window)
            if r:
                candidates.append(r)
        except Exception:
            logger.exception("Trigger %s failed", fn.__name__)
    for fn in TRIGGERS_MULTI:
        try:
            rs = fn(now, sb, ignore_time_window=ignore_time_window)
            candidates.extend(rs or [])
        except Exception:
            logger.exception("Trigger %s failed", fn.__name__)

    logger.info("Trigger candidates: %d", len(candidates))
    for c in candidates:
        logger.info("  candidate: %s", c["trigger_type"])

    for r in candidates:
        trigger_type = r["trigger_type"]
        if not skip_dedup and _already_sent_today(sb, trigger_type, today_iso):
            logger.info("Skip duplicate reminder: %s on %s", trigger_type, today_iso)
            continue

        if dry_run:
            logger.info("[DRY-RUN] Would send: %s\n%s", trigger_type, r["text"][:200])
            sent += 1
            continue

        # Bug fix audit F1/F2: CLAIM-before-send. Inseriamo la riga dedup PRIMA
        # di inviare; un conflitto sull'indice unique (trigger_type, sent_date)
        # significa "già inviato oggi" → skip. Così:
        #  - se il logging fallisse DOPO l'invio non avremmo re-invio (era F1);
        #  - due run concorrenti non inviano due volte (era F2).
        if not skip_dedup:
            try:
                _log_sent(sb, trigger_type, today_iso, None, r.get("context", {}))
            except Exception:
                logger.info("Skip reminder (già inviato/claim fallito): %s", trigger_type)
                continue

        try:
            from coach.utils.telegram_logger import send_and_log_message
            # send_and_log_message ritorna message_id (int) o None — NON un dict.
            msg_id = send_and_log_message(
                r["text"],
                purpose="proactive_reminder",
                context_data={"trigger_type": trigger_type, **r.get("context", {})},
            )
            sent += 1
            logger.info("Sent reminder: %s", trigger_type)
            # aggiorna il message_id sulla riga claimata (best effort)
            if not skip_dedup and isinstance(msg_id, int):
                try:
                    sb.table("sent_reminders").update({"message_id": msg_id}).eq(
                        "trigger_type", trigger_type
                    ).eq("sent_date", today_iso).execute()
                except Exception:
                    logger.warning("Impossibile aggiornare message_id per %s", trigger_type)
        except Exception:
            logger.exception("Failed to send reminder %s", trigger_type)

    return sent


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--ignore-time-window", action="store_true",
                   help="Bypass time checks (test all triggers regardless of day/hour)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be sent without actually sending or logging")
    p.add_argument("--skip-dedup", action="store_true",
                   help="Ignore sent_reminders table (force re-send)")
    args = p.parse_args()

    # Env var override (used by GitHub Actions workflow_dispatch input)
    import os
    ignore = args.ignore_time_window or os.environ.get("IGNORE_TIME_WINDOW", "").lower() in ("true", "1", "yes")
    dry = args.dry_run or os.environ.get("DRY_RUN", "").lower() in ("true", "1", "yes")
    skip_dedup = args.skip_dedup or os.environ.get("SKIP_DEDUP", "").lower() in ("true", "1", "yes")

    from coach.utils.health import record_health
    try:
        n = run_proactive_reminders(ignore_time_window=ignore, dry_run=dry, skip_dedup=skip_dedup)
    except Exception as e:  # noqa: BLE001
        record_health("proactive_reminders", success=False, error=str(e))
        raise
    logger.info("Proactive reminders run: %d %s", n, "would-be-sent" if dry else "sent")
    if not dry:
        record_health("proactive_reminders", success=True, metadata={"sent": n})


if __name__ == "__main__":
    main()
