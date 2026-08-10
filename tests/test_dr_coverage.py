"""Copertura del backup DR: nessuna tabella deve restare fuori per dimenticanza.

Il backup copriva 9 tabelle su 23. Le 14 mancanti includevano
`active_constraints` (i vincoli medici, fonte di verità per le prescrizioni),
tutte le `beliefs` e le `session_analyses`: un restore avrebbe riportato il
piano ma perso lo stato di coaching, senza che nulla lo segnalasse — il
controllo di sanità guardava solo 3 tabelle.

Questo test fallisce quando una migration crea una tabella nuova che nessuno
ha aggiunto (o escluso esplicitamente) nello snapshot.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tabelle deliberatamente FUORI dal backup, con la ragione. Aggiungere qui è
# una decisione esplicita; dimenticarsene fa fallire il test.
INTENTIONALLY_EXCLUDED = {
    # Viste, non tabelle: si ricalcolano dai dati sottostanti.
    "prediction_accuracy",
}


def _declared_tables() -> set[str]:
    """Tabelle create da schema.sql + migrations."""
    tables: set[str] = set()
    sources = [ROOT / "sql" / "schema.sql", *sorted((ROOT / "migrations").glob("*.sql"))]
    for path in sources:
        if not path.exists():
            continue
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)", sql, re.IGNORECASE
        ):
            tables.add(m.group(1).lower())
    return tables


def test_dr_snapshot_covers_every_table():
    from scripts.dr_snapshot import TABLES

    declared = _declared_tables()
    assert declared, "nessuna tabella trovata: parser da rivedere"

    missing = declared - set(TABLES) - INTENTIONALLY_EXCLUDED
    assert not missing, (
        f"Tabelle create nello schema ma assenti dal backup DR: {sorted(missing)}. "
        "Aggiungile a scripts/dr_snapshot.TABLES (nella posizione giusta per le FK) "
        "oppure dichiarale in INTENTIONALLY_EXCLUDED con la motivazione."
    )


def test_dr_snapshot_has_no_phantom_tables():
    """Il contrario: una tabella nell'elenco ma inesistente farebbe fallire
    l'export a ogni run notturno."""
    from scripts.dr_snapshot import TABLES

    declared = _declared_tables()
    phantom = set(TABLES) - declared
    assert not phantom, f"Tabelle nell'elenco DR ma non create da alcuna migration: {sorted(phantom)}"


def test_restore_order_matches_snapshot():
    """Restore e snapshot devono usare la stessa lista: divergendo, il restore
    salta tabelle o le scrive in un ordine che viola le foreign key."""
    from scripts.dr_restore import RESTORE_ORDER
    from scripts.dr_snapshot import TABLES

    assert list(RESTORE_ORDER) == list(TABLES)


def test_activities_precede_dependent_tables():
    """physiology_zones.test_activity_id e session_analyses.activity_id sono FK
    verso activities: se arrivano prima, il restore esplode a metà."""
    from scripts.dr_snapshot import TABLES

    pos = {t: i for i, t in enumerate(TABLES)}
    for dependent in ("physiology_zones", "session_analyses"):
        assert pos["activities"] < pos[dependent], (
            f"{dependent} viene ripristinata prima di activities: violazione FK"
        )
    assert pos["races"] < pos["mesocycles"], "mesocycles.target_race_id → races"


def test_athletes_precede_everything():
    """Ogni tabella con dati d'atleta ha una FK verso athletes: se non arriva
    per prima, il restore viola il vincolo alla prima riga scritta."""
    from scripts.dr_snapshot import TABLES

    assert TABLES[0] == "athletes", (
        f"athletes deve essere la prima tabella ripristinata, trovata: {TABLES[0]}"
    )
