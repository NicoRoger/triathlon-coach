"""#5 — una belief confutata (flagged) non deve essere ri-rinforzata in automatico."""
from __future__ import annotations
import sys
import types
import unittest
from unittest.mock import MagicMock


class TestReinforceRespectsFlagged(unittest.TestCase):
    def test_flagged_belief_not_reinforced(self):
        # Altri test stubbano belief_engine in sys.modules: ricarica il vero.
        sys.modules.pop("coach.analytics.belief_engine", None)
        import coach.analytics.belief_engine as be

        flagged_row = {
            "id": "b1", "belief_key": "k", "belief_text": "x", "confidence": 0.6,
            "evidence_n": 3, "status": "validated_belief", "flagged": True,
            "flag_reason": "confutata", "category": None,
        }
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
            types.SimpleNamespace(data=[flagged_row])
        be.get_supabase = lambda: sb

        be.reinforce_belief("k", reason="post-session")
        self.assertFalse(sb.table.return_value.update.called,
                         "una belief flagged non deve essere aggiornata da reinforce")


if __name__ == "__main__":
    unittest.main()
