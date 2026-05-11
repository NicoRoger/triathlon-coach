"""Blocco 3.3 — Auto-update CLAUDE.md §4 (stato corrente) da daily_metrics.

Legge daily_metrics ultimo giorno + physiology_zones correnti.
Aggiorna §4 con CTL, TSB, HRV z-score, fase corrente.
Committa solo se cambio > 5% o cambio fase.

Uso: python scripts/update_claude_md_status.py
Integrato nel workflow pattern-extraction (domenica notte).
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _get_latest_metrics() -> dict | None:
    from coach.utils.supabase_client import get_supabase
    from coach.utils.dt import today_rome

    sb = get_supabase()
    today = today_rome()
    for offset in range(3):
        d = (today - timedelta(days=offset)).isoformat()
        res = sb.table("daily_metrics").select("*").eq("date", d).execute()
        if res.data:
            return res.data[0]
    return None


def _determine_phase(ctl: float | None, tsb: float | None, race_date: date | None, today: date) -> str:
    """Determina fase di allenamento da CTL, TSB e vicinanza gara."""
    if race_date:
        weeks = (race_date - today).days // 7
        if weeks <= 0:
            return "race_week"
        if weeks <= 2:
            return "taper"
        if weeks <= 4:
            return "peak"
        if weeks <= 8:
            return "specifico"
        if weeks <= 12:
            return "build"

    if ctl is not None:
        if ctl < 20:
            return "base"
        if ctl < 40:
            return "build"
        return "specifico"

    return "base"


def _get_next_race_date() -> date | None:
    from coach.utils.supabase_client import get_supabase
    from coach.utils.dt import today_rome

    sb = get_supabase()
    today = today_rome()
    res = sb.table("races").select("race_date").gte(
        "race_date", today.isoformat()
    ).eq("priority", "A").order("race_date").limit(1).execute()
    if res.data:
        return date.fromisoformat(res.data[0]["race_date"])
    return None


def build_status_yaml(metrics: dict, phase: str) -> str:
    today_iso = metrics.get("date", date.today().isoformat())
    ctl = metrics.get("ctl")
    atl = metrics.get("atl")
    tsb = metrics.get("tsb")
    hrv_z = metrics.get("hrv_z_score")
    readiness = metrics.get("readiness_score")
    readiness_label = metrics.get("readiness_label", "?")

    lines = [
        f"data_aggiornamento: {today_iso}",
        f"fase_corrente: {phase}",
    ]
    if ctl is not None:
        lines.append(f"ctl: {ctl}")
    if atl is not None:
        lines.append(f"atl: {atl}")
    if tsb is not None:
        lines.append(f"tsb: {tsb}")
    if hrv_z is not None:
        lines.append(f"hrv_z_score: {hrv_z}")
    if readiness is not None:
        lines.append(f"readiness: {readiness}/100 ({readiness_label})")

    lines.append(f"note_fase: |")
    lines.append(f"  Aggiornato automaticamente da update_claude_md_status.py")

    return "\n".join(lines)


def _extract_current_status(content: str) -> str | None:
    """Estrae il blocco yaml corrente da §4."""
    m = re.search(r"```yaml\ndata_aggiornamento:.*?```", content, re.DOTALL)
    if m:
        return m.group(0)
    return None


def _should_update(old_yaml: str | None, new_yaml: str) -> bool:
    """Aggiorna solo se cambio significativo (>5% su metriche o cambio fase)."""
    if old_yaml is None:
        return True

    old_ctl = re.search(r"ctl:\s*([\d.]+)", old_yaml)
    new_ctl = re.search(r"ctl:\s*([\d.]+)", new_yaml)
    if old_ctl and new_ctl:
        old_v = float(old_ctl.group(1))
        new_v = float(new_ctl.group(1))
        if old_v > 0 and abs(new_v - old_v) / old_v > 0.05:
            return True

    old_phase = re.search(r"fase_corrente:\s*(\w+)", old_yaml)
    new_phase = re.search(r"fase_corrente:\s*(\w+)", new_yaml)
    if old_phase and new_phase and old_phase.group(1) != new_phase.group(1):
        return True

    old_date = re.search(r"data_aggiornamento:\s*([\d-]+)", old_yaml)
    new_date = re.search(r"data_aggiornamento:\s*([\d-]+)", new_yaml)
    if old_date and new_date:
        old_d = date.fromisoformat(old_date.group(1))
        new_d = date.fromisoformat(new_date.group(1))
        if (new_d - old_d).days >= 7:
            return True

    return False


def update_claude_md() -> bool:
    """Aggiorna §4 di CLAUDE.md. Ritorna True se aggiornato."""
    metrics = _get_latest_metrics()
    if not metrics:
        logger.info("No daily_metrics found, skipping CLAUDE.md update")
        return False

    from coach.utils.dt import today_rome
    today = today_rome()
    race_date = _get_next_race_date()
    phase = _determine_phase(metrics.get("ctl"), metrics.get("tsb"), race_date, today)
    new_yaml = build_status_yaml(metrics, phase)

    content = CLAUDE_MD.read_text(encoding="utf-8")
    old_yaml = _extract_current_status(content)

    if not _should_update(old_yaml, new_yaml):
        logger.info("No significant change, skipping CLAUDE.md update")
        return False

    new_block = f"```yaml\n{new_yaml}\n```"
    if old_yaml:
        content = content.replace(old_yaml, new_block)
    else:
        placeholder = "```yaml\ndata_aggiornamento: YYYY-MM-DD"
        idx = content.find(placeholder)
        if idx >= 0:
            end = content.find("```", idx + 10)
            if end >= 0:
                content = content[:idx] + new_block + content[end + 3:]

    CLAUDE_MD.write_text(content, encoding="utf-8")
    logger.info("CLAUDE.md §4 updated: phase=%s, CTL=%s", phase, metrics.get("ctl"))
    return True


def main() -> None:
    try:
        from dotenv import load_dotenv; load_dotenv()
    except ImportError:
        pass

    sys.path.insert(0, str(ROOT))
    updated = update_claude_md()
    if updated:
        print("CLAUDE.md §4 aggiornato")
    else:
        print("Nessun aggiornamento necessario")


if __name__ == "__main__":
    main()
