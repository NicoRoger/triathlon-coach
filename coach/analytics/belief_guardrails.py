"""Fase 4.4 — Belief guardrails.

Anti-overfitting + anti-implausibilità per le beliefs.

Reject/flag:
- Low-sample prescriptive (n<5 con prescrizione strict)
- Physiological impossibilities (es. "recovery Z5 in 6h" → flag)
- Safety override (beliefs che propongono attività rischiose)
- Causalità con dataset minuscolo (n<3 con confidence >0.5 → reject)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Pattern di beliefs sospette (semplice keyword matching, da arricchire nel tempo)
IMPLAUSIBLE_KEYWORDS = [
    "recupera in 1 ora", "recover in 1h", "no recovery needed",
    "infinito",  "indefinitamente", "sempre", "mai un infortunio",
    "ignora dolore", "soglia raddoppiata", "ftp 10w",
]

# Beliefs che potenzialmente overridano safety (DEVONO essere flagged)
SAFETY_OVERRIDE_PATTERNS = [
    re.compile(r"ignora.*hrv", re.IGNORECASE),
    re.compile(r"ignora.*infortun", re.IGNORECASE),
    re.compile(r"continua nonostante", re.IGNORECASE),
    re.compile(r"non serve recover", re.IGNORECASE),
    re.compile(r"recupera.*z[45].*in [1-5]\s*h", re.IGNORECASE),
]


def check_belief_admissible(
    belief_text: str,
    initial_confidence: float,
    evidence_n: int,
    prescription: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Verifica admissibility di una belief candidata.

    Returns:
        (admissible: bool, flag_reason: Optional[str])
        Se non admissible, la belief viene comunque creata ma con flagged=True
        e flag_reason valorizzato. Il sistema NON la userà in proposte.
    """
    text_lower = belief_text.lower()

    # 1. Causalità con n minuscolo + confidence alta
    if evidence_n < 3 and initial_confidence > 0.5:
        return False, f"Causalità con n={evidence_n} e confidence={initial_confidence} (n minimo 3)"

    # 2. Prescription prescrittiva con n basso
    if prescription and evidence_n < 5:
        # Permettiamo se è cautelativa (parole come "considerare", "valutare", "monitorare")
        cautious_keywords = ["considera", "considerare", "valuta", "valutare", "monitora", "monitorare"]
        is_cautious = any(kw in prescription.lower() for kw in cautious_keywords)
        if not is_cautious:
            return False, f"Prescrizione prescrittiva (non cautelativa) con n={evidence_n} (min 5)"

    # 3. Implausibilità fisiologica
    for kw in IMPLAUSIBLE_KEYWORDS:
        if kw in text_lower:
            return False, f"Implausibilità fisiologica: contiene '{kw}'"

    # 4. Safety override
    for pat in SAFETY_OVERRIDE_PATTERNS:
        if pat.search(belief_text) or (prescription and pat.search(prescription)):
            return False, f"Possibile safety override: pattern '{pat.pattern}'"

    # 5. Confidence iniziale fuori range
    if initial_confidence < 0 or initial_confidence > 1:
        return False, f"Confidence {initial_confidence} fuori range [0,1]"

    return True, None


def is_belief_actionable_for_priority_engine(belief: dict) -> bool:
    """Le beliefs sono usabili in priority engine (priority 5) solo se:
    - status in {validated_belief, strong_belief}
    - non flagged
    - confidence > 0.6 (sopra weak threshold)
    """
    status = belief.get("status", "hypothesis")
    flagged = bool(belief.get("flagged", False))
    confidence = float(belief.get("confidence", 0))
    return (
        status in ("validated_belief", "strong_belief")
        and not flagged
        and confidence > 0.6
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cases = [
        ("HRV basso sabato (mean z=-0.8)", 0.6, 6, "evitare qualità sabato"),
        ("Ignora HRV in fase build", 0.7, 10, "spingi forte"),
        ("Recupera Z5 in 2h", 0.5, 4, None),
        ("RPE elevato dopo Z4 (n=2)", 0.8, 2, "spingere ancora più forte"),
        ("Mercoledì giorno migliore per qualità", 0.6, 8, "considera Mercoledì per blocchi qualità"),
    ]
    for text, conf, n, presc in cases:
        ok, reason = check_belief_admissible(text, conf, n, presc)
        print(f"{'OK' if ok else 'FLAG'}: {text}")
        if reason:
            print(f"   reason: {reason}")


if __name__ == "__main__":
    main()
