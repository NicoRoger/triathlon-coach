"""Fase 4.4 (integrazione) — Estrae belief candidates da coaching_observations.md.

Workflow: dopo pattern_extraction.py produce coaching_observations.md con
pattern strutturati nel formato:

    - **[Osservazione]** (n=X, confidence Y) → **Prescrizione**: <azione>.
      **Expected outcome**: <miglioramento>.

Questo script parsa quei pattern e li registra in `beliefs` table via
`belief_engine.create_belief()`, applicando guardrails automatici.

Pattern già esistenti vengono reinforced (n++, confidence++) se ancora presenti
nelle observations; altrimenti vengono contradicted (n++, confidence--).

Cron: dopo pattern_extraction nel workflow domenicale.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

from coach.analytics.belief_engine import (
    create_belief,
    reinforce_belief,
    contradict_belief,
    list_beliefs,
)

logger = logging.getLogger(__name__)

OBSERVATIONS_FILE = Path(__file__).resolve().parent.parent.parent / "docs" / "coaching_observations.md"

# Regex per estrarre pattern strutturato dal coaching_observations.md
# Formato atteso (rendiamo molto flessibile):
#   - **<observation text>** (n=<N> sett, confidence <C>) → **Prescrizione**: <prescription>.
#     **Expected outcome**: <outcome>.
PATTERN_REGEX = re.compile(
    r"[-•*]\s+"
    r"\*\*(?P<observation>[^*]+?)\*\*"
    r".*?"
    r"\(n[=:]\s*(?P<n>\d+)"
    r"(?:\s*(?:sett|sessioni|sessions|obs)\.?)?"
    r"[,;\s]*"
    r"confidence[\s:]*(?P<confidence>[\d.]+)\)"
    r".*?"
    r"(?:→|->|>)\s*"
    r"(?:\*\*Prescrizione\*\*|\*\*Prescription\*\*)[:\s]*"
    r"(?P<prescription>[^.]+(?:\.[^*\n][^.\n]*)*?)"
    r"(?=\s*\*\*Expected|\s*$)",
    re.IGNORECASE | re.DOTALL,
)

EXPECTED_REGEX = re.compile(
    r"\*\*Expected outcome\*\*[:\s]*(?P<expected>[^.\n]+)",
    re.IGNORECASE,
)


# ============================================================================
# Parsing
# ============================================================================

def _slugify(text: str) -> str:
    """Genera belief_key snake_case da observation text. Stabile fra run."""
    t = unicodedata.normalize("NFKD", text)
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9\s]", "", t).lower()
    words = t.split()
    # Prendi le prime 6 parole significative (skip stopwords ovvie)
    stopwords = {"il", "la", "lo", "i", "gli", "le", "un", "una", "uno",
                 "di", "a", "e", "o", "per", "con", "in", "su", "tra",
                 "che", "del", "della", "dei", "delle", "dal", "dalla"}
    significant = [w for w in words if w not in stopwords and len(w) >= 2][:6]
    return "_".join(significant) if significant else "unnamed_belief"


def _classify_category(observation: str, section: Optional[str]) -> str:
    """Determina category in base a section header o keyword."""
    s = (section or "").lower()
    o = observation.lower()
    if "recupero" in s or "recovery" in s or "recupero" in o:
        return "recovery"
    if "biometrici" in s or "hrv" in o or "sleep" in o:
        return "biometric"
    if "soggettivi" in s or "rpe" in o:
        return "subjective"
    if "settimanali" in s or "settimana" in o:
        return "weekly_pattern"
    if "contestuali" in s or "infortun" in o or "fascite" in o or "spalla" in o:
        return "contextual"
    if any(sp in s for sp in ["nuoto", "swim"]) or "nuoto" in o or "swim" in o:
        return "swim_specific"
    if any(sp in s for sp in ["bici", "bike"]) or "bici" in o or "bike" in o:
        return "bike_specific"
    if any(sp in s for sp in ["corsa", "run"]) or "corsa" in o or "run" in o:
        return "run_specific"
    return "general"


def parse_observations_to_candidates(content: str) -> list[dict]:
    """Estrae lista di belief candidate dal markdown.

    Returns: lista di dict con belief_key, belief_text, prescription, etc.
    """
    candidates: list[dict] = []
    # Split per sezioni (## headers)
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for section_block in sections:
        if not section_block.strip():
            continue
        first_line, _, body = section_block.partition("\n")
        section_name = first_line.strip()

        for m in PATTERN_REGEX.finditer(body):
            obs_text = m.group("observation").strip()
            try:
                n = int(m.group("n"))
                conf = float(m.group("confidence"))
            except (ValueError, TypeError):
                continue
            prescription = m.group("prescription").strip().rstrip(".") + "."
            # Expected outcome (opzionale, cerca dopo il match)
            tail = body[m.end():m.end() + 300]
            expected_match = EXPECTED_REGEX.search(tail)
            expected = expected_match.group("expected").strip() if expected_match else None

            belief_key = _slugify(obs_text)
            category = _classify_category(obs_text, section_name)

            candidates.append({
                "belief_key": belief_key,
                "belief_text": obs_text,
                "initial_confidence": conf,
                "evidence_n_observed": n,
                "category": category,
                "prescription": prescription,
                "expected_outcome": expected,
                "section": section_name,
            })
    return candidates


# ============================================================================
# Sync con belief_engine
# ============================================================================

def sync_beliefs_from_observations(content: Optional[str] = None) -> dict:
    """Confronta belief candidates parsate con DB e applica:
    - reinforce_belief se belief esiste già
    - create_belief se nuova
    - contradict_belief se DB ha belief che non appare più (rimossa)

    Returns:
        dict counts {created, reinforced, contradicted, skipped}
    """
    if content is None:
        if not OBSERVATIONS_FILE.exists():
            logger.warning("Observations file not found: %s", OBSERVATIONS_FILE)
            return {"created": 0, "reinforced": 0, "contradicted": 0, "skipped": 0}
        content = OBSERVATIONS_FILE.read_text(encoding="utf-8")

    candidates = parse_observations_to_candidates(content)
    logger.info("Parsed %d belief candidates from observations", len(candidates))

    # Beliefs già in DB
    existing_beliefs = list_beliefs(min_status="hypothesis", include_flagged=True)
    existing_keys = {b.belief_key for b in existing_beliefs}
    seen_keys: set[str] = set()
    counts = {"created": 0, "reinforced": 0, "contradicted": 0, "skipped": 0}

    for c in candidates:
        key = c["belief_key"]
        seen_keys.add(key)
        if key in existing_keys:
            # Reinforce con outcome che non esiste ancora (None) ma incrementa n+1
            reinforce_belief(key, reason=f"Re-osservato in {c['section']}")
            counts["reinforced"] += 1
        else:
            try:
                create_belief(
                    belief_key=key,
                    belief_text=c["belief_text"],
                    initial_confidence=c["initial_confidence"],
                    category=c["category"],
                    prescription=c["prescription"],
                    expected_outcome=c.get("expected_outcome"),
                    source="pattern_extraction",
                    metadata={
                        "section": c["section"],
                        "n_observed_in_obs": c.get("evidence_n_observed"),
                    },
                )
                counts["created"] += 1
            except Exception:
                logger.exception("Failed to create belief %s", key)
                counts["skipped"] += 1

    # Beliefs in DB ma non più nelle observations → contraddizione cauta
    # Solo se ancora attive (status != retired) e non flagged
    for b in existing_beliefs:
        if b.belief_key in seen_keys or b.status == "retired" or b.flagged:
            continue
        # Aging: se è la prima volta che manca, solo decay naturale; se mancata
        # 3+ volte di seguito, contraddiciamo. Per ora: contraddizione leggera 1x.
        # Per evitare contradiction su belief vecchie ma non più visibili (potrebbero
        # essere riapparse in futuro), faccio contradict SOLO se belief recente
        # (< 60gg). Beliefs vecchie le lascio decay naturale.
        from datetime import datetime, timezone, timedelta
        if b.last_reinforced_at:
            last = b.last_reinforced_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last).days
            if age < 60:
                contradict_belief(b.belief_key,
                                  reason="non re-osservata in nuovo pattern_extraction")
                counts["contradicted"] += 1

    logger.info("Beliefs sync done: %s", counts)
    return counts


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Print parsed candidates without writing")
    args = p.parse_args()

    if args.dry_run:
        if not OBSERVATIONS_FILE.exists():
            print("No observations file found")
            return
        content = OBSERVATIONS_FILE.read_text(encoding="utf-8")
        candidates = parse_observations_to_candidates(content)
        print(f"Parsed {len(candidates)} candidates:")
        for c in candidates:
            print(f"  - [{c['category']}] {c['belief_key']}: {c['belief_text']}")
            print(f"      n={c['evidence_n_observed']}, conf={c['initial_confidence']}")
            print(f"      → {c['prescription']}")
            if c.get("expected_outcome"):
                print(f"      ✓ {c['expected_outcome']}")
            print()
    else:
        counts = sync_beliefs_from_observations()
        print(f"Sync done: {counts}")


if __name__ == "__main__":
    main()
