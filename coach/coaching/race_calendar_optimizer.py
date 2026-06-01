"""Fase 3.2 — Race calendar optimization (multi-horizon planning).

Dato un set di gare future (A, B, C), produce un piano annuale/multi-mesociclo
con picchi di CTL allineati alle gare A e gare B/C usate come tappe di build.

Output: macro-plan con elenco mesocicli proposti (start, end, phase, target CTL)
che il sistema può poi committare in `mesocycles` table via skill `generate_mesocycle`.

Costo: ZERO LLM. Solo logica rule-based su date e periodizzazione.

Use cases:
1. Setup inizio stagione: input gare → output calendario mesocicli
2. Insert nuova gara mid-season: ricalcolo dei mesocicli successivi
3. Check coerenza: alert se 2 gare A troppo vicine (peak overlap impossibile)

Principi applicati:
- Tapering: 10-14gg pre-gara A, 7gg pre-gara B [source: Mujika & Padilla 2003]
- Block periodization: 3-4 settimane di carico + 1 di scarico [source: Issurin 2008]
- Build progression: max +5-7 CTL/sett medio in fase build [source: Friel TrainingPeaks]
- Recovery post-A: minimo 7-10gg easy + 1 settimana di rebuild
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Optional

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Config
# ============================================================================

# Settimane minime per peak verso una gara A
TAPER_WEEKS_A = 2
TAPER_WEEKS_B = 1

# Build settimane min/max prima del taper
BUILD_WEEKS_MIN = 3
BUILD_WEEKS_MAX = 6

# Recovery post-gara A
RECOVERY_WEEKS_A = 1
REBUILD_WEEKS_A = 1

# Gap minimo tra 2 gare A perché abbiano peak indipendenti
MIN_WEEKS_BETWEEN_A_PEAKS = 6


@dataclass
class MesoSlot:
    """Slot di mesociclo proposto nel calendario."""
    start_date: str
    end_date: str
    phase: str           # base / build / specific / peak / taper / recovery
    weeks: int
    target_ctl_delta: float = 0.0  # +X CTL atteso (negativo per scarico/taper)
    related_race_id: Optional[str] = None
    related_race_name: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CalendarPlan:
    season_year: int
    today: str
    horizon_end: str
    races_considered: list[dict]
    mesocycles: list[MesoSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "season_year": self.season_year,
            "today": self.today,
            "horizon_end": self.horizon_end,
            "races_considered": self.races_considered,
            "mesocycles": [m.to_dict() for m in self.mesocycles],
            "warnings": self.warnings,
        }


# ============================================================================
# Loaders
# ============================================================================

def _fetch_future_races(today: date, horizon_days: int = 365) -> list[dict]:
    sb = get_supabase()
    until = today + timedelta(days=horizon_days)
    res = (
        sb.table("races")
        .select("id,name,race_date,priority,distance,location,season_year")
        .gte("race_date", today.isoformat())
        .lte("race_date", until.isoformat())
        .order("race_date", desc=False)
        .execute()
    )
    return res.data or []


def _fetch_current_ctl(today: date) -> Optional[float]:
    sb = get_supabase()
    res = (
        sb.table("daily_metrics")
        .select("ctl")
        .lte("date", today.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if res.data and res.data[0].get("ctl") is not None:
        return float(res.data[0]["ctl"])
    return None


# ============================================================================
# Optimization logic
# ============================================================================

def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _add_meso(plan: CalendarPlan, start: date, weeks: int, phase: str,
              ctl_delta: float = 0.0, race_id: Optional[str] = None,
              race_name: Optional[str] = None, notes: Optional[str] = None) -> date:
    """Aggiunge un mesociclo al piano. Ritorna data fine (esclusiva, prossimo inizio)."""
    end = start + timedelta(weeks=weeks) - timedelta(days=1)
    plan.mesocycles.append(MesoSlot(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        phase=phase,
        weeks=weeks,
        target_ctl_delta=ctl_delta,
        related_race_id=race_id,
        related_race_name=race_name,
        notes=notes,
    ))
    return end + timedelta(days=1)


def optimize_calendar(today: Optional[date] = None, horizon_days: int = 365) -> CalendarPlan:
    """Produce un calendario mesocicli per le gare future entro horizon_days."""
    today = today or today_rome()
    races = _fetch_future_races(today, horizon_days)
    plan = CalendarPlan(
        season_year=today.year,
        today=today.isoformat(),
        horizon_end=(today + timedelta(days=horizon_days)).isoformat(),
        races_considered=races,
    )
    if not races:
        plan.warnings.append("Nessuna gara futura nel calendario — proponi prima di pianificare.")
        return plan

    # Check overlap fra gare A
    races_A = [r for r in races if r["priority"] == "A"]
    for i in range(len(races_A) - 1):
        d1 = date.fromisoformat(races_A[i]["race_date"])
        d2 = date.fromisoformat(races_A[i + 1]["race_date"])
        gap_weeks = (d2 - d1).days // 7
        if gap_weeks < MIN_WEEKS_BETWEEN_A_PEAKS:
            plan.warnings.append(
                f"Gare A troppo vicine ({races_A[i]['name']} → {races_A[i+1]['name']}, "
                f"{gap_weeks} settimane). Picchi indipendenti difficili: considera "
                f"trattare la seconda come B."
            )

    # Cursore: lunedì successivo a oggi
    cursor = _monday_of(today) + timedelta(days=7)
    current_ctl = _fetch_current_ctl(today)
    if current_ctl is None:
        plan.warnings.append("CTL attuale non disponibile (no daily_metrics). Stima 25.")
        current_ctl = 25.0

    # Pianifica per ogni gara in ordine cronologico
    for race in races:
        race_date = date.fromisoformat(race["race_date"])
        race_monday = _monday_of(race_date)
        priority = race["priority"]

        if priority == "A":
            taper_weeks = TAPER_WEEKS_A
        elif priority == "B":
            taper_weeks = TAPER_WEEKS_B
        else:  # C → no taper dedicato, gara usata come tappa
            taper_weeks = 0

        # Build a ritroso: taper precede race, build precede taper
        # Taper inizia (race_monday - taper_weeks settimane)
        taper_start = race_monday - timedelta(weeks=taper_weeks)
        # Settimane disponibili per build dalla data corrente cursor a taper_start
        weeks_available = max(0, (taper_start - cursor).days // 7)

        if weeks_available < BUILD_WEEKS_MIN and priority in {"A", "B"}:
            plan.warnings.append(
                f"Tempo insufficiente per build verso {race['name']} ({weeks_available} sett. "
                f"disponibili, min {BUILD_WEEKS_MIN}). Considera taper più corto o gara declassata."
            )

        # Determina fase mesocicli da inserire
        # - Se distanza > 12 sett: base + build + specific + taper
        # - Se 8-12 sett: build + specific + taper
        # - Se 5-7 sett: build/specific + taper
        # - Se < 5 sett: solo taper
        # Numeri tarati per atleta endurance esperto.

        if priority == "C":
            # Nessuna pianificazione dedicata — usa la gara C come BRT (race-pace simulation)
            # senza taper, ma annota
            continue

        if weeks_available >= 9:
            # Build (3-4 sett) + Specific (3-4 sett) + Taper
            build_w = min(BUILD_WEEKS_MAX, max(BUILD_WEEKS_MIN, weeks_available // 2))
            cursor = _add_meso(plan, cursor, build_w, "build",
                               ctl_delta=+5 * build_w,
                               notes=f"Build verso {race['name']}")
            spec_w = max(BUILD_WEEKS_MIN, weeks_available - build_w)
            cursor = _add_meso(plan, cursor, spec_w, "specific",
                               ctl_delta=+3 * spec_w,
                               race_id=race["id"], race_name=race["name"],
                               notes=f"Specifico per {race['name']} (race-pace)")
        elif weeks_available >= 5:
            spec_w = weeks_available
            cursor = _add_meso(plan, cursor, spec_w, "specific",
                               ctl_delta=+3 * spec_w,
                               race_id=race["id"], race_name=race["name"],
                               notes=f"Specifico per {race['name']}")
        elif weeks_available > 0:
            # Solo brevissimo specifico/taper
            cursor = _add_meso(plan, cursor, weeks_available, "specific",
                               ctl_delta=+1 * weeks_available,
                               race_id=race["id"], race_name=race["name"],
                               notes=f"Specifico breve per {race['name']}")

        # Taper
        if taper_weeks > 0:
            cursor = _add_meso(plan, cursor, taper_weeks, "taper",
                               ctl_delta=-2 * taper_weeks,
                               race_id=race["id"], race_name=race["name"],
                               notes=f"Taper {taper_weeks}sett verso {race['name']} [Mujika 2003]")

        # Race-week pseudo-event: cursor avanza a settimana successiva alla gara.
        # Bug fix audit H3: usa max(cursor, ...) per non far MAI tornare indietro
        # il cursore. Se build+spec+taper hanno superato race_monday (over-alloc
        # da arrotondamenti), un reset secco creerebbe mesocicli sovrapposti.
        cursor = max(cursor, race_monday + timedelta(weeks=1))

        # Recovery + rebuild post-gara A (1+1 sett)
        if priority == "A":
            cursor = _add_meso(plan, cursor, RECOVERY_WEEKS_A, "recovery",
                               ctl_delta=-8,
                               notes=f"Recovery post-{race['name']}")
            cursor = _add_meso(plan, cursor, REBUILD_WEEKS_A, "base",
                               ctl_delta=+2,
                               notes="Rebuild post-recovery")

    # Se rimangono >= 4 settimane prima di horizon_end senza gare, aggiungi base maintenance
    horizon = date.fromisoformat(plan.horizon_end)
    if (horizon - cursor).days >= 28:
        weeks_left = (horizon - cursor).days // 7
        weeks_block = min(weeks_left, 8)
        _add_meso(plan, cursor, weeks_block, "base",
                  ctl_delta=+2 * weeks_block,
                  notes="Base maintenance off-season")

    return plan


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    plan = optimize_calendar()
    print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
