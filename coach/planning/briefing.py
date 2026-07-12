"""Briefing v2 — versione narrativa comprensibile.

Cambiamenti vs v1:
- Italiano naturale, niente sigle non spiegate
- Interpretazione esplicita di ogni numero
- Usa Garmin training load (acute/chronic) ora che è popolato
- Sezione "cosa fare oggi" + "watch-out specifici"
- Stratificato per dati disponibili (skip sezioni se dati assenti)

Costo runtime: 0 chiamate LLM, tutto rule-based.
"""
from __future__ import annotations


import logging
import os
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import requests

from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health
from coach.utils.dt import today_rome
from coach.utils.purposes import ENERGY_UPDATE, MORNING_BRIEF

logger = logging.getLogger(__name__)

FRESHNESS_HOURS = 18


# ============================================================================
# Interpretazioni hardcoded
# ============================================================================

def _interpret_sleep(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    if score >= 85:
        return f"{score}/100 — ottimo"
    if score >= 70:
        return f"{score}/100 — buono"
    if score >= 50:
        return f"{score}/100 — discreto"
    return f"{score}/100 — scarso, considera scarico"


def _interpret_hrv(z: Optional[float]) -> Optional[str]:
    if z is None:
        return None
    if z > 1:
        return f"+{z:.1f}σ — sopra la tua media, freschezza alta"
    if z >= -0.5:
        return f"{z:+.1f}σ — nella tua norma"
    if z >= -1:
        return f"{z:.1f}σ — leggermente bassa"
    if z >= -2:
        return f"{z:.1f}σ — bassa, segnale di affaticamento"
    return f"{z:.1f}σ — molto bassa, oggi recupero"


def _interpret_body_battery(bb: Optional[int]) -> Optional[str]:
    if bb is None:
        return None
    if bb >= 75:
        return f"{bb}/100 — alta"
    if bb >= 50:
        return f"{bb}/100 — media"
    return f"{bb}/100 — bassa"


def _interpret_acwr(acute: Optional[float], chronic: Optional[float]) -> tuple[Optional[float], Optional[str]]:
    """Restituisce (ratio, interpretazione)."""
    if acute is None or chronic is None or chronic == 0:
        return None, None
    ratio = acute / chronic
    if ratio < 0.8:
        return ratio, "decarica (carico recente sotto la fitness)"
    if ratio <= 1.3:
        return ratio, "zona allenante ottimale"
    if ratio <= 1.5:
        return ratio, "alto, monitorare"
    return ratio, "rischio infortunio (sopra 1.5 = soglia Gabbett)"


def _interpret_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    map_ita = {
        "productive": "fase produttiva",
        "peaking": "vicino al picco di forma",
        "maintaining": "mantenimento",
        "recovery": "in recupero",
        "unproductive": "carico non sta producendo adattamenti",
        "strained": "carico molto alto, sotto stress",
        "overreaching": "troppo carico, rischio overtraining",
        "detraining": "perdita di fitness",
        "no_recent_load": "poco carico recente",
        "no_status": "dati insufficienti",
    }
    return map_ita.get(status, status)


# ============================================================================
# Sezioni del brief
# ============================================================================

def _build_header(d: date) -> str:
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"<b>🏊 Brief {giorni[d.weekday()]} {d.day} {mesi[d.month-1]}</b>"


def _build_freshness_warning(age_hours: Optional[float]) -> str:
    if age_hours is not None and age_hours > FRESHNESS_HOURS:
        return f"⚠️ <i>Ultimo sync Garmin {age_hours:.0f}h fa — valutazione parziale.</i>\n"
    return ""


def _build_wellness_section(wellness: dict, metrics: dict) -> str:
    """Sonno/HRV nel brief delle 5:00. Body Battery e readiness Garmin NON
    stanno qui: alle 5 il sonno è ancora in corso, la notifica stessa lo
    interrompe e Body Battery/readiness escono artificialmente bassi. Vanno
    in _build_energy_section, mandata più tardi (vedi build_energy_update)."""
    lines = []
    sleep_str = _interpret_sleep(wellness.get("sleep_score"))
    hrv_str = _interpret_hrv(metrics.get("hrv_z_score"))

    if not any([sleep_str, hrv_str]):
        return ""

    lines.append("<b>📊 Come stai oggi</b>")
    if sleep_str:
        lines.append(f"Sonno stanotte: {sleep_str}")
    if hrv_str:
        lines.append(f"HRV: {hrv_str}")

    return "\n".join(lines)


def _build_energy_section(wellness: dict, metrics: dict) -> str:
    """Body Battery + readiness Garmin — separati dal brief delle 5:00 perché
    la notifica di quell'ora interrompe il sonno e falsa entrambi i valori
    (letti bassi non per stanchezza reale ma per il risveglio forzato)."""
    lines = []
    bb_str = _interpret_body_battery(wellness.get("body_battery_max"))
    if bb_str:
        lines.append(f"Energia al risveglio: {bb_str}")

    # CLAUDE.md §12: discrepanza >15 tra il nostro readiness e Garmin = segnale
    our_r = metrics.get("readiness_score")
    garmin_r = metrics.get("garmin_training_readiness") or wellness.get("training_readiness_score")
    if our_r is not None and garmin_r is not None:
        diff = abs(int(our_r) - int(garmin_r))
        if diff > 15:
            if our_r > garmin_r:
                note = "Garmin è più pessimista — possibile carico recente sottostimato"
            else:
                note = "Garmin è più ottimista — considera il nostro score come più prudente"
            lines.append(
                f"⚠️ <i>Readiness: noi {our_r} vs Garmin {garmin_r} (Δ{diff}) — {note}.</i>"
            )

    if not lines:
        return ""
    return "<b>🔋 Energia</b>\n" + "\n".join(lines)


def _build_load_section(metrics: dict) -> str:
    acute = metrics.get("garmin_acute_load")
    chronic = metrics.get("garmin_chronic_load")
    status = metrics.get("garmin_training_status")

    if acute is None and chronic is None and status is None:
        return ""

    lines = ["<b>📈 Carico (secondo Garmin)</b>"]
    if acute is not None:
        lines.append(f"Acute load: {acute:.0f} (carico recente, ultimi 7gg)")
    if chronic is not None:
        lines.append(f"Chronic load: {chronic:.0f} (la tua fitness, ultimi 28gg)")

    ratio, ratio_interp = _interpret_acwr(acute, chronic)
    if ratio is not None:
        lines.append(f"Rapporto acute/chronic: {ratio:.2f} → {ratio_interp}")

    status_interp = _interpret_status(status)
    if status_interp:
        lines.append(f"Stato Garmin: {status_interp}")

    return "\n".join(lines)


def _format_target_zones(zones) -> Optional[str]:
    """Rende target_zones (dict {'z2':0.7,...}) in una riga leggibile."""
    if not isinstance(zones, dict) or not zones:
        return None
    parts = []
    for z, frac in zones.items():
        try:
            pct = round(float(frac) * 100)
        except (TypeError, ValueError):
            continue
        parts.append(f"{str(z).upper()} {pct}%")
    return " · ".join(parts) if parts else None


def _format_structured(structured) -> list[str]:
    """Rende un workout strutturato (lista di step o dict) in righe leggibili.
    Best-effort: tollera formati diversi senza crashare."""
    from html import escape as _esc
    out: list[str] = []
    steps = None
    if isinstance(structured, dict):
        steps = structured.get("steps") or structured.get("intervals") or structured.get("workout")
    elif isinstance(structured, list):
        steps = structured
    if not isinstance(steps, list):
        return out
    for s in steps:
        if isinstance(s, dict):
            # campi tipici: name/label, reps, duration_s/duration, zone/target, notes
            label = s.get("name") or s.get("label") or s.get("type") or "step"
            reps = s.get("reps")
            dur = s.get("duration_s") or s.get("duration")
            zone = s.get("zone") or s.get("target") or s.get("intensity")
            bits = [str(label)]
            if reps:
                bits.append(f"x{reps}")
            if dur:
                try:
                    bits.append(f"{int(dur) // 60}min" if int(dur) >= 60 else f"{int(dur)}s")
                except (TypeError, ValueError):
                    pass
            if zone:
                bits.append(str(zone))
            out.append("  • " + _esc(" · ".join(bits)))
        else:
            out.append("  • " + _esc(str(s)))
    return out


def _fetch_current_zones(sb) -> dict:
    """Legge l'ultima riga physiology_zones per disciplina (valid_to is null).

    Ritorna un dict {discipline: row_dict}. Degrada a {} su errore — non deve
    mai far crashare il brief (pattern identico a _build_race_progress_section).
    """
    try:
        res = (
            sb.table("physiology_zones")
            .select("discipline,ftp_w,threshold_pace_s_per_km,css_pace_s_per_100m,lthr,valid_from")
            .is_("valid_to", "null")
            .order("valid_from", desc=True)
            .execute()
        )
        rows = res.data or []
        zones_by_discipline: dict = {}
        for row in rows:
            disc = row.get("discipline")
            # Tieni solo la riga piu' recente per disciplina
            if disc and disc not in zones_by_discipline:
                zones_by_discipline[disc] = row
        return zones_by_discipline
    except Exception:
        logger.warning("_fetch_current_zones: impossibile leggere physiology_zones", exc_info=True)
        return {}


def _format_session_zones(sport: str, zones_by_discipline: dict) -> Optional[str]:
    """Formatta una riga compatta con le zone misurate per la disciplina della sessione.

    Placeholder esplicito per bici se FTP mancante (D-11). Ritorna None se nessun
    dato disponibile per lo sport richiesto.
    """
    from coach.coaching.fitness_test_processor import derive_zones_for_discipline

    # Mappa brick → run (la parte corsa e' quella con pace zone)
    disc_map = {"swim": "swim", "bike": "bike", "run": "run", "brick": "run"}
    discipline = disc_map.get(sport)
    if discipline is None:
        return None

    row = zones_by_discipline.get(discipline)

    # Bici: atleta SENZA wattmetro → zone da LTHR (HR). FTP solo se presente.
    if discipline == "bike":
        ftp = row.get("ftp_w") if row else None
        lthr = row.get("lthr") if row else None
        if ftp:
            zones = derive_zones_for_discipline("bike", ftp_w=float(ftp))
            z2, z4 = zones.get("Z2_endurance", ""), zones.get("Z4_threshold", "")
        elif lthr:
            zones = derive_zones_for_discipline("bike", lthr=float(lthr))
            z2, z4 = zones.get("Z2_aerobic", ""), zones.get("Z4_threshold", "")
        else:
            return "[zone bici non misurate — fai un test soglia HR 20']"
        parts = []
        if z2:
            parts.append(f"Z2: {z2}")
        if z4:
            parts.append(f"Z4: {z4}")
        suffix = "" if ftp else " (HR, no wattmetro)"
        return (" | ".join(parts) + suffix) if parts else None

    if row is None:
        return None

    if discipline == "run":
        tp = row.get("threshold_pace_s_per_km")
        if not tp:
            return None
        zones = derive_zones_for_discipline("run", threshold_pace_s_per_km=float(tp))
        z2 = zones.get("Z2_endurance", "")
        z4 = zones.get("Z4_threshold", "")
        parts = []
        if z2:
            parts.append(f"Z2: {z2}")
        if z4:
            parts.append(f"Z4: {z4}")
        return " | ".join(parts) if parts else None

    if discipline == "swim":
        css = row.get("css_pace_s_per_100m")
        if not css:
            return None
        zones = derive_zones_for_discipline("swim", css_pace_s_per_100m=float(css))
        css_minus5 = zones.get("CSS_minus5", "")
        css_val = zones.get("CSS", "")
        parts = []
        if css_minus5:
            parts.append(f"Z1-Z2: {css_minus5}")
        if css_val:
            parts.append(f"CSS: {css_val}")
        return " | ".join(parts) if parts else None

    return None


def _build_session_section(planned_sessions: list[dict], zones_by_discipline: Optional[dict] = None) -> str:
    lines = ["<b>🎯 Cosa fare oggi</b>"]
    if planned_sessions:
        from html import escape as _esc
        sport_emoji_map = {"swim": "🏊", "bike": "🚴", "run": "🏃",
                           "brick": "🚴🏃", "strength": "💪"}
        _zones = zones_by_discipline or {}
        for planned in planned_sessions:
            sport_emoji = sport_emoji_map.get(planned.get("sport"), "🏋️")
            dur_min = (planned.get("duration_s") or 0) // 60
            type_str = planned.get("session_type") or ""
            # Riga intestazione: sport · tipo · durata · TSS target
            header = f"{sport_emoji} {type_str} · {dur_min}min"
            if planned.get("target_tss") is not None:
                header += f" · TSS {round(float(planned['target_tss']))}"
            lines.append(header)
            # Zone target (percentuali)
            zones_line = _format_target_zones(planned.get("target_zones"))
            if zones_line:
                lines.append(f"Zone: {zones_line}")
            # Zone misurate (da physiology_zones DB)
            sport = planned.get("sport") or ""
            measured_zones = _format_session_zones(sport, _zones)
            if measured_zones:
                lines.append(f"Zone misurate: {measured_zones}")
            # Descrizione COMPLETA (non troncata) — richiesta atleta: dettaglio
            # accurato come su calendar.
            if planned.get("description"):
                desc = [_esc(line) for line in planned["description"].strip().split("\n")]
                lines.append(f"<i>{chr(10).join(desc)}</i>")
            # Workout strutturato (se presente)
            struct_lines = _format_structured(planned.get("structured"))
            if struct_lines:
                lines.append("<b>Struttura:</b>")
                lines.extend(struct_lines)
        return "\n".join(lines)

    lines.append("Nessuna sessione pianificata.")
    lines.append("<i>Il sistema di pianificazione automatica non è ancora attivo. "
                 "Per ora gestisci tu la sessione, oppure apri una conversazione "
                 "col coach in Claude Code per discutere cosa fare.</i>")
    return "\n".join(lines)


def _fetch_latest_severity(kind: str) -> Optional[dict]:
    """Fase 1.5 — recupera l'ultimo log injury/illness ancora 'attivo' (ultimi 14gg)
    per estrarre severity, body_location, durata attesa.
    """
    try:
        sb = get_supabase()
        since = (today_rome() - timedelta(days=14)).isoformat()
        # Non solo kind esatto: un debrief (kind='evening_debrief' etc.) con
        # injury_flag/illness_flag=true portava severity che veniva ignorata.
        res = (
            sb.table("subjective_log")
            .select("severity,body_location,expected_duration_days,logged_at,injury_location")
            .or_(f"kind.eq.{kind},{kind}_flag.eq.true")
            .gte("logged_at", since)
            .order("logged_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        logger.exception("_fetch_latest_severity failed (kind=%s)", kind)
        return None


def _build_warnings_section(metrics: dict) -> str:
    """Warning specifici (hardcoded da CLAUDE.md, gestiti via env var) + severity-aware."""
    flags = metrics.get("flags") or []
    flag_msgs = {
        "fatigue_critical": "🚨 HRV in crash (z<-2) → recovery obbligatorio oggi",
        "fatigue_warning": "⚠️ HRV in calo da 2+ giorni → rimodula sessione di oggi",
        "trend_negative": "📉 HRV trend 7gg sotto baseline 28gg",
        "anticipate_recovery_week": "🔄 Suggerito anticipo settimana di scarico",
        "high_soreness": "😣 Soreness alta segnalata",
        "low_motivation": "😐 Motivazione bassa segnalata",
        "post_illness_caution": "🐢 Cautela post-malattia",
    }
    flag_lines = [flag_msgs[f] for f in flags if f in flag_msgs]

    # Fase 1.5 — Severity-aware injury/illness warnings
    if "injury_flag" in flags:
        inj = _fetch_latest_severity("injury") or {}
        sev = inj.get("severity")
        loc = inj.get("body_location") or inj.get("injury_location") or ""
        loc_str = f" a {loc}" if loc else ""
        if sev == "severe":
            flag_lines.append(
                f"🚑 <b>Infortunio severo{loc_str}</b> → STOP disciplina coinvolta. Valuta visita medica."
            )
        elif sev == "moderate":
            flag_lines.append(
                f"🩹 <b>Infortunio moderato{loc_str}</b> → skip qualità sulla disciplina. Z1-Z2 e tecnica."
            )
        elif sev == "mild":
            flag_lines.append(
                f"🟡 Fastidio lieve{loc_str} → monitora durante sessione, se peggiora STOP."
            )
        else:
            flag_lines.append("🩹 Flag infortunio attivo → stop disciplina coinvolta")

    if "illness_flag" in flags:
        ill = _fetch_latest_severity("illness") or {}
        sev = ill.get("severity")
        dur = ill.get("expected_duration_days")
        dur_str = f" (durata attesa ~{dur}gg)" if dur else ""
        if sev == "severe":
            flag_lines.append(
                f"🤒 <b>Malattia grave{dur_str}</b> → STOP totale allenamento. Riposo + idratazione."
            )
        elif sev == "moderate":
            flag_lines.append(
                f"🤧 Malattia moderata{dur_str} → solo Z1 leggera se sintomi sopra il collo, altrimenti riposo."
            )
        elif sev == "mild":
            flag_lines.append(
                f"😷 Sintomi lievi{dur_str} → Z1-Z2 ridotto, evita intensità."
            )
        else:
            flag_lines.append("🤒 Flag malattia attivo → stop intensità")

    # Warning permanenti gestiti da env var (default True, settali a "false" quando risolti)
    permanent = []
    if os.environ.get("SHOULDER_ACTIVE", "true").lower() == "true":
        permanent.append(
            "<b>Spalla dx</b> (borsite ancora attiva): se nuoti, solo Z1-Z2 con focus tecnica. Niente serie intense."
        )
    if os.environ.get("PLANTAR_ACTIVE", "true").lower() == "true":
        permanent.append(
            "<b>Fascite plantare sx</b>: se corri, max +10% volume rispetto a settimana scorsa."
        )

    if not flag_lines and not permanent:
        return ""

    lines = ["<b>⚠️ Da tenere d'occhio</b>"]
    for f in flag_lines:
        lines.append(f)
    for p in permanent:
        lines.append(f"• {p}")
    return "\n".join(lines)

def _build_race_progress_section(today: date) -> str:
    """Sezione progresso verso la prossima gara A dalla tabella races."""
    # Bug fix audit C2: una query/parsing fallita su questa sezione opzionale
    # NON deve far crashare l'intero brief mattutino. Degrada a sezione vuota.
    try:
        sb = get_supabase()
        res = sb.table("races").select(
            "name,race_date"
        ).gte("race_date", today.isoformat()).eq(
            "priority", "A"
        ).order("race_date").limit(1).execute()

        if not res.data:
            return ""

        r = res.data[0]
        race_date = date.fromisoformat(r["race_date"])
        race_name = r["name"]
        days_left = (race_date - today).days
    except Exception:
        logger.warning("_build_race_progress_section fallita", exc_info=True)
        return ""

    if days_left < 0:
        return ""

    weeks_left = days_left // 7

    if weeks_left >= 14:
        phase = "Ricostruzione"
        focus = "Base aerobica, tecnica, recupero infortuni. NO intensità ancora."
    elif weeks_left >= 10:
        phase = "Test + Build 1"
        focus = "Test fitness questa fase. Introduzione Z2/Z3 controllata, primo blocco soglia."
    elif weeks_left >= 6:
        phase = "Build 2 specifico"
        focus = "Specifico cross: brick MTB+trail, OWS, simulazioni, qualità Z4."
    elif weeks_left >= 3:
        phase = "Pre-gara"
        focus = "Specifico race-pace, taper iniziale."
    elif weeks_left >= 1:
        phase = "Taper"
        focus = "Volume ridotto, intensità mantenuta in micro-dosi."
    else:
        phase = "Race week"
        focus = "Modalità gara attiva — vedi race week protocol."

    lines = [
        f"<b>📅 Verso {race_name}</b>",
        f"Mancano <b>{days_left} giorni</b> ({weeks_left} settimane).",
        f"Fase: {phase}",
        f"<i>{focus}</i>",
    ]
    return "\n".join(lines)

def _get_upcoming_race(today: date) -> Optional[dict]:
    """Trova la prossima gara A o B entro 7 giorni dalla tabella races."""
    # Bug fix audit C2: questa funzione gira presto in build_brief; una query
    # fallita non deve abbattere l'intero brief.
    try:
        sb = get_supabase()
        window_end = (today + timedelta(days=7)).isoformat()
        res = sb.table("races").select(
            "name,race_date,priority,distance"
        ).gte("race_date", today.isoformat()).lte(
            "race_date", window_end
        ).in_("priority", ["A", "B"]).order("race_date").limit(1).execute()

        if not res.data:
            return None

        r = res.data[0]
        race_dt = date.fromisoformat(r["race_date"])
        return {
            "name": r["name"],
            "date": race_dt,
            "priority": r["priority"],
            "distance": r.get("distance") or "",
            "days_to_race": (race_dt - today).days,
        }
    except Exception:
        logger.warning("_get_upcoming_race fallita", exc_info=True)
        return None


def _race_section_applicable(race: Optional[dict]) -> bool:
    """True se la sezione race-week va mostrata per questa gara.

    Protocollo race-week completo (T-7 → T-0) SOLO per gare priority A.
    Per le gare B (di preparazione) la sezione compare solo da T-2, con
    indicazioni leggere: un taper completo a T-7 distruggerebbe la settimana
    di carico.
    """
    if not race:
        return False
    if race.get("priority") == "B" and race.get("days_to_race", 99) > 2:
        return False
    return True


def _build_race_b_section(race: dict, days: int) -> str:
    """Sezione leggera per gara B (T-2 → T-0): scarico breve, niente taper."""
    weekday_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    when = "OGGI" if days == 0 else f"tra {days}gg" if days > 1 else "domani"
    lines = [
        f"<b>🏁 {race['name']} — gara B {when}</b>",
        f"Gara: {weekday_it[race['date'].weekday()]} {race['date'].day}/{race['date'].month}",
        "",
        "Gara di preparazione: scarico breve pre-gara B, niente taper.",
        "La settimana resta di carico normale — usala come allenamento race-pace.",
    ]
    return "\n".join(lines)


def _build_race_week_section(race: dict, today: date) -> str:
    """Sezione race week (T-7 a T-0).

    Sostituisce/affianca la sezione 'Verso Lavarone' nei 7 giorni gara.
    Protocollo completo solo per gare A; per le B sezione leggera (da T-2).
    """
    days = race["days_to_race"]
    weekday_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

    if race.get("priority") == "B":
        return _build_race_b_section(race, days)

    if days == 0:
        return _build_race_day_section(race)
    
    label = {
        7: "T-7 — Inizio settimana gara",
        6: "T-6 — Settimana gara, taper attivo",
        5: "T-5 — Settimana gara",
        4: "T-4 — Settimana gara",
        3: "T-3 — Sessione richiamo intensità oggi",
        2: "T-2 — Apertura + check materiale",
        1: "T-1 — Vigilia",
    }.get(days, f"T-{days}")
    
    lines = [
        f"<b>🏆 {race['name']} — {label}</b>",
        f"Gara: {weekday_it[race['date'].weekday()]} {race['date'].day}/{race['date'].month}",
    ]
    
    # Indicazioni per giorno
    if days == 7:
        lines.append("")
        lines.append("Inizia il taper: volume -40%, intensità mantenuta in micro-dosi.")
        lines.append("Verifica iscrizione, alloggio, viaggio. Inizia check bici.")
    elif days == 3:
        lines.append("")
        lines.append("Sessione di richiamo: 10min Z2 + 5×30s allungo + 10min Z2.")
        lines.append("Brief percorso e meteo: cerca aggiornamenti gara.")
    elif days == 2:
        lines.append("")
        lines.append("Ultima sessione apertura: 20-30 min Z1-Z2 + 3-4 allunghi brevi.")
        lines.append("📋 Oggi: check materiale completo (vedi skill race_week_protocol).")
    elif days == 1:
        lines.append("")
        lines.append("Sessione vigilia: 15-20 min Z1, 1-2 allunghi neutri.")
        lines.append("Cena entro 19:30, idratazione spalmata, letto entro 22:00.")
        lines.append("Tutto pronto stasera, NIENTE preparazione domattina.")
    
    lines.append("")
    lines.append("<i>Per il piano gara dettagliato apri Claude Code: 'attiva race week protocol'</i>")
    
    return "\n".join(lines)


def _build_race_day_section(race: dict) -> str:
    """T-0: il giorno della gara. Ricorda di aprire Claude Code per il race brief."""
    return (
        f"<b>🏆 {race['name']} — RACE DAY</b>\n"
        f"\n"
        f"Oggi è il giorno. Apri Claude Code ORA per ricevere il race day brief "
        f"completo (timeline, colazione, warm-up, pace plan, mental checkpoints).\n"
        f"\n"
        f"<i>Comando: 'race day brief'</i>\n"
        f"\n"
        f"In bocca al lupo. Hai fatto il lavoro, oggi è esecuzione."
    )

def _build_footer() -> str:
    return "<i>💬 /log note · /debrief stasera · /help comandi</i>"


def _build_risk_section() -> str:
    """Fase 2.5 — Sezione rischio probabilistico nel brief.

    Mostra solo i rischi >= 'high' (50%+) per non sovraccaricare il brief.
    Rischi 'moderate' silenziosi; 'low' invisibili.
    """
    try:
        from coach.analytics.risk import compute_all_risks, risks_to_brief_lines
        risks = compute_all_risks()
        lines = risks_to_brief_lines(risks, threshold="high")
        if not lines:
            return ""
        return "<b>⚠️ Rischi attivi</b>\n" + "\n".join(lines)
    except Exception:
        logger.warning("Risk section failed", exc_info=True)
        return ""


def _build_belief_insight_section() -> str:
    """Fase 4.4 — Sezione 'belief del giorno' nel brief.

    Cita una validated/strong belief rilevante oggi (es. giorno della settimana,
    fase mesociclo). Solo beliefs status >= validated_belief, confidence > 0.7.
    Niente cita se non ce ne sono.
    """
    try:
        from coach.analytics.belief_engine import get_actionable_beliefs
        from coach.utils.dt import today_rome
        beliefs = get_actionable_beliefs()
        if not beliefs:
            return ""
        # Filtra beliefs rilevanti per oggi: cerca giorno settimana o fase mesociclo
        # in belief_text. Semplice heuristica per ora.
        today = today_rome()
        day_names_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        today_name = day_names_it[today.weekday()]

        relevant = [b for b in beliefs
                    if today_name in b.belief_text.lower()
                    or today_name in (b.prescription or "").lower()]
        if not relevant:
            return ""
        b = relevant[0]
        emoji = "🏆" if b.status == "strong_belief" else "✅"
        from html import escape as _esc
        # Escape: il testo viene da estrazione automatica e contiene operatori
        # letterali (es. "TSB < -30", "TSS > 60") che romperebbero il parse HTML.
        text = _esc((b.prescription or b.belief_text).replace("**", ""))
        return (
            f"<b>{emoji} Insight personalizzato</b>\n"
            f"{text} <i>(n={b.evidence_n}, conf={int(b.confidence*100)}%)</i>"
        )
    except Exception:
        logger.warning("Belief insight section failed", exc_info=True)
        return ""


def _build_uncertainty_disclaimer() -> str:
    """Fase 4.3 — Disclaimer se confidence dei dati di oggi è bassa.

    Hard rules: missing HRV >40%, sleep mancante, sample <7 giorni.
    """
    try:
        from coach.utils.dt import today_rome
        from coach.utils.supabase_client import get_supabase
        from datetime import timedelta
        sb = get_supabase()
        today = today_rome()
        since = (today - timedelta(days=7)).isoformat()
        res = sb.table("daily_wellness").select("date,hrv_rmssd,sleep_score").gte(
            "date", since
        ).execute()
        rows = res.data or []
        if not rows:
            return ""
        hrv_present = sum(1 for r in rows if r.get("hrv_rmssd") is not None)
        sleep_present = sum(1 for r in rows if r.get("sleep_score") is not None)
        total = len(rows)
        hrv_coverage = hrv_present / total if total > 0 else 0
        sleep_coverage = sleep_present / total if total > 0 else 0

        warnings = []
        if hrv_coverage < 0.6:
            warnings.append(f"HRV mancante {total - hrv_present}/{total} giorni")
        if sleep_coverage < 0.6:
            warnings.append(f"sleep score mancante {total - sleep_present}/{total} giorni")
        if not warnings:
            return ""
        return (
            "<b>📊 Confidence ridotta</b>\n"
            f"<i>{', '.join(warnings)}. Le proposte di oggi hanno data_coverage bassa.</i>"
        )
    except Exception:
        logger.warning("Uncertainty disclaimer failed", exc_info=True)
        return ""


# ============================================================================
# Main
# ============================================================================

def _last_sync_age_hours(sb) -> Optional[float]:
    res = sb.table("health").select("last_success_at").eq("component", "garmin_sync").execute()
    if not res.data or not res.data[0]["last_success_at"]:
        return None
    last = datetime.fromisoformat(res.data[0]["last_success_at"].replace("Z", "+00:00"))
    # Bug fix audit C3: se il timestamp è naive (senza tz), forzalo UTC altrimenti
    # `now(utc) - naive` solleva TypeError e fa crashare l'intero brief.
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def build_brief() -> str:
    sb = get_supabase()
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    today_iso = today.isoformat()

    age = _last_sync_age_hours(sb)

    metrics_res = sb.table("daily_metrics").select("*").eq("date", today_iso).execute()
    metrics = metrics_res.data[0] if metrics_res.data else {}

    wellness_res = sb.table("daily_wellness").select("*").eq("date", today_iso).execute()
    wellness = wellness_res.data[0] if wellness_res.data else {}

    planned_res = sb.table("planned_sessions").select("*").eq(
        "planned_date", today_iso
    ).eq("status", "planned").execute()
    planned_sessions = planned_res.data or []

    # Zone misurate da physiology_zones (una sola query, passata a _build_session_section)
    zones_by_discipline = _fetch_current_zones(sb)

    # Controlla se siamo in race week: protocollo completo T-7 → T-0 per gare A;
    # per gare B sezione leggera solo da T-2 (niente taper per gare di preparazione)
    upcoming_race = _get_upcoming_race(today)
    if not _race_section_applicable(upcoming_race):
        upcoming_race = None

    # Blocco 5.3: personalized insert from coaching_observations
    pattern_line = ""
    try:
        from coach.planning.personalized_insert import get_personalized_insert
        pattern_line = get_personalized_insert(today) or ""
    except Exception:
        pass

    if upcoming_race:
        sections = [
            _build_header(today),
            _build_freshness_warning(age),
            _build_wellness_section(wellness, metrics),
            _build_race_week_section(upcoming_race, today),
            _build_session_section(planned_sessions, zones_by_discipline),
            _build_warnings_section(metrics),
            _build_risk_section(),
            _build_belief_insight_section(),
            _build_uncertainty_disclaimer(),
            pattern_line,
            _build_footer(),
        ]
    else:
        sections = [
            _build_header(today),
            _build_freshness_warning(age),
            _build_wellness_section(wellness, metrics),
            _build_load_section(metrics),
            _build_session_section(planned_sessions, zones_by_discipline),
            _build_race_progress_section(today),
            _build_warnings_section(metrics),
            _build_risk_section(),
            _build_belief_insight_section(),
            _build_uncertainty_disclaimer(),
            pattern_line,
            _build_footer(),
        ]
    # Join non-empty con doppia newline
    return "\n\n".join(s for s in sections if s.strip())


def send_to_telegram(message: str, purpose: str = MORNING_BRIEF, parent_workflow: str = "morning-briefing.yml") -> None:
    from coach.utils.telegram_logger import send_and_log_message
    result = send_and_log_message(message, purpose=purpose, parent_workflow=parent_workflow)
    if result is None:
        raise RuntimeError("send_to_telegram failed (see logs)")


def _already_sent_today(sb, purpose: str) -> bool:
    """Idempotenza: True se un messaggio con questo purpose è già stato
    inviato OGGI (giorno Rome). Una-volta-al-giorno, non finestra mobile:
    robusto a trigger multipli/ritardati (ingest ogni 3h + eventuale fallback
    cron nativo che arriva in ritardo)."""
    rome = ZoneInfo("Europe/Rome")
    midnight_rome = datetime.now(rome).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = midnight_rome.astimezone(timezone.utc).isoformat()
    try:
        res = (
            sb.table("bot_messages")
            .select("id,sent_at")
            .eq("purpose", purpose)
            .gte("sent_at", cutoff)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        logger.warning("Idempotency check failed; proceeding with send", exc_info=True)
        return False


def _brief_already_sent_today(sb) -> bool:
    return _already_sent_today(sb, MORNING_BRIEF)


def build_energy_update() -> str:
    """Body Battery + readiness Garmin per il messaggio energia separato,
    mandato più tardi del brief delle 5:00 (vedi _build_energy_section)."""
    sb = get_supabase()
    today_iso = datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()

    metrics_res = sb.table("daily_metrics").select("*").eq("date", today_iso).execute()
    metrics = metrics_res.data[0] if metrics_res.data else {}

    wellness_res = sb.table("daily_wellness").select("*").eq("date", today_iso).execute()
    wellness = wellness_res.data[0] if wellness_res.data else {}

    return _build_energy_section(wellness, metrics)


def main() -> None:
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Idempotenza once-per-day: skip se un brief è già stato inviato OGGI
    # (giorno Rome). workflow_dispatch può forzare via FORCE_SEND=true.
    force_send = os.environ.get("FORCE_SEND", "").lower() in ("true", "1", "yes")

    # Floor gate: target 05:00 Rome. I cron coprono estate/inverno (03/04 UTC);
    # questo evita che il cron 03:00 UTC d'inverno (= 04:00 Rome) invii in anticipo.
    if not force_send and datetime.now(ZoneInfo("Europe/Rome")).hour < 5:
        logger.info("Brief gate: prima delle 05 Rome, troppo presto — skip")
        return

    if not force_send:
        sb = get_supabase()
        if _brief_already_sent_today(sb):
            logger.info("Morning brief already sent today (Rome) — skipping duplicate run")
            return

    try:
        msg = build_brief()
        send_to_telegram(msg)
        record_health("briefing_morning", success=True)
        logger.info("Brief v2 sent")
    except Exception as e:  # noqa: BLE001
        logger.exception("Brief v2 failed")
        record_health("briefing_morning", success=False, error=str(e))
        raise


def main_energy() -> None:
    """Messaggio energia separato (Body Battery + readiness Garmin), mandato
    dopo il risveglio naturale — non alle 5:00 come il brief principale,
    altrimenti il sonno interrotto dalla notifica falsa proprio i dati che
    deve riportare."""
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    force_send = os.environ.get("FORCE_SEND", "").lower() in ("true", "1", "yes")

    # Floor gate: target ~07:30 Rome. I cron coprono estate/inverno; finestra
    # larga (ingest ogni 3h) cattura il primo run dopo le 07:00 Rome.
    if not force_send and datetime.now(ZoneInfo("Europe/Rome")).hour < 7:
        logger.info("Energy gate: prima delle 07 Rome, troppo presto — skip")
        return

    sb = get_supabase()
    if not force_send and _already_sent_today(sb, ENERGY_UPDATE):
        logger.info("Energy update already sent today (Rome) — skipping duplicate run")
        return

    try:
        msg = build_energy_update()
        if not msg:
            logger.info("Nessun dato energia disponibile oggi — skip invio")
            record_health("energy_update", success=True)
            return
        send_to_telegram(msg, purpose=ENERGY_UPDATE, parent_workflow="energy-update.yml")
        record_health("energy_update", success=True)
        logger.info("Energy update sent")
    except Exception as e:  # noqa: BLE001
        logger.exception("Energy update failed")
        record_health("energy_update", success=False, error=str(e))
        raise


if __name__ == "__main__":
    import sys
    if "--energy" in sys.argv:
        main_energy()
    else:
        main()