"""WP3 — rewrite_description: riallineamento range HR nelle prescrizioni."""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

# Load per path (non per package): altri file di test stubbano coach.coaching
# in sys.modules e romperebbero l'import package durante la collection piena.
_spec = _ilu.spec_from_file_location(
    "zone_recalc_under_test",
    Path(__file__).resolve().parent.parent / "coach" / "coaching" / "zone_recalc.py",
)
_mod = _ilu.module_from_spec(_spec)  # type: ignore
_spec.loader.exec_module(_mod)  # type: ignore
rewrite_description = _mod.rewrite_description
_bounds_from_lthr = _mod._bounds_from_lthr

# LTHR 175 → b1=142, b2=156, b3=166 (round di 0.81/0.89/0.95 — stessi
# moltiplicatori di _compute_lthr_5zone)
LTHR = 175


def test_bounds_match_lthr_5zone_multipliers():
    b = _bounds_from_lthr(LTHR)
    assert b == {1: "<142", 2: "142-156", 3: "156-166", 4: "166-175", 5: ">175"}


def test_rewrites_common_formats():
    desc = (
        "- 10' warm-up Z1 (HR <138)\n"
        "- 1h15 Z2 continuo (HR 136-158), no salite\n"
        "- 3×8' in Z3 (HR 158-168) con 4' recupero\n"
        "- chiusura Z4 (HR 163-172, breve)\n"
    )
    out = rewrite_description(desc, LTHR)
    assert "Z1 (HR <142)" in out
    assert "Z2 continuo (HR 142-156), no salite" in out
    assert "in Z3 (HR 156-166) con 4' recupero" in out
    assert "Z4 (HR 166-175, breve)" in out


def test_preserves_trailing_content_in_parens():
    """Solo lo span numerico viene riscritto: ', ~5:30/km' resta (i pace non
    sono gestiti in v1, limite documentato)."""
    out = rewrite_description("25-30' Z2 (HR 138-155, ~5:30/km)", LTHR)
    assert out == "25-30' Z2 (HR 142-156, ~5:30/km)"


def test_untouched_when_no_recognizable_range():
    for desc in [
        "Nuoto 4×200m a passo Z2 (~1:30-1:35/100m)",  # pace, non HR
        "Zona industriale (HR department)",             # niente numeri
        "Z2 lungo senza range espliciti",
    ]:
        assert rewrite_description(desc, LTHR) == desc


def test_does_not_cross_lines_or_parens():
    desc = "Z2 oggi.\nDomani altro (HR 140-150)"  # label e range su righe diverse
    assert rewrite_description(desc, LTHR) == desc


def test_multiple_zones_on_one_line_each_gets_own_range():
    """Regressione: con più label di zona sulla stessa riga vinceva il match
    più a sinistra, così le ripetute Z5 ricevevano il range della Z2 —
    prescrizione corrotta, scritta in automatico e senza conferma."""
    assert rewrite_description("20' Z2 + 5x3' Z5 (HR >178)", LTHR) == "20' Z2 + 5x3' Z5 (HR >175)"
    assert rewrite_description("Z2 60' con finale Z4 (HR 165-174)", LTHR) == "Z2 60' con finale Z4 (HR 166-175)"
    assert (
        rewrite_description("8' warm-up Z1 / 30' Z2 (HR 145-155) / 7' cool-down Z1.", LTHR)
        == "8' warm-up Z1 / 30' Z2 (HR 142-156) / 7' cool-down Z1."
    )


def test_rewrite_touches_only_hr_parens():
    """Invariante di sicurezza: fuori dai gruppi (HR ...) il testo è identico."""
    src = "Z1 (HR <138) poi 4x800m in Z4 (HR 160-170, 4:20/km) rec 2' Z1 (HR <138)"
    out = rewrite_description(src, LTHR)
    assert _mod._only_hr_ranges_changed(src, out)
    assert "4x800m" in out and "4:20/km" in out


def test_unsafe_rewrite_is_discarded(monkeypatch):
    """Se una futura modifica alla regex toccasse testo fuori dai range HR,
    la riscrittura viene scartata invece di corrompere la sessione."""
    import re as _re
    monkeypatch.setattr(_mod, "_ZONE_HR_RE", _re.compile(r"(?P<prefix>Z(?P<zn>[1-5]) )(?P<range>\w+)"))
    src = "Z2 continuo 45'"
    assert rewrite_description(src, LTHR) == src
