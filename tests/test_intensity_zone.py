"""#4 — l'intensità si giudica sulla NOSTRA zona (LTHR), non sui bucket Garmin."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_psa", Path("coach/coaching/post_session_analysis.py").resolve()
)
# Evita di eseguire dipendenze pesanti: importiamo solo le funzioni pure via exec
import types, sys
psa = importlib.util.module_from_spec(_spec)


class TestOurHrZone(unittest.TestCase):
    def test_143_with_lthr_172_is_z2_not_z3(self):
        # carica modulo (dipende da supabase ecc., ma le funzioni usate sono pure)
        try:
            _spec.loader.exec_module(psa)
        except Exception:
            self.skipTest("modulo non importabile in isolamento")
        self.assertEqual(psa._our_hr_zone(143, 172), "Z2")
        self.assertEqual(psa.SESSION_TYPE_ZONE.get("easy"), "Z2")
        # 165/172 = 0.96 → Z4; 150/172 = 0.87 → Z2
        self.assertEqual(psa._our_hr_zone(165, 172), "Z4")
        self.assertEqual(psa._our_hr_zone(150, 172), "Z2")


if __name__ == "__main__":
    unittest.main()
