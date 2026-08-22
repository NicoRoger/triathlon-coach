"""Scoping per atleta: il debito può solo diminuire.

Con `athlete_id` sulle tabelle, il modo peggiore di sbagliare è una query non
filtrata: legge o scrive i dati dell'atleta sbagliato **senza errori**. Il
default sulla colonna (fase 1) protegge dalle scritture, ma non dalle letture.

Qui si tiene una baseline dei call site ancora non convertiti a `aq()`. Il
numero può solo SCENDERE: una query nuova non filtrata fa fallire la CI.
È il pattern strangler fig — si converte per strati, senza un big-bang su 238
punti, e senza che nel frattempo se ne aggiungano altri.

Quando la baseline arriva a zero si toglie il DEFAULT dalla colonna in DB e
il sistema diventa fail-loud anche in scrittura.
"""
from __future__ import annotations

import re
from pathlib import Path

from coach.utils.athlete import PER_ATHLETE_TABLES, SYSTEM_TABLES

ROOT = Path(__file__).resolve().parent.parent

#: Call site NON ancora convertiti, per file. Aggiornato dopo la conversione
#: del layer analytics (daily/risk/uncertainty: 12 call site convertiti).
#: NON aggiungere voci: si convertono i file e si abbassano i numeri.
UNSCOPED_BASELINE: dict[str, int] = {
    "scripts/simulate_validation_data.py": 17,
    "coach/coaching/modulation.py": 16,
    "coach/analytics/belief_engine.py": 12,
    "coach/coaching/pattern_extraction.py": 12,
    "coach/planning/briefing.py": 12,
    "coach/coaching/hypothesis.py": 11,
    "coach/coaching/outcome_verification.py": 11,
    "coach/coaching/post_session_analysis.py": 10,
}
#: Totale su tutti i file (inclusi quelli sotto la soglia di dettaglio sopra).
UNSCOPED_TOTAL_BASELINE = 226

_TABLE_CALL = re.compile(r'\.table\(\s*["\'](\w+)["\']')


def _unscoped_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for base in ("coach", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            n = sum(
                1
                for m in _TABLE_CALL.finditer(path.read_text(encoding="utf-8"))
                if m.group(1) in PER_ATHLETE_TABLES
            )
            if n:
                counts[str(path.relative_to(ROOT))] = n
    return counts


def test_unscoped_queries_only_decrease():
    counts = _unscoped_counts()
    total = sum(counts.values())

    assert total <= UNSCOPED_TOTAL_BASELINE, (
        f"Query non filtrate per atleta: {total} (baseline {UNSCOPED_TOTAL_BASELINE}). "
        "Ne sono state aggiunte di nuove: usa `aq(\"tabella\")` da "
        "coach/utils/athlete.py invece di `get_supabase().table(...)`, "
        "altrimenti la query vede i dati di TUTTI gli atleti."
    )

    regressioni = {
        f: (n, UNSCOPED_BASELINE[f])
        for f, n in counts.items()
        if f in UNSCOPED_BASELINE and n > UNSCOPED_BASELINE[f]
    }
    assert not regressioni, f"File peggiorati (attuale, baseline): {regressioni}"


def test_baseline_is_not_stale():
    """Se il totale scende, la baseline va abbassata: altrimenti il guard
    lascia spazio per reintrodurre query non filtrate senza accorgersene."""
    total = sum(_unscoped_counts().values())
    assert total >= UNSCOPED_TOTAL_BASELINE - 15, (
        f"Il totale è sceso a {total}: aggiorna UNSCOPED_TOTAL_BASELINE "
        f"(e le voci per file) per bloccare il progresso ottenuto."
    )


def test_table_classification_is_exhaustive():
    """Ogni tabella interrogata dal codice deve essere classificata: per-atleta
    o di sistema. Una tabella nuova non classificata farebbe sollevare `aq()`
    a runtime, in produzione, invece che qui."""
    known = PER_ATHLETE_TABLES | SYSTEM_TABLES
    # Viste e cataloghi interrogati in sola lettura da script diagnostici.
    ignorabili = {"prediction_accuracy", "columns", "table_constraints"}

    used: set[str] = set()
    for base in ("coach", "scripts"):
        for path in (ROOT / base).rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            used.update(_TABLE_CALL.findall(path.read_text(encoding="utf-8")))

    non_classificate = used - known - ignorabili
    assert not non_classificate, (
        f"Tabelle usate dal codice ma non classificate in coach/utils/athlete.py: "
        f"{sorted(non_classificate)}"
    )


def test_per_athlete_tables_match_migration():
    """PER_ATHLETE_TABLES deve coincidere con le tabelle a cui la migration ha
    aggiunto athlete_id: se divergono, `aq()` filtrerebbe su una colonna
    inesistente (errore) o lascerebbe passare una tabella non filtrata."""
    migration = (ROOT / "migrations" / "2026-08-09-multi-athlete-foundation.sql").read_text(
        encoding="utf-8"
    )
    block = re.search(
        r"per_athlete_tables TEXT\[\] := ARRAY\[(.*?)\]", migration, re.DOTALL
    )
    assert block, "blocco per_athlete_tables non trovato nella migration"
    dichiarate = set(re.findall(r"'(\w+)'", block.group(1)))

    assert dichiarate == set(PER_ATHLETE_TABLES), (
        f"Disallineamento codice/migration.\n"
        f"Solo nella migration: {sorted(dichiarate - PER_ATHLETE_TABLES)}\n"
        f"Solo nel codice: {sorted(PER_ATHLETE_TABLES - dichiarate)}"
    )
