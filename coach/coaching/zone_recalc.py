"""WP3 — Riallinea i range HR nelle prescrizioni future quando cambiano le zone.

Le descrizioni delle planned_sessions contengono range HR scritti nel testo
("25' Z2 (HR 138-155)"): quando physiology_zones cambia (nuovo test o commit
manuale), le sessioni già committate resterebbero coi numeri vecchi. Questo
modulo riscrive SOLO la parte numerica dei range riconoscibili nelle sessioni
future non completate — mai la struttura dell'allenamento.

Formato riconoscibile (già usato di fatto dal coach nelle prescrizioni):
    Zn ... (HR a-b ...)   oppure   Z1 ... (HR <a ...)   oppure   Z5 ... (HR >a ...)
con la parentesi sulla stessa riga della label di zona.

Limiti espliciti (v1):
- Solo HR per run/bike (la valuta di intensità primaria di questo atleta,
  senza wattmetro). I pace nel testo (es. "~5:30/km") NON vengono toccati.
- sport='brick' saltato: la descrizione mescola range bici e corsa con due
  LTHR diverse — riscriverli alla cieca farebbe danni. Loggato, non silente.
"""
from __future__ import annotations

import logging
import re

from coach.utils.dt import today_rome
from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Z<num> seguito (stessa riga, max 40 char, senza aprire altre parentesi)
# da "(HR <numeri>": si riscrive solo lo span numerico, il resto della
# parentesi (", ~5:30/km", ", LTHR 170") resta intatto.
_ZONE_HR_RE = re.compile(
    r"(?P<prefix>Z(?P<zn>[1-5])[^\n()]{0,40}?\(HR\s*)(?P<range><?\s*\d+(?:\s*-\s*\d+)?|>\s*\d+)"
)


def _bounds_from_lthr(lthr: int) -> dict[int, str]:
    """Range testuali per zona dai confini contigui di _compute_lthr_5zone
    (stessi moltiplicatori 0.81/0.89/0.95 — unica fonte di verità matematica)."""
    b1 = round(lthr * 0.81)
    b2 = round(lthr * 0.89)
    b3 = round(lthr * 0.95)
    return {1: f"<{b1}", 2: f"{b1}-{b2}", 3: f"{b2}-{b3}", 4: f"{b3}-{lthr}", 5: f">{lthr}"}


def rewrite_description(description: str, lthr: int) -> str:
    """Riscrive i range HR riconoscibili in una descrizione. Pura, testabile."""
    bounds = _bounds_from_lthr(lthr)

    def _sub(m: re.Match) -> str:
        return m.group("prefix") + bounds[int(m.group("zn"))]

    return _ZONE_HR_RE.sub(_sub, description)


def recalc_future_sessions(discipline: str) -> int:
    """Riallinea le planned_sessions future del sport alla zona attiva corrente.

    Ritorna il numero di sessioni aggiornate. Non tocca: sessioni passate,
    status != planned, sport brick, discipline senza LTHR attiva (es. swim).
    """
    if discipline not in ("run", "bike"):
        logger.info("zone_recalc: disciplina %s non supportata (solo HR run/bike), skip", discipline)
        return 0

    sb = get_supabase()
    today = today_rome().isoformat()

    zone_res = (
        sb.table("physiology_zones")
        .select("lthr,valid_from")
        .eq("discipline", discipline)
        .is_("valid_to", "null")
        .order("valid_from", desc=True)
        .limit(1)
        .execute()
    )
    row = (zone_res.data or [None])[0]
    if not row or not row.get("lthr"):
        logger.info("zone_recalc: nessuna LTHR attiva per %s, skip", discipline)
        return 0
    lthr = int(row["lthr"])

    sessions = (
        sb.table("planned_sessions")
        .select("id,description")
        .eq("sport", discipline)
        .eq("status", "planned")
        .gte("planned_date", today)
        .execute()
    ).data or []

    updated = 0
    for s in sessions:
        desc = s.get("description") or ""
        new_desc = rewrite_description(desc, lthr)
        if new_desc != desc:
            sb.table("planned_sessions").update({"description": new_desc}).eq("id", s["id"]).execute()
            updated += 1

    logger.info("zone_recalc: %d/%d sessioni %s future riallineate a LTHR %d",
                updated, len(sessions), discipline, lthr)
    return updated
