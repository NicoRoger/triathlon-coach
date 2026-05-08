"""Commit settimana 07/05 → 13/05 2026 su tabella planned_sessions.

Generato da weekly review del 2026-05-06.
Razionale completo: vedi conversazione coach + entry training_journal del 06/05/26.

Idempotente: se rieseguito, cancella le sessioni con planned_date in [07/05, 13/05]
e le reinserisce.
"""
from __future__ import annotations

from coach.utils.supabase_client import get_supabase

WEEK = [
    {
        "planned_date": "2026-05-07",
        "sport": "swim",
        "session_type": "technique",
        "duration_s": 3000,  # 50'
        "target_tss": 25,
        "target_zones": {"z1": 0.7, "z2": 0.3},
        "description": (
            "Nuoto tecnica + drill 50'.\n"
            "Warm-up: 200m sciolto + 200m mix.\n"
            "Main: 6×100m drill bracciata (gomito alto, no spinta forzata) R20\" / "
            "4×50m gambata sciolta R30\" / 4×50m a sentimento neutro.\n"
            "Cool-down: 200m easy.\n"
            "Vincolo spalla: zero Z4+. Se RPE spalla > 5 → stop.\n"
            "Razionale: continuità tecnica, moltiplicatore di efficienza."
        ),
    },
    {
        "planned_date": "2026-05-08",
        "sport": "run",
        "session_type": "z2_aerobic",
        "duration_s": 2700,  # 45'
        "target_tss": 40,
        "target_zones": {"z1": 0.3, "z2": 0.7},
        "description": (
            "Z2 corsa 45' (~7km).\n"
            "8' warm-up Z1 / 30' Z2 (HR 145-155) / 7' cool-down Z1.\n"
            "Vincolo fascite: terreno pianeggiante. Se stiramento plantare > 4/10 → "
            "riduci a 30' o stop.\n"
            "Successo: HR sotto 158 in tutto il blocco. Fascite asintomatica a sera."
        ),
    },
    {
        "planned_date": "2026-05-09",
        "sport": "bike",
        "session_type": "z2_long",
        "duration_s": 6300,  # 1h45 (mid del range 1h45-2h)
        "target_tss": 120,
        "target_zones": {"z1": 0.2, "z2": 0.8},
        "description": (
            "Lungo Z2 bici 1h45-2h.\n"
            "15' warm-up Z1 / 1h15-1h30 Z2 continuo (no salite > 5min sopra Z2) / "
            "15' cool-down Z1.\n"
            "Razionale: stimolo aerobico principale della settimana. Bici zero-impact "
            "per fascite.\n"
            "Successo: chiusura sensazione 'potevo fare 30' in più'. Se gambe "
            "pesanti già al 45' → tronca a 1h30."
        ),
    },
    {
        "planned_date": "2026-05-10",
        "sport": "other",
        "session_type": "rest_day",
        "duration_s": 0,
        "target_tss": 0,
        "target_zones": {},
        "description": (
            "Recovery / off.\n"
            "HRV check al risveglio: se z > 0 e gambe ok, opzionale 20-30' Z1 a "
            "sentimento (camminata o bici easy).\n"
            "Se HRV < 0 o gambe pesanti, off totale.\n"
            "Decisione finale a sentimento la mattina."
        ),
    },
    {
        "planned_date": "2026-05-11",
        "sport": "run",
        "session_type": "z2_aerobic",
        "duration_s": 2700,  # 45'
        "target_tss": 40,
        "target_zones": {"z1": 0.3, "z2": 0.7},
        "description": (
            "Z2 corsa 45' (~7km) — TBD parametri precisi sab 09/05 sera.\n"
            "Indicativo: stesso schema di venerdì 08/05.\n"
            "Vincolo fascite: cumulato settimana ≤ 14km."
        ),
    },
    {
        "planned_date": "2026-05-12",
        "sport": "swim",
        "session_type": "technique",
        "duration_s": 3000,  # 50'
        "target_tss": 25,
        "target_zones": {"z1": 0.7, "z2": 0.3},
        "description": (
            "Nuoto tecnica + gambata 50' — TBD parametri precisi a metà settimana.\n"
            "Indicativo: rotazione drill diversi da giovedì (focus gambata e respirazione "
            "bilaterale).\n"
            "Vincolo spalla: zero Z4+."
        ),
    },
    {
        "planned_date": "2026-05-13",
        "sport": "bike",
        "session_type": "z2_medium",
        "duration_s": 4200,  # 1h10
        "target_tss": 75,
        "target_zones": {"z1": 0.2, "z2": 0.8},
        "description": (
            "Bici Z2 medio 1h-1h15 — TBD parametri precisi mar 12/05 sera.\n"
            "Indicativo: tutto Z2 continuo, no qualità."
        ),
    },
]


def main():
    sb = get_supabase()

    dates = [s["planned_date"] for s in WEEK]
    print(f"Pulizia eventuali planned_sessions esistenti per: {dates[0]} → {dates[-1]}")
    deleted = (
        sb.table("planned_sessions")
        .delete()
        .gte("planned_date", dates[0])
        .lte("planned_date", dates[-1])
        .execute()
    )
    print(f"  Cancellate: {len(deleted.data)} righe")

    print(f"\nInserimento {len(WEEK)} sessioni:")
    for s in WEEK:
        row = {
            "planned_date": s["planned_date"],
            "sport": s["sport"],
            "session_type": s["session_type"],
            "duration_s": s["duration_s"],
            "target_tss": s["target_tss"],
            "target_zones": s["target_zones"],
            "description": s["description"],
            "status": "planned",
        }
        res = sb.table("planned_sessions").insert(row).execute()
        inserted_id = res.data[0]["id"] if res.data else "?"
        print(
            f"  {s['planned_date']} {s['sport']:6s} "
            f"{s['session_type']:14s} dur={s['duration_s']:>5d}s "
            f"tss={s['target_tss']:>4d} id={inserted_id[:8]}"
        )

    print("\nVerifica finale:")
    check = (
        sb.table("planned_sessions")
        .select("planned_date,sport,session_type,duration_s,target_tss,status")
        .gte("planned_date", dates[0])
        .lte("planned_date", dates[-1])
        .order("planned_date")
        .execute()
    )
    for r in check.data:
        print(
            f"  {r['planned_date']} {r['sport']:6s} {r['session_type']:14s} "
            f"dur={r['duration_s']}s tss={r['target_tss']} status={r['status']}"
        )


if __name__ == "__main__":
    main()
