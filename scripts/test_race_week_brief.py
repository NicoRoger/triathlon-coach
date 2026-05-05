"""Test simulato: forza race week per verificare il template."""
from datetime import date
from unittest.mock import patch

from coach.planning import briefing


def test_t_minus_3():
    """Simula oggi a T-3 dalla gara."""
    fake_today = date(2026, 9, 3)  # 3 giorni prima del 6 settembre
    
    with patch.object(briefing, '_get_upcoming_race') as mock_race:
        mock_race.return_value = {
            "name": "Lavarone Cross Sprint",
            "date": date(2026, 9, 6),
            "priority": "A",
            "distance": "750m + 16-17km MTB + 5km trail",
            "days_to_race": 3,
        }
        # Patcha anche la data di oggi
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with patch.object(briefing, 'datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 9, 3, 6, 30, tzinfo=ZoneInfo("Europe/Rome"))
            mock_dt.fromisoformat = datetime.fromisoformat
            
            msg = briefing.build_brief()
            print(msg)


if __name__ == "__main__":
    test_t_minus_3()