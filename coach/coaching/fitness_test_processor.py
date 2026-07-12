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
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

SPORT_MAP = {"bike": "bike", "run": "run", "swim": "swim"}

# Ciclo test. NB: l'atleta NON ha wattmetro → sulla bici si usa il test a HR
# (threshold_bike_hr), non FTP a potenza. I test a potenza restano supportati
# per il futuro (se arriverà un wattmetro).
TEST_CYCLE_ORDER = ["threshold_bike_hr", "threshold_run_30min", "css_swim_400_200", "lthr_run"]

# Bound di plausibilità fisiologica per test_type (audit E — confermati
# dall'atleta, 2026-06-01). Risultati fuori range = estrazione errata
# (unità/split sbagliati) → scartati per non corrompere le zone.
PLAUSIBLE_BOUNDS = {
    "ftp_bike_20min": (80, 450),       # W
    "ftp_bike_ramp": (80, 450),        # W
    "threshold_bike_hr": (120, 200),   # bpm
    "threshold_run_30min": (150, 360), # s/km
    "css_swim_400_200": (70, 150),     # s/100m
    "lthr_run": (120, 200),            # bpm
}
TEST_CYCLE_NEXT = {
    "threshold_bike_hr": "threshold_run_30min",
    "threshold_run_30min": "css_swim_400_200",
    "threshold_run_20min": "css_swim_400_200",
    "css_swim_400_200": "lthr_run",
    "lthr_run": "threshold_bike_hr",
    # Varianti a potenza (richiedono wattmetro)
    "ftp_bike_20min": "threshold_run_30min",
    "ftp_bike_ramp": "threshold_run_30min",
}

# zone_system di default per ogni test_type (usato dal path manuale e come
# fallback se structured non lo specifica).
DEFAULT_ZONE_SYSTEM = {
    "ftp_bike_20min": "coggan_7zone",
    "ftp_bike_ramp": "coggan_7zone",
    "threshold_bike_hr": "lthr_5zone",
    "threshold_run_30min": "pace_5zone",
    "threshold_run_20min": "pace_5zone",
    "css_swim_400_200": "css_3zone",
    "lthr_run": "lthr_5zone",
}

# Mappa test_type → (colonna DB, disciplina)
FIELD_MAP = {
    "ftp_bike_20min": ("ftp_w", "bike"),
    "ftp_bike_ramp": ("ftp_w", "bike"),
    "threshold_bike_hr": ("lthr", "bike"),
    "threshold_run_30min": ("threshold_pace_s_per_km", "run"),
    "threshold_run_20min": ("threshold_pace_s_per_km", "run"),
    "css_swim_400_200": ("css_pace_s_per_100m", "swim"),
    "lthr_run": ("lthr", "run"),
}


class FitnessTestProcessor:
    def __init__(self):
        self.sb = get_supabase()

    def process_fitness_test(self, activity: dict, planned_session: dict) -> dict:
        structured = planned_session.get("structured") or {}
        # Se il coach non ha popolato structured, inferisci il test_type da
        # sport + description (così una sessione fitness_test non viene saltata
        # silenziosamente solo perché manca il payload strutturato).
        test_type = structured.get("test_type") or _infer_test_type(planned_session, activity)
        activity_id = activity.get("id") or activity.get("external_id")

        if not test_type:
            return {"status": "skip", "reason": "cannot determine test_type"}

        existing = self.sb.table("physiology_zones").select("id").eq(
            "test_activity_id", str(activity_id)
        ).limit(1).execute()
        if existing.data:
            logger.info("Already processed: activity %s", activity_id)
            return {"status": "skip", "reason": "already_processed"}

        extractor = {
            "ftp_bike_20min": self._extract_ftp_bike_20min,
            "ftp_bike_ramp": self._extract_ftp_bike_ramp,
            "threshold_bike_hr": self._extract_threshold_bike_hr,
            "threshold_run_30min": self._extract_threshold_run,
            "threshold_run_20min": self._extract_threshold_run,
            "css_swim_400_200": self._extract_css_swim,
            "lthr_run": self._extract_lthr,
        }.get(test_type)

        if not extractor:
            return {"status": "error", "reason": f"unknown test_type: {test_type}"}

        # Auto-estrazione SOLO se il coach ha fornito la config di extraction
        # (quale split/lap usare). Senza config lo split del test è ignoto:
        # NON estraiamo (eviteremmo di scrivere una soglia sbagliata) e
        # instradiamo alla revisione del coach.
        if structured.get("extraction"):
            result = extractor(activity, structured)
            if result is None:
                result = self._try_fallback_extraction(activity, structured)
        else:
            result = None

        if result is None:
            self._notify_telegram(
                test_type, 0, {}, success=False,
                error_msg=(
                    "Estrazione automatica non possibile (config split mancante o "
                    "dati assenti). Apri Claude.ai: il coach leggerà gli split con "
                    "get_session_review_context e salverà le zone con "
                    "commit_physiology_zones."
                ),
                dedup_key=f"fittest_fail_{activity_id}",
            )
            return {"status": "needs_coach_review", "test_type": test_type,
                    "activity_id": str(activity_id)}

        # Audit E: bound di plausibilità. Un risultato fuori range indica
        # estrazione errata (unità/split) → NON sovrascrivere le zone con dati corrotti.
        bounds = PLAUSIBLE_BOUNDS.get(test_type)
        if bounds and not (bounds[0] <= result <= bounds[1]):
            logger.warning(
                "Fitness test %s: risultato %s fuori range plausibile %s, scartato",
                test_type, result, bounds,
            )
            self._notify_telegram(
                test_type, result, {}, success=False,
                error_msg=f"Risultato estratto ({result}) fuori range plausibile {bounds}. "
                          f"Probabile errore di rilevamento split. Verifica manualmente su Claude.ai.",
                dedup_key=f"fittest_fail_{activity_id}",
            )
            return {"status": "implausible_result", "test_type": test_type, "result": result}

        zone_system = structured.get("zone_system") or DEFAULT_ZONE_SYSTEM.get(test_type, "coggan_7zone")
        zones = self._compute_zones(zone_system, result)

        sport = _test_type_to_sport(test_type)
        from coach.utils.dt import to_rome_date
        _d = to_rome_date(activity.get("started_at"))
        activity_date = _d.isoformat() if _d else str(activity.get("started_at", ""))[:10]

        applied = self._upsert_physiology_zones(
            sport=sport,
            result=result,
            zones=zones,
            test_type=test_type,
            test_date=activity_date,
            source_activity_id=str(activity_id),
            zone_system=zone_system,
        )

        # C3: se il write è stato saltato (lock manuale), NON aggiornare CLAUDE.md
        # e NON annunciare "zone aggiornate" con valori mai scritti.
        if not applied:
            self._notify_telegram(
                test_type, result, {}, success=False,
                error_msg=(
                    "⚠️ Test rilevato ma NON applicato: zona manuale attiva (lock). "
                    "Usa commit manuale per forzare."
                ),
                dedup_key=f"fittest_lock_{activity_id}",
            )
            return {"status": "skipped_manual_lock", "test_type": test_type, "result": result}

        # L'anamnesi è una vista rigenerata da zero dal DB (WP1): sostituisce
        # il vecchio patch regex su CLAUDE.md (_update_claude_md, rimosso) che
        # duplicava la verità e falliva in silenzio se il campo cambiava nome.
        anamnesis_ok = self._regenerate_anamnesis()

        self._notify_telegram(test_type, result, zones, success=True)

        return {
            "status": "processed",
            "test_type": test_type,
            "result": result,
            "zones": zones,
            "anamnesis_updated": anamnesis_ok,
        }

    # ── Extractors ─────────────────────────────────────────────────────────

    def _extract_ftp_bike_20min(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index", 1)
        if splits and isinstance(splits, list) and len(splits) > idx:
            # Bug fix audit E1: NIENTE fallback su averageSpeed — velocità (m/s) e
            # potenza (W) non sono interscambiabili; usarla come watt corrompe FTP
            # e tutte le zone. Senza potenza per-split, ritorna None (no dato).
            avg_power = splits[idx].get("avg_power_w")
            if avg_power and float(avg_power) > 0:
                return round(float(avg_power) * 0.95, 1)
        return None

    def _extract_ftp_bike_ramp(self, activity: dict, structured: dict) -> Optional[float]:
        max_power = activity.get("max_power_w") or activity.get("np_w")
        if max_power:
            return round(float(max_power) * 0.75, 1)
        return None

    def _extract_threshold_bike_hr(self, activity: dict, structured: dict) -> Optional[float]:
        """Test soglia bici a frequenza cardiaca (atleta SENZA wattmetro).

        Protocollo: 20' (o 30') a sforzo costante massimo sostenibile.
        LTHR ≈ HR media del segmento di test × factor. Factor default 1.0 per un
        20' steady; per un 30' Friel usa la media degli ultimi 20' (factor ~0.95
        sulla media totale). Override via structured.extraction.primary.lthr_factor.
        """
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index")
        factor = float(extraction.get("lthr_factor", 1.0))
        splits = activity.get("splits")
        avg_hr = None
        if idx is not None and splits and isinstance(splits, list) and len(splits) > idx:
            avg_hr = splits[idx].get("avg_hr") or splits[idx].get("averageHR")
        # Fallback: HR media dell'attività intera (meno preciso ma meglio di niente)
        if not avg_hr:
            avg_hr = activity.get("avg_hr")
        if avg_hr:
            return round(float(avg_hr) * factor)
        return None

    def _extract_threshold_run(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        extraction = (structured.get("extraction") or {}).get("primary", {})
        idx = extraction.get("interval_index", 1)
        if splits and isinstance(splits, list) and len(splits) > idx:
            # Bug fix audit E2: NIENTE fallback su averagePace (chiave raw Garmin
            # con unità diversa da s/km) — usiamo solo il campo normalizzato dal
            # nostro ingest. Unità errata produrrebbe zone senza senso.
            pace = splits[idx].get("avg_pace_s_per_km")
            if pace and float(pace) > 0:
                return round(float(pace), 1)
        return None

    def _extract_css_swim(self, activity: dict, structured: dict) -> Optional[float]:
        splits = activity.get("splits")
        if not splits or not isinstance(splits, list) or len(splits) < 2:
            return None

        # C6: il protocollo prevede 400m warmup + 200m progressivo PRIMA dei
        # segmenti all-out → il PRIMO split nel range di distanza è il warmup,
        # non il test. Tra i candidati di ogni range si prende il PIÙ VELOCE
        # (tempo minimo), che è per definizione il segmento all-out.
        t400 = None
        t200 = None
        for s in splits:
            dist = s.get("distance_m") or s.get("distance") or 0
            time_s = s.get("duration_s") or s.get("movingDuration") or s.get("elapsedDuration") or 0
            dist = float(dist)
            time_s = float(time_s)
            if time_s <= 0:
                continue
            if 350 <= dist <= 450 and (t400 is None or time_s < t400):
                t400 = time_s
            elif 180 <= dist <= 250 and (t200 is None or time_s < t200):
                t200 = time_s

        # Bug fix audit E3: guard t400 > t200. Se gli split sono mal rilevati
        # (es. warmup catturato come t400) la formula darebbe CSS negativo/assurdo
        # che corromperebbe le zone. Richiediamo t400 > t200 (e tempi positivi).
        if t400 is not None and t200 is not None and t400 > t200 > 0:
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
        # Confini CONTIGUI: la fine di una zona è l'inizio della successiva,
        # niente buchi (prima Z2→0.89 e Z3→0.90 lasciavano 151-153 scoperto).
        b1 = round(lthr * 0.81)
        b2 = round(lthr * 0.89)
        b3 = round(lthr * 0.95)
        return {
            "Z1_recovery": f"<{b1} bpm",
            "Z2_aerobic": f"{b1}-{b2} bpm",
            "Z3_tempo": f"{b2}-{b3} bpm",
            "Z4_threshold": f"{b3}-{lthr} bpm",
            "Z5_above": f">{lthr} bpm",
        }

    # ── Persistence ────────────────────────────────────────────────────────

    def _upsert_physiology_zones(
        self, sport: str, result: float, zones: dict,
        test_type: str, test_date: str, source_activity_id: str,
        zone_system: str, method: Optional[str] = None,
    ) -> bool:
        """Scrive la zona su DB. Ritorna True se scritta, False se saltata
        (lock manuale attivo o test_type sconosciuto) — il chiamante NON deve
        aggiornare CLAUDE.md né annunciare "zone aggiornate" se ritorna False (C3).
        """
        field_map = FIELD_MAP
        db_field, discipline = field_map.get(test_type, (None, sport))
        if not db_field:
            return False

        method = method or test_type

        # Lock correzione manuale: se esiste una zona attiva con method 'manual*'
        # (es. correzione caldo della soglia), NON sovrascriverla con un ricalcolo
        # automatico. L'atleta l'ha messa a mano e deve restare finché non la cambia.
        # Un commit deliberato con method 'manual_*' bypassa il lock (è esso stesso
        # manuale, e diventa il nuovo lock).
        if not method.startswith("manual"):
            try:
                locked = self.sb.table("physiology_zones").select("method").eq(
                    "discipline", discipline
                ).is_("valid_to", "null").like("method", "manual%").limit(1).execute()
                if locked.data:
                    logger.warning(
                        "Zona %s bloccata manualmente (%s) — skip ricalcolo automatico %s",
                        discipline, locked.data[0]["method"], test_type,
                    )
                    return False
            except Exception:
                logger.warning("Check lock zona manuale fallito, procedo", exc_info=True)

        # M3: chiudi la riga attiva precedente della stessa disciplina (valid_to
        # = valid_from nuovo), altrimenti restano N righe aperte e
        # proactive_reminders._check_test_due manda reminder "test da rifare" falsi.
        try:
            self.sb.table("physiology_zones").update(
                {"valid_to": test_date}
            ).eq("discipline", discipline).is_("valid_to", "null").lt(
                "valid_from", test_date
            ).execute()
        except Exception:
            logger.warning("Chiusura valid_to riga precedente fallita, procedo", exc_info=True)

        record = {
            "discipline": discipline,
            "valid_from": test_date,
            db_field: result,
            "test_activity_id": source_activity_id,
            "method": method,
            "notes": json.dumps({"zones": zones, "zone_system": zone_system}),
        }

        # Audit E4: chiave unique (discipline, valid_from, method) — prima non
        # esisteva alcun vincolo unique (upsert sarebbe fallito a runtime) e
        # test diversi lo stesso giorno si sarebbero sovrascritti.
        self.sb.table("physiology_zones").upsert(
            record, on_conflict="discipline,valid_from,method"
        ).execute()
        logger.info("Physiology zones upserted: %s %s=%s", discipline, db_field, result)

        # WP3: le prescrizioni future contengono i range HR nel testo — al
        # cambio zone vanno riallineate, altrimenti restano coi numeri del
        # test precedente. Punto unico: qui, dove le zone cambiano davvero.
        # Non-bloccante (le zone sono già su DB).
        try:
            from coach.coaching.zone_recalc import recalc_future_sessions
            n = recalc_future_sessions(discipline)
            if n > 0:
                from coach.utils.purposes import ZONES_RECALC
                from coach.utils.telegram_logger import send_and_log_message
                send_and_log_message(
                    f"🔁 Zone {discipline} aggiornate: {n} sessioni future riallineate ai nuovi range.\n"
                    f"<i>Ricorda di aggiornare anche le zone HR sul Garmin (device/Connect).</i>",
                    purpose=ZONES_RECALC,
                )
        except Exception:
            logger.warning("zone_recalc fallito (zone comunque salvate)", exc_info=True)
        return True

    def _regenerate_anamnesis(self) -> bool:
        """Rigenera docs/athlete_anamnesis.md dal DB (WP1).

        Sostituisce il patch regex su CLAUDE.md: il file è una vista, la
        verità sta in physiology_zones/active_constraints/mesocycles.
        Non-bloccante: un fallimento qui non deve far fallire il test appena
        processato (le zone sono già scritte sul DB).
        """
        try:
            from scripts.generate_anamnesis import generate_anamnesis
            return generate_anamnesis()
        except Exception:
            logger.exception("Rigenerazione anamnesi fallita (zone comunque salvate su DB)")
            return False

    def commit_manual_result(
        self,
        test_type: str,
        result: float,
        test_date: str,
        activity_id: Optional[str] = None,
        zone_system: Optional[str] = None,
        notify: bool = True,
    ) -> dict:
        """Scrive una zona fisiologica da un risultato test RIPORTATO (non auto-estratto).

        È il path che chiude il vicolo cieco: quando l'auto-estrazione fallisce
        (split mancanti, nessuna sessione pianificata, bici senza wattmetro),
        l'atleta/coach fornisce il valore del segmento di test e qui calcoliamo le
        zone e le persistiamo. Stesso identico storage dell'auto-detection.

        result: per ftp_* = watt; threshold_run_* = sec/km; css = sec/100m;
                lthr_run/threshold_bike_hr = bpm.
        """
        if test_type not in FIELD_MAP:
            return {"status": "error", "reason": f"unknown test_type: {test_type}"}

        zone_system = zone_system or DEFAULT_ZONE_SYSTEM.get(test_type, "coggan_7zone")
        zones = self._compute_zones(zone_system, float(result))
        sport = _test_type_to_sport(test_type)

        # C3: il commit manuale è deliberato → method 'manual_<test_type>' bypassa
        # il lock anti-sovrascrittura (essendo esso stesso manual) e diventa il
        # nuovo lock. Senza questo, un lock manuale precedente bloccava anche il
        # commit manuale, rendendo impossibile aggiornare la soglia.
        method = test_type if test_type.startswith("manual") else f"manual_{test_type}"
        self._upsert_physiology_zones(
            sport=sport,
            result=float(result),
            zones=zones,
            test_type=test_type,
            test_date=test_date,
            source_activity_id=str(activity_id) if activity_id else "manual",
            zone_system=zone_system,
            method=method,
        )

        anamnesis_ok = self._regenerate_anamnesis()

        if notify:
            self._notify_telegram(test_type, float(result), zones, success=True)

        logger.info("Manual test result committed: %s=%s (%s)", test_type, result, test_date)
        return {
            "status": "processed_manual",
            "test_type": test_type,
            "result": float(result),
            "zones": zones,
            "anamnesis_updated": anamnesis_ok,
        }

    def _claim_notification(self, dedup_key: str) -> bool:
        """M4: claim-before-send su sent_reminders (unique trigger_type+sent_date).

        Ritorna True se il claim riesce (si può inviare), False se già inviato
        (conflitto unique) — evita fino a ~16 reinvii con ingest ogni 3h.
        """
        try:
            self.sb.table("sent_reminders").insert({
                "trigger_type": dedup_key,
                "sent_date": today_rome().isoformat(),
                "context": {"source": "fitness_test_processor"},
            }).execute()
            return True
        except Exception:
            logger.info("Notifica fitness test già inviata oggi (%s), skip", dedup_key)
            return False

    def _notify_telegram(self, test_type: str, result: float, zones: dict, success: bool,
                         error_msg: str = "", dedup_key: Optional[str] = None) -> None:
        if dedup_key and not self._claim_notification(dedup_key):
            return
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


def _infer_test_type(planned_session: dict, activity: dict) -> Optional[str]:
    """Inferisce il test_type da sport + description quando structured è nullo.

    Regola bici: senza wattmetro (nessuna potenza nell'attività) → test a HR.
    """
    sport = (planned_session.get("sport") or activity.get("sport") or "").lower()
    desc = (planned_session.get("description") or "").lower()
    if sport == "run":
        if "lthr" in desc:
            return "lthr_run"
        return "threshold_run_30min"
    if sport == "swim":
        return "css_swim_400_200"
    if sport == "bike":
        has_power = bool(activity.get("avg_power_w") or activity.get("np_w"))
        return "ftp_bike_20min" if has_power else "threshold_bike_hr"
    return None


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
        "threshold_bike_hr": "Soglia Bici (HR)",
        "threshold_run_30min": "Soglia Corsa 30min",
        "threshold_run_20min": "Soglia Corsa 20min",
        "css_swim_400_200": "CSS Nuoto 400+200",
        "lthr_run": "LTHR Corsa",
    }
    return names.get(test_type, test_type)


def _format_result(test_type: str, result: float) -> str:
    if "ftp" in test_type:
        return f"{round(result)}W"
    if "css" in test_type:
        return f"{_fmt_swim_pace(result)}/100m"
    # HR-based (LTHR run + soglia bici a HR): controlla PRIMA di "threshold"
    if "lthr" in test_type or "_hr" in test_type:
        return f"{round(result)} bpm"
    if "threshold" in test_type:
        return f"{_fmt_pace(result)}/km"
    return str(result)


# ── Zone derivation (module-level, reusable) ──────────────────────────────

def derive_zones_for_discipline(
    discipline: str,
    ftp_w: Optional[float] = None,
    threshold_pace_s_per_km: Optional[float] = None,
    css_pace_s_per_100m: Optional[float] = None,
    lthr: Optional[float] = None,
) -> dict:
    """Deriva le zone fisiologiche Z1-Z5 per la disciplina specificata.

    Riusa i @staticmethod esistenti di FitnessTestProcessor senza istanziare
    il processore. Ritorna {} se il valore richiesto per la disciplina e' None.

    Args:
        discipline: "bike", "run" o "swim"
        ftp_w: FTP in watt (per bici)
        threshold_pace_s_per_km: passo soglia in s/km (per corsa)
        css_pace_s_per_100m: CSS in s/100m (per nuoto)
        lthr: soglia HR in bpm (parametro accettato, riservato a uso futuro)

    Returns:
        dict con chiavi zona (es. "Z2_endurance") o {} se dato mancante
    """
    if discipline == "bike":
        # Atleta senza wattmetro: zone bici da LTHR. FTP solo se disponibile.
        if ftp_w is not None:
            return FitnessTestProcessor._compute_coggan_7zone(float(ftp_w))
        if lthr is not None:
            return FitnessTestProcessor._compute_lthr_5zone(float(lthr))
        return {}
    if discipline == "run":
        if threshold_pace_s_per_km is None:
            return {}
        return FitnessTestProcessor._compute_pace_5zone(float(threshold_pace_s_per_km))
    if discipline == "swim":
        if css_pace_s_per_100m is None:
            return {}
        return FitnessTestProcessor._compute_css_3zone(float(css_pace_s_per_100m))
    return {}


# ── CLI entry point ────────────────────────────────────────────────────────

def check_recent() -> list[dict]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sb = get_supabase()
    processor = FitnessTestProcessor()

    # 48h window: a test done in the morning may not be processed until the
    # next ingest cycle (runs every 3h). 6h missed late-morning tests processed
    # by a 6pm ingest run when the activity synced at 9:30am.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    activities = sb.table("activities").select(
        "id,external_id,started_at,sport,duration_s,avg_hr,max_hr,avg_power_w,np_w,avg_pace_s_per_km,avg_pace_s_per_100m,tss,splits,notes"
    ).gte("started_at", cutoff).in_(
        "sport", ["bike", "run", "swim"]
    ).order("started_at", desc=True).limit(10).execute().data or []

    results = []
    from coach.utils.dt import to_rome_date
    for activity in activities:
        _d = to_rome_date(activity.get("started_at"))
        activity_date = _d.isoformat() if _d else str(activity.get("started_at", ""))[:10]
        sport = activity.get("sport")

        # C5: escludi le planned già processate (status='completed'), altrimenti
        # QUALSIASI attività stesso sport nello stesso giorno (es. footing serale)
        # rimatcherebbe il test e sovrascriverebbe la soglia estratta al mattino.
        planned = sb.table("planned_sessions").select("*").eq(
            "planned_date", activity_date
        ).eq("sport", sport).eq(
            "session_type", "fitness_test"
        ).neq("status", "completed").limit(1).execute().data

        if planned:
            logger.info("Matched planned fitness test: %s %s", sport, activity_date)
            # Bug fix audit E5: isola ogni attività — un errore (estrazione, cast,
            # write DB) non deve abortire il processing delle restanti.
            try:
                result = processor.process_fitness_test(activity, planned[0])
                results.append(result)
                # C5: marca la planned session dopo il primo processing riuscito,
                # così le attività successive del giorno non la rimatchano.
                if result.get("status") == "processed" and planned[0].get("id"):
                    try:
                        sb.table("planned_sessions").update({
                            "status": "completed",
                            "completed_activity_id": activity.get("id"),
                        }).eq("id", planned[0]["id"]).execute()
                    except Exception:
                        logger.warning("Impossibile marcare planned test come completed", exc_info=True)
            except Exception as e:  # noqa: BLE001
                logger.exception("Errore processing fitness test per %s", activity.get("external_id"))
                results.append({"status": "error", "activity": activity.get("external_id"), "error": str(e)})
            continue

        name = (activity.get("notes") or activity.get("external_id") or "").lower()
        keywords = ["ftp", "css", "threshold", "soglia", "test", "ramp"]
        if any(kw in name for kw in keywords):
            logger.info("Keyword match (no planned_session): %s — flagging for manual review", name)
            # M4: dedup claim-before-send (l'ingest gira ogni 3h → senza claim
            # la stessa attività genererebbe reinvii a raffica).
            if not processor._claim_notification(f"fittest_keyword_{activity.get('external_id')}"):
                results.append({"status": "keyword_match_manual_review", "activity": activity.get("external_id")})
                continue
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
    parser.add_argument("--manual", action="store_true",
                        help="Inserisce manualmente un risultato test (no auto-estrazione)")
    parser.add_argument("--test-type", help="es. threshold_run_30min, threshold_bike_hr, css_swim_400_200")
    parser.add_argument("--value", type=float, help="risultato: W / sec-per-km / sec-per-100m / bpm")
    parser.add_argument("--date", help="data test YYYY-MM-DD (default: oggi)")
    parser.add_argument("--activity-id", help="id attività sorgente (opzionale)")
    parser.add_argument("--zone-system", help="override zone_system (opzionale)")
    args = parser.parse_args()

    if args.manual:
        if not args.test_type or args.value is None:
            print("Usage: --manual --test-type <type> --value <num> [--date YYYY-MM-DD] [--activity-id ID]")
            return
        proc = FitnessTestProcessor()
        res = proc.commit_manual_result(
            test_type=args.test_type,
            result=args.value,
            test_date=args.date or today_rome().isoformat(),
            activity_id=args.activity_id,
            zone_system=args.zone_system,
        )
        print(json.dumps(res, default=str))
    elif args.check_recent:
        results = check_recent()
        for r in results:
            print(json.dumps(r, default=str))
    else:
        print("Usage: python -m coach.coaching.fitness_test_processor --check-recent | --manual ...")


if __name__ == "__main__":
    main()
