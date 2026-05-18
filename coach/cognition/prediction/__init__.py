"""Prediction layer: forecast numerici verificabili.

Re-export dei moduli esistenti per separazione semantica:
- outcome_engine: tracking predizioni vs outcome
- test_prediction: FTP/CSS/threshold pre-test prediction
- race_prediction: race time prediction
"""

# Re-export outcome tracking (Fase 2.1 + 4.1)
from coach.coaching.outcome_verification import (
    record_prediction,
    verify_pending_predictions,
    update_athlete_beliefs,
    RESOLVERS,
)

# Re-export test prediction
try:
    from coach.coaching.test_prediction import (
        generate_pre_test_predictions,
        PREDICTORS,
    )
except ImportError:
    pass

# Re-export race prediction (se esiste come modulo Python)
try:
    from coach.coaching.race_prediction import predict_race_time
except ImportError:
    pass  # race_prediction è skill-based, non sempre modulo Python

__all__ = [
    "record_prediction",
    "verify_pending_predictions",
    "update_athlete_beliefs",
    "RESOLVERS",
    "generate_pre_test_predictions",
    "PREDICTORS",
]
