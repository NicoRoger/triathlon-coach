"""Genera docs/athlete_anamnesis.md interamente dal DB.

Sostituisce i patch regex su CLAUDE.md (fitness_test_processor._update_claude_md
e scripts/update_claude_md_status.py, rimossi): il DB è l'unica fonte di
verità, questo file è una VISTA rigenerata da zero ad ogni run — niente
doppia verità, niente regex fragili, niente conflitti git su patch parziali.

Trigger: dopo ogni fitness test processato (ingest) e nel cron domenicale
(pattern-extraction). Il commit avviene nei workflow, solo se il contenuto
è cambiato. Il file NON contiene timestamp di generazione: le date derivano
dai dati stessi, così rigenerare senza cambi di dato produce zero diff.

Uso: python scripts/generate_anamnesis.py
     oppure from scripts.generate_anamnesis import generate_anamnesis
"""
from __future__ import annotations

import logging
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANAMNESIS_PATH = ROOT / "docs" / "athlete_anamnesis.md"

logger = logging.getLogger(__name__)

SEVERITY_ITA = {"low": "bassa", "medium": "media", "high": "alta", "critical": "critica"}
STATUS_ITA = {
    "symptomatic": "sintomatico",
    "asymptomatic": "asintomatico",
    "recovering": "in recupero (via libera progressivo)",
}


def _fmt_pace(s_per_km: float) -> str:
    m, s = divmod(round(s_per_km), 60)
    return f"{m}:{s:02d}/km"


def _fmt_swim(s_per_100m: float) -> str:
    m, s = divmod(round(s_per_100m), 60)
    return f"{m}:{s:02d}/100m"


def _zones_section(sb) -> tuple[list[str], list[str]]:
    """Ritorna (righe sezione zone correnti, righe storico test)."""
    from coach.coaching.fitness_test_processor import derive_zones_for_discipline

    res = (
        sb.table("physiology_zones")
        .select("discipline,valid_from,valid_to,ftp_w,threshold_pace_s_per_km,"
                "css_pace_s_per_100m,lthr,hr_max,method")
        .order("valid_from", desc=True)
        .execute()
    )
    rows = res.data or []

    lines = ["## Soglie e zone correnti (misurate)"]
    seen: set[str] = set()
    for r in rows:  # già ordinate desc: la prima per disciplina è l'attiva
        d = r["discipline"]
        if d in seen or r.get("valid_to") is not None:
            continue
        seen.add(d)

        header_bits = []
        if r.get("lthr"):
            header_bits.append(f"LTHR {int(r['lthr'])} bpm")
        if r.get("threshold_pace_s_per_km"):
            header_bits.append(f"soglia {_fmt_pace(r['threshold_pace_s_per_km'])}")
        if r.get("css_pace_s_per_100m"):
            header_bits.append(f"CSS {_fmt_swim(r['css_pace_s_per_100m'])}")
        if r.get("ftp_w"):
            header_bits.append(f"FTP {int(r['ftp_w'])}W")
        if r.get("hr_max"):
            header_bits.append(f"HRmax {int(r['hr_max'])}")

        lines.append("")
        lines.append(f"### {d.capitalize()} — {' | '.join(header_bits) or 'nessun valore'}")
        lines.append(f"*Metodo: {r.get('method') or 'n/d'} — valido dal {r['valid_from']}*")

        zones = derive_zones_for_discipline(
            d,
            ftp_w=r.get("ftp_w"),
            threshold_pace_s_per_km=r.get("threshold_pace_s_per_km"),
            css_pace_s_per_100m=r.get("css_pace_s_per_100m"),
            lthr=r.get("lthr"),
        )
        for zname, zval in zones.items():
            lines.append(f"- {zname}: {zval}")

    history = ["## Storico test fisiologici", "", "| Data | Disciplina | Metodo |", "|---|---|---|"]
    for r in rows:
        method = (r.get("method") or "n/d").split(".")[0][:90]
        history.append(f"| {r['valid_from']} | {r['discipline']} | {method} |")

    return lines, history


def _constraints_section(sb) -> list[str]:
    res = (
        sb.table("active_constraints")
        .select("type,discipline,description,severity,symptom_status,note,created_at,resolved_at")
        .is_("resolved_at", "null")
        .order("created_at")
        .execute()
    )
    lines = ["## Vincoli medici attivi"]
    for c in res.data or []:
        sev = SEVERITY_ITA.get(c.get("severity") or "", c.get("severity") or "n/d")
        stat = STATUS_ITA.get(c.get("symptom_status") or "", c.get("symptom_status") or "stato n/d")
        lines.append("")
        lines.append(f"### {c['discipline']} — severità {sev}, {stat}")
        lines.append(c.get("description") or "")
        if c.get("note"):
            lines.append(f"*Nota: {c['note']}*")
    if len(lines) == 1:
        lines.append("")
        lines.append("Nessun vincolo attivo.")
    return lines


def _training_state_section(sb) -> list[str]:
    from coach.utils.dt import today_rome

    today = today_rome()
    lines = ["## Stato allenamento corrente"]

    meso_res = (
        sb.table("mesocycles")
        .select("name,phase,start_date,end_date,progression_plan")
        .lte("start_date", today.isoformat())
        .gte("end_date", today.isoformat())
        .order("start_date", desc=True)
        .limit(1)
        .execute()
    )
    meso = (meso_res.data or [None])[0]
    if meso:
        weeks_total = ((_d(meso["end_date"]) - _d(meso["start_date"])).days // 7) + 1
        week_n = ((today - _d(meso["start_date"])).days // 7) + 1
        lines.append("")
        lines.append(f"Mesociclo: **{meso['name']}** (fase {meso['phase']}) — "
                     f"settimana {week_n} di {weeks_total} ({meso['start_date']} → {meso['end_date']})")
        plan = meso.get("progression_plan") or {}
        wk = f"week{week_n}"
        steps = {k: v.get(wk) for k, v in plan.items() if isinstance(v, dict) and v.get(wk)}
        for k, v in sorted(steps.items()):
            lines.append(f"- {k}: {v}")
    else:
        lines.append("")
        lines.append("Nessun mesociclo attivo.")

    # Ultima riga metrica con PMC popolato (max 7gg indietro)
    for offset in range(7):
        d_iso = (today - timedelta(days=offset)).isoformat()
        m_res = sb.table("daily_metrics").select("date,ctl,atl,tsb,readiness_score,readiness_label").eq("date", d_iso).execute()
        m = (m_res.data or [None])[0]
        if m and m.get("ctl") is not None:
            lines.append("")
            lines.append(f"Carico al {m['date']}: CTL {m['ctl']} | ATL {m['atl']} | TSB {m['tsb']}"
                         + (f" | readiness {m['readiness_score']}/100 ({m.get('readiness_label')})"
                            if m.get("readiness_score") is not None else ""))
            break

    race_res = (
        sb.table("races")
        .select("name,race_date,priority,location")
        .gte("race_date", today.isoformat())
        .order("race_date")
        .limit(3)
        .execute()
    )
    if race_res.data:
        lines.append("")
        lines.append("Prossime gare:")
        for r in race_res.data:
            days = (_d(r["race_date"]) - today).days
            lines.append(f"- {r['race_date']} ({days}gg): {r['name']} [{r.get('priority') or '?'}] — {r.get('location') or ''}")
    return lines


def _beliefs_section(sb) -> list[str]:
    res = (
        sb.table("beliefs")
        .select("belief_text,status,confidence,evidence_n")
        .eq("flagged", False)
        .neq("status", "retired")
        .in_("status", ["weak_belief", "validated_belief", "strong_belief"])
        .order("confidence", desc=True)
        .limit(15)
        .execute()
    )
    lines = ["## Pattern osservati (belief non flaggate, weak+)"]
    for b in res.data or []:
        lines.append(f"- [{b['status']} n={b['evidence_n']} conf={b['confidence']:.2f}] {b['belief_text']}")
    if len(lines) == 1:
        lines.append("Nessuna belief consolidata al momento.")
    return lines


def _baselines_section(sb) -> list[str]:
    from coach.utils.dt import today_rome

    today = today_rome()
    since = (today - timedelta(days=28)).isoformat()
    res = (
        sb.table("daily_wellness")
        .select("resting_hr,hrv_rmssd")
        .gte("date", since)
        .lte("date", today.isoformat())
        .execute()
    )
    rows = res.data or []
    rhr = sorted(r["resting_hr"] for r in rows if r.get("resting_hr") is not None)
    hrv = [r["hrv_rmssd"] for r in rows if r.get("hrv_rmssd") is not None]
    lines = ["## Baseline fisiologiche (finestra 28gg)"]
    if rhr:
        lines.append(f"- HR riposo: {rhr[len(rhr) // 2]} bpm tipica (range {rhr[0]}-{rhr[-1]})")
    if hrv:
        lines.append(f"- HRV rMSSD baseline: {round(sum(hrv) / len(hrv))} ms (n={len(hrv)})")
    if len(lines) == 1:
        lines.append("Dati wellness insufficienti.")
    return lines


def _d(iso: str):
    from datetime import date
    return date.fromisoformat(iso)


def build_anamnesis() -> str:
    from coach.utils.supabase_client import get_supabase

    sb = get_supabase()
    zones, test_history = _zones_section(sb)
    parts = [
        "# Anamnesi Atleta — Nicolò Ruggero",
        "",
        "> FILE GENERATO AUTOMATICAMENTE da `scripts/generate_anamnesis.py` — non modificare a mano:",
        "> ogni run lo riscrive da zero. Fonte di verità: il database (physiology_zones,",
        "> active_constraints, mesocycles, beliefs, daily_metrics/wellness).",
        "> Profilo statico, storia e pattern mentali restano in CLAUDE.md §2.",
        "",
        "\n".join(zones),
        "",
        "\n".join(_constraints_section(sb)),
        "",
        "\n".join(_training_state_section(sb)),
        "",
        "\n".join(_baselines_section(sb)),
        "",
        "\n".join(_beliefs_section(sb)),
        "",
        "\n".join(test_history),
        "",
    ]
    return "\n".join(parts)


def generate_anamnesis() -> bool:
    """Rigenera il file. Ritorna True se il contenuto è cambiato."""
    content = build_anamnesis()
    old = ANAMNESIS_PATH.read_text(encoding="utf-8") if ANAMNESIS_PATH.exists() else None
    if content == old:
        logger.info("Anamnesi invariata, nessuna scrittura")
        return False
    ANAMNESIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANAMNESIS_PATH.write_text(content, encoding="utf-8")
    logger.info("Anamnesi rigenerata: %s", ANAMNESIS_PATH)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    sys.path.insert(0, str(ROOT))
    changed = generate_anamnesis()
    print("Anamnesi aggiornata" if changed else "Anamnesi invariata")


if __name__ == "__main__":
    main()
