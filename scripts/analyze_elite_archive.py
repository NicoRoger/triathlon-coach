"""Analizza l'archivio FIT dell'atleta dal periodo elite (2021-2022).

Estrae pattern di allenamento: volume settimanale, distribuzione sport,
struttura tipica sessioni, zone HR, intensità. Produce il documento
docs/elite_training_reference.md usato dal coach come linea guida.

Uso: python scripts/analyze_elite_archive.py <path_to_zip>
"""
from __future__ import annotations

import gzip
import io
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path
from zipfile import ZipFile

import fitdecode

SPORT_MAP = {
    "running": "run",
    "cycling": "bike",
    "swimming": "swim",
    "open_water_swimming": "swim",
    "pool_swimming": "swim",
    "lap_swimming": "swim",
    "training": "strength",
    "strength_training": "strength",
    "transition": "transition",
    "generic": "other",
    "multisport": "brick",
}

HR_ZONES = {
    "Z1": (0, 130),
    "Z2": (130, 150),
    "Z3": (150, 165),
    "Z4": (165, 178),
    "Z5": (178, 999),
}


def parse_fit_data(fit_bytes: bytes) -> dict | None:
    try:
        with fitdecode.FitReader(io.BytesIO(fit_bytes)) as fit:
            session = None
            laps = []
            records_hr = []
            records_power = []

            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue

                if frame.name == "session":
                    session = {}
                    for field in frame.fields:
                        session[field.name] = field.value

                elif frame.name == "lap":
                    lap = {}
                    for field in frame.fields:
                        lap[field.name] = field.value
                    laps.append(lap)

                elif frame.name == "record":
                    hr = None
                    power = None
                    for field in frame.fields:
                        if field.name == "heart_rate" and field.value is not None:
                            hr = field.value
                        if field.name == "power" and field.value is not None:
                            power = field.value
                    if hr is not None:
                        records_hr.append(hr)
                    if power is not None:
                        records_power.append(power)

            if session is None:
                return None

            sport_raw = str(session.get("sport", "unknown")).lower()
            sub_sport = str(session.get("sub_sport", "")).lower()
            sport = SPORT_MAP.get(sport_raw, SPORT_MAP.get(sub_sport, "other"))

            start = session.get("start_time")
            if isinstance(start, datetime):
                start_date = start.date()
                start_iso = start.isoformat()
            else:
                return None

            duration_s = session.get("total_timer_time")
            if duration_s is not None:
                duration_s = int(duration_s)

            distance_m = session.get("total_distance")

            avg_hr = session.get("avg_heart_rate")
            max_hr = session.get("max_heart_rate")
            avg_power = session.get("avg_power")

            # HR zone distribution
            hr_zone_seconds = defaultdict(int)
            if records_hr:
                for hr_val in records_hr:
                    for zone_name, (lo, hi) in HR_ZONES.items():
                        if lo <= hr_val < hi:
                            hr_zone_seconds[zone_name] += 1
                            break

            return {
                "sport": sport,
                "start_date": start_date,
                "start_iso": start_iso,
                "duration_s": duration_s,
                "distance_m": distance_m,
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "avg_power": avg_power,
                "laps": len(laps),
                "hr_zone_seconds": dict(hr_zone_seconds),
                "records_count": len(records_hr),
                "power_records": len(records_power),
                "avg_power_records": round(statistics.fmean(records_power)) if records_power else None,
            }
    except Exception as e:
        return None


def process_zip(zip_path: str) -> list[dict]:
    sessions = []
    with ZipFile(zip_path, "r") as zf:
        for entry in zf.namelist():
            if not entry.endswith(".gz"):
                continue
            try:
                compressed = zf.read(entry)
                fit_bytes = gzip.decompress(compressed)
                result = parse_fit_data(fit_bytes)
                if result:
                    sessions.append(result)
            except Exception:
                continue
    return sorted(sessions, key=lambda s: s["start_date"])


def analyze_sessions(sessions: list[dict]) -> dict:
    by_sport = defaultdict(list)
    by_week = defaultdict(list)
    by_weekday = defaultdict(lambda: defaultdict(int))

    for s in sessions:
        sport = s["sport"]
        by_sport[sport].append(s)

        week_start = s["start_date"] - timedelta(days=s["start_date"].weekday())
        by_week[week_start].append(s)

        weekday = s["start_date"].weekday()
        by_weekday[weekday][sport] += 1

    # Weekly volume stats
    weekly_durations = []
    weekly_sessions = []
    weekly_by_sport = defaultdict(list)
    for week, week_sessions in by_week.items():
        total_min = sum((s["duration_s"] or 0) for s in week_sessions) / 60
        weekly_durations.append(total_min)
        weekly_sessions.append(len(week_sessions))
        for sport in set(s["sport"] for s in week_sessions):
            sport_min = sum((s["duration_s"] or 0) for s in week_sessions if s["sport"] == sport) / 60
            weekly_by_sport[sport].append(sport_min)

    # Sport summaries
    sport_stats = {}
    for sport, sport_sessions in by_sport.items():
        durations = [(s["duration_s"] or 0) / 60 for s in sport_sessions]
        hrs = [s["avg_hr"] for s in sport_sessions if s.get("avg_hr")]
        distances = [s["distance_m"] for s in sport_sessions if s.get("distance_m")]

        # HR zone distribution aggregated
        total_zone_secs = defaultdict(int)
        for s in sport_sessions:
            for zone, secs in s.get("hr_zone_seconds", {}).items():
                total_zone_secs[zone] += secs
        total_secs = sum(total_zone_secs.values())
        zone_pcts = {z: round(s / total_secs * 100, 1) for z, s in total_zone_secs.items()} if total_secs > 0 else {}

        sport_stats[sport] = {
            "count": len(sport_sessions),
            "avg_duration_min": round(statistics.fmean(durations), 1) if durations else 0,
            "max_duration_min": round(max(durations), 1) if durations else 0,
            "avg_hr": round(statistics.fmean(hrs)) if hrs else None,
            "avg_distance_km": round(statistics.fmean(distances) / 1000, 1) if distances else None,
            "max_distance_km": round(max(distances) / 1000, 1) if distances else None,
            "hr_zone_pct": zone_pcts,
        }

    # Weekday patterns
    weekday_names = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
    weekday_summary = {}
    for wd in range(7):
        sports_on_day = dict(by_weekday[wd])
        if sports_on_day:
            dominant = max(sports_on_day, key=sports_on_day.get)
            weekday_summary[weekday_names[wd]] = {
                "dominant_sport": dominant,
                "sessions": dict(sports_on_day),
            }

    return {
        "total_sessions": len(sessions),
        "date_range": f"{sessions[0]['start_date']} — {sessions[-1]['start_date']}",
        "weeks_covered": len(by_week),
        "avg_weekly_hours": round(statistics.fmean(weekly_durations) / 60, 1) if weekly_durations else 0,
        "avg_weekly_sessions": round(statistics.fmean(weekly_sessions), 1) if weekly_sessions else 0,
        "max_weekly_hours": round(max(weekly_durations) / 60, 1) if weekly_durations else 0,
        "weekly_by_sport_avg_min": {
            sport: round(statistics.fmean(mins), 0) for sport, mins in weekly_by_sport.items()
        },
        "sport_stats": sport_stats,
        "weekday_patterns": weekday_summary,
    }


def generate_reference_doc(analysis: dict, swim_workouts: str) -> str:
    lines = [
        "# Allenamenti Elite — Riferimento per il Coach",
        "",
        f"*Periodo: {analysis['date_range']}*",
        f"*Sessioni analizzate: {analysis['total_sessions']} su {analysis['weeks_covered']} settimane*",
        "",
        "> Questo documento contiene i pattern di allenamento di Nicolò nel periodo elite",
        "> (ex-azzurro cross triathlon). Il coach li usa come linea guida per la pianificazione,",
        "> adattandoli allo stato attuale (ritorno post-pausa, infortuni attivi, vincoli).",
        "",
        "---",
        "",
        "## Volume settimanale tipico",
        "",
        f"- **Media**: {analysis['avg_weekly_hours']}h/settimana",
        f"- **Picco**: {analysis['max_weekly_hours']}h/settimana",
        f"- **Sessioni/settimana**: {analysis['avg_weekly_sessions']}",
        "",
    ]

    if analysis["weekly_by_sport_avg_min"]:
        lines.append("### Distribuzione media per sport (min/settimana)")
        lines.append("")
        for sport, mins in sorted(analysis["weekly_by_sport_avg_min"].items(), key=lambda x: -x[1]):
            hours = mins / 60
            lines.append(f"- **{sport}**: {mins:.0f} min ({hours:.1f}h)")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Statistiche per sport")
    lines.append("")

    for sport, stats in sorted(analysis["sport_stats"].items(), key=lambda x: -x[1]["count"]):
        if stats["count"] < 3:
            continue
        lines.append(f"### {sport.capitalize()} ({stats['count']} sessioni)")
        lines.append(f"- Durata media: {stats['avg_duration_min']} min")
        lines.append(f"- Durata max: {stats['max_duration_min']} min")
        if stats.get("avg_distance_km"):
            lines.append(f"- Distanza media: {stats['avg_distance_km']} km")
            lines.append(f"- Distanza max: {stats['max_distance_km']} km")
        if stats.get("avg_hr"):
            lines.append(f"- HR media: {stats['avg_hr']} bpm")
        if stats.get("hr_zone_pct"):
            zone_str = " | ".join(f"{z}: {p}%" for z, p in sorted(stats["hr_zone_pct"].items()))
            lines.append(f"- Distribuzione HR: {zone_str}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Weekday patterns
    if analysis["weekday_patterns"]:
        lines.append("## Struttura settimanale tipica (periodo elite)")
        lines.append("")
        for day, info in analysis["weekday_patterns"].items():
            sports = ", ".join(f"{s} ({c}x)" for s, c in sorted(info["sessions"].items(), key=lambda x: -x[1]))
            lines.append(f"- **{day}**: {sports} — sport dominante: {info['dominant_sport']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Swim workouts
    lines.append("## Allenamenti nuoto elite (dettaglio)")
    lines.append("")
    lines.append(swim_workouts.strip())
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Linee guida per il coach")
    lines.append("")
    lines.append("### Come usare questo riferimento")
    lines.append("- Questi dati rappresentano il **livello target a lungo termine**, non il punto di partenza")
    lines.append("- L'atleta è in fase di ritorno post-pausa (2023-2025) con vincoli attivi (spalla dx, fascite sx)")
    lines.append("- Progressione graduale: partire dal 40-50% del volume elite e salire max +10%/settimana")
    lines.append("- La distribuzione HR zona fornisce il modello polarizzato da replicare (80/20)")
    lines.append("- Gli allenamenti nuoto elite servono come template da semplificare (ridurre volume, mantenere struttura)")
    lines.append("")
    lines.append("### Adattamenti rispetto al periodo elite")
    lines.append("- **Nuoto**: volume dimezzato, zero Z4+ per spalla, focus tecnica e drill")
    lines.append("- **Corsa**: volume progressivo (fascite), cap +10%/settimana, terreni morbidi preferiti")
    lines.append("- **Bici**: sport più sicuro per ripresa, volume può crescere più rapidamente")
    lines.append("- **Brick**: da introdurre gradualmente dopo 8+ settimane di base solida")

    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/analyze_elite_archive.py <path_to_zip>")
        sys.exit(1)

    zip_path = sys.argv[1]
    print(f"Parsing FIT files da {zip_path}...")

    sessions = process_zip(zip_path)
    print(f"Parsate {len(sessions)} sessioni")

    if not sessions:
        print("Nessuna sessione trovata!")
        sys.exit(1)

    analysis = analyze_sessions(sessions)

    swim_workouts = """### Legenda nuoto
- SL = stile libero, DO = dorso, MS = misti, ES = esercizi, ESC = esercizi completi
- G = gambe, B = braccia, BL = braccia lente, BP = braccia con palette
- DF = delfino, VE = veloce, NB = nuotato bene, PRG = progressivo
- GC = gambe complete, GB = gambe/braccia, LEG = leggero, P = pull, SOST = sostenuto

### Allenamento 1 — Volume tecnico (~4000m)

**Riscaldamento** (~2200m):
- 700: 100 SL + 100 ES alternati
- 6x50 SL @45"
- 700: 100 MS + 100 SL alternati
- 6x50 @40"
- 4x150 GBC @2'30"

**Serie centrale** (~2700m):
3x (300 SL PRG @4' + 200 SL VE @2'30" + 100 SL NB @1'30")
Poi: 6x50 B @45" (15" pausa) + 8x25 BP @25" (resp 1/4)
Recupero blocco: 40"

**Defaticamento**: 4x150 GESC

### Allenamento 2 — Velocità + serie (~3500m)

**Attivazione**: 15x50 (5 @50" + 5 @45" + 5 @40")
**Velocità**: 10x25 (5 DF @30" + 5 SL @25", resp 1/5)
**Tecnica**: 400B + 300G + 200B + 100G

**Serie centrale** (piramidale):
6x100 @1'20" + 4x200 @2'40" + 4x100 @1'20" + 2x200 @2'40" + 2x100 @1'20"
Schema: 100 veloci, 200 regolari

**Chiusura**: 400G + 300B + 200G + 100B + 8x50 B @45" NB (resp 1/4) + 100 ES"""

    doc = generate_reference_doc(analysis, swim_workouts)

    output_path = Path(__file__).resolve().parent.parent / "docs" / "elite_training_reference.md"
    output_path.write_text(doc, encoding="utf-8")
    print(f"\nDocumento generato: {output_path}")

    # Print summary
    print(f"\n=== Riepilogo ===")
    print(f"Sessioni: {analysis['total_sessions']}")
    print(f"Periodo: {analysis['date_range']}")
    print(f"Volume medio: {analysis['avg_weekly_hours']}h/sett")
    print(f"Sessioni/sett: {analysis['avg_weekly_sessions']}")
    for sport, stats in analysis["sport_stats"].items():
        print(f"  {sport}: {stats['count']} sessioni, media {stats['avg_duration_min']}min")


if __name__ == "__main__":
    main()
