"""Drift tra vincoli CHECK del DB e valori letterali scritti dal codice.

Nato da un incidente reale: il CHECK su `plan_modulations.source` ammetteva
('auto','coach','athlete') mentre il codice scriveva 'test_scheduler'. Il job
domenicale è morto con 23514 per 4 settimane consecutive — e siccome lo step
falliva PRIMA di quello che registra lo stato di salute, il watchdog è rimasto
verde per tutto il tempo.

Questo test legge i valori ammessi dalle migrations e li confronta con quelli
letterali nel codice: un disallineamento fallisce in CI invece che di domenica
notte in produzione.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _allowed_values(table: str, column: str) -> set[str]:
    """Valori ammessi dall'ULTIMO CHECK definito per (tabella, colonna).

    Le migrations sono cronologiche nel nome: l'ultima che tocca il vincolo
    vince, come in produzione dove vengono applicate in ordine.
    """
    pattern = re.compile(
        rf"ADD\s+CONSTRAINT\s+{table}_{column}_check\s+CHECK\s*\(\s*{column}\s+IN\s*\((?P<vals>[^)]*)\)",
        re.IGNORECASE | re.DOTALL,
    )
    allowed: set[str] = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        # I commenti SQL vanno rimossi PRIMA del match: una parentesi chiusa
        # dentro un commento (es. "-- test scaduto (Phase 2.6)") troncherebbe
        # l'elenco dei valori e farebbe fallire il test su un vincolo corretto.
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
        m = pattern.search(sql)
        if m:
            allowed = set(re.findall(r"'([^']+)'", m.group("vals")))
    return allowed


def _source_literals_in_code() -> dict[str, str]:
    """Valori letterali passati come `source=` alle chiamate Python.

    Ritorna {valore: 'file:riga'} per un messaggio d'errore utile.
    """
    found: dict[str, str] = {}
    for path in (ROOT / "coach").rglob("*.py"):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for value in re.findall(r'\bsource\s*=\s*"([a-z_]+)"', line):
                found.setdefault(value, f"{path.relative_to(ROOT)}:{i}")
    return found


def test_plan_modulations_source_values_are_allowed():
    allowed = _allowed_values("plan_modulations", "source")
    assert allowed, "CHECK su plan_modulations.source non trovato nelle migrations"

    # `source=` compare anche in chiamate a create_belief/record_prediction, che
    # hanno un dominio diverso: si verificano solo i valori usati per le
    # modulazioni, cioè quelli nei moduli che chiamano propose_modulation.
    modulation_callers = {"test_scheduler", "pattern_extraction_job", "auto", "coach", "athlete"}
    used = {v: loc for v, loc in _source_literals_in_code().items() if v in modulation_callers}

    violations = {v: loc for v, loc in used.items() if v not in allowed}
    assert not violations, (
        "Valori di plan_modulations.source scritti dal codice ma non ammessi dal "
        f"CHECK {sorted(allowed)}: {violations}. "
        "Aggiungi una migration che allarga il vincolo, oppure cambia il valore nel codice."
    )
