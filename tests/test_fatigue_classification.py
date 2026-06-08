"""Test unitari per classify_fatigue_type (ADAPT-01) e update_beliefs_from_session_patterns (ADAPT-03).

Wave 0 RED: classify_fatigue_type e update_beliefs_from_session_patterns non sono ancora implementate.
Questi test falliscono con ImportError/AttributeError finché plan 02/04 non li rendono GREEN.

Esecuzione: python -m pytest tests/test_fatigue_classification.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from coach.analytics.readiness import classify_fatigue_type


# ===========================================================================
# Helper: genera split sintetici per test di corsa
# ===========================================================================

def make_splits_run(
    hr_first: float,
    hr_second: float,
    pace_first: float,
    pace_second: float,
    n: int = 5,
) -> list:
    """Genera split sintetici per test: prima metà HR/pace primo valore, seconda metà degradata.

    Args:
        hr_first: HR media nella prima metà (bpm)
        hr_second: HR media nella seconda metà (bpm)
        pace_first: Pace media nella prima metà (s/km)
        pace_second: Pace media nella seconda metà (s/km) — più alto = più lento
        n: numero totale di split

    Returns:
        Lista di dict con avg_hr e avg_pace_s_per_km
    """
    half = n // 2
    splits = []
    for _ in range(half):
        splits.append({"avg_hr": hr_first, "avg_pace_s_per_km": pace_first})
    for _ in range(n - half):
        splits.append({"avg_hr": hr_second, "avg_pace_s_per_km": pace_second})
    return splits


# ===========================================================================
# Test classify_fatigue_type — segnale cardiovascolare (ADAPT-01)
# ===========================================================================

def test_cardiovascular_signal():
    """HR drift >10bpm nella seconda metà → failure_type == 'cardiovascular'."""
    activity = {"sport": "run", "duration_s": 3600}
    # HR 145→160 (drift +15bpm > 10bpm), pace stabile 280→282 (drop ~0.7% << 5%)
    splits = make_splits_run(hr_first=145, hr_second=160, pace_first=280, pace_second=282)
    result = classify_fatigue_type(activity, splits, debrief_rpe=7)
    assert result.failure_type == "cardiovascular", (
        f"Atteso 'cardiovascular' (HR drift +15bpm), ottenuto: {result.failure_type}"
    )
    assert result.confidence >= 0.6, (
        f"Confidence attesa >= 0.6, ottenuta: {result.confidence}"
    )


# ===========================================================================
# Test classify_fatigue_type — segnale muscolare (ADAPT-01)
# ===========================================================================

def test_muscular_signal():
    """HR stabile + pace peggiora >5% + RPE>=8 → failure_type == 'muscular'."""
    activity = {"sport": "run", "duration_s": 3600}
    # HR stabile 150→152 (drift +2bpm <= 10bpm), pace 263→285 (drop ~8.4% > 5%), RPE 8
    splits = make_splits_run(hr_first=150, hr_second=152, pace_first=263, pace_second=285)
    result = classify_fatigue_type(activity, splits, debrief_rpe=8)
    assert result.failure_type == "muscular", (
        f"Atteso 'muscular' (HR stabile, pace drop 8%, RPE 8), ottenuto: {result.failure_type}"
    )
    assert result.confidence >= 0.6, (
        f"Confidence attesa >= 0.6, ottenuta: {result.confidence}"
    )


# ===========================================================================
# Test classify_fatigue_type — fallback RPE-only (splits assenti)
# ===========================================================================

def test_fallback_rpe_only_no_splits():
    """Splits None + RPE 9 → fallback muscular con confidence = 0.4, signal_used = 'rpe_only'."""
    activity = {"sport": "run", "duration_s": 3600}
    result = classify_fatigue_type(activity, None, debrief_rpe=9)
    assert result.failure_type == "muscular", (
        f"Atteso 'muscular' (RPE 9 >= 8, fallback), ottenuto: {result.failure_type}"
    )
    assert result.confidence == 0.4, (
        f"Confidence attesa == 0.4 (fallback RPE-only), ottenuta: {result.confidence}"
    )
    assert result.signal_used == "rpe_only", (
        f"signal_used atteso 'rpe_only', ottenuto: {result.signal_used}"
    )


# ===========================================================================
# Test classify_fatigue_type — sessione troppo corta
# ===========================================================================

def test_insufficient_data_short_session():
    """Sessione < 30min (1200s) → failure_type is None (dati insufficienti)."""
    activity = {"sport": "run", "duration_s": 1200}  # 20 minuti
    result = classify_fatigue_type(activity, [], debrief_rpe=6)
    assert result.failure_type is None, (
        f"Atteso None per sessione < 30min, ottenuto: {result.failure_type}"
    )


# ===========================================================================
# Test classify_fatigue_type — splits assenti + RPE basso
# ===========================================================================

def test_missing_splits_low_rpe():
    """Bici, splits None, RPE 5 (< 8) → failure_type is None, signal_used == 'rpe_only'."""
    activity = {"sport": "bike", "duration_s": 3600}
    result = classify_fatigue_type(activity, None, debrief_rpe=5)
    assert result.failure_type is None, (
        f"Atteso None (RPE 5 < 8, nessun segnale), ottenuto: {result.failure_type}"
    )
    assert result.signal_used == "rpe_only", (
        f"signal_used atteso 'rpe_only', ottenuto: {result.signal_used}"
    )


# ===========================================================================
# Test update_beliefs_from_session_patterns — n < 3 sessioni → skip (ADAPT-03)
# ===========================================================================

def test_belief_update_minimum_sessions():
    """Il job NON crea belief quando un gruppo session_type ha < 3 sessioni."""
    from coach.coaching.pattern_extraction import update_beliefs_from_session_patterns

    # Fake: 2 session_analyses con session_type 'threshold_run' (< 3 → skip)
    fake_analyses = [
        {"activity_id": "act_1", "fatigue_type": "muscular", "fatigue_confidence": 0.7, "created_at": "2026-06-01T10:00:00Z"},
        {"activity_id": "act_2", "fatigue_type": "muscular", "fatigue_confidence": 0.65, "created_at": "2026-06-02T10:00:00Z"},
    ]
    fake_planned = [
        {"completed_activity_id": "uuid_act_1", "session_type": "threshold_run"},
        {"completed_activity_id": "uuid_act_2", "session_type": "threshold_run"},
    ]
    fake_activities = [
        {"id": "uuid_act_1", "external_id": "act_1"},
        {"id": "uuid_act_2", "external_id": "act_2"},
    ]

    # Contatori per verificare che create_belief/reinforce_belief NON vengano chiamati
    create_call_count = []
    reinforce_call_count = []

    def fake_create_belief(*args, **kwargs):
        create_call_count.append(1)

    def fake_reinforce_belief(*args, **kwargs):
        reinforce_call_count.append(1)

    # Costruisce fake Supabase che restituisce dati controllati
    def make_fake_supabase():
        mock_sb = MagicMock()

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_execute = MagicMock()

            if table_name == "session_analyses":
                mock_execute.data = fake_analyses
            elif table_name == "planned_sessions":
                mock_execute.data = fake_planned
            elif table_name == "activities":
                mock_execute.data = fake_activities
            else:
                mock_execute.data = []

            # Catena di chiamate: .select().gte()....execute()
            mock_chain = MagicMock()
            mock_chain.execute.return_value = mock_execute
            mock_chain.gte.return_value = mock_chain
            mock_chain.not_ = mock_chain
            mock_chain.is_.return_value = mock_chain
            mock_chain.select.return_value = mock_chain
            mock_chain.in_.return_value = mock_chain
            mock_chain.eq.return_value = mock_chain
            mock_table.select.return_value = mock_chain
            return mock_table

        mock_sb.table.side_effect = table_side_effect
        return mock_sb

    with patch("coach.coaching.pattern_extraction.get_supabase", return_value=make_fake_supabase()), \
         patch("coach.analytics.belief_engine.create_belief", side_effect=fake_create_belief), \
         patch("coach.analytics.belief_engine.reinforce_belief", side_effect=fake_reinforce_belief):
        result = update_beliefs_from_session_patterns(days=14)

    assert len(create_call_count) == 0, (
        f"create_belief non doveva essere chiamato con n<3, chiamato {len(create_call_count)} volte"
    )
    assert len(reinforce_call_count) == 0, (
        f"reinforce_belief non doveva essere chiamato con n<3, chiamato {len(reinforce_call_count)} volte"
    )


# ===========================================================================
# Test update_beliefs_from_session_patterns — session_type None → skip (ADAPT-03, Pitfall 4)
# ===========================================================================

def test_belief_update_skips_null_session_type():
    """Il job NON crea belief responds_well_None/struggles_with_None per sessioni senza planned_session."""
    from coach.coaching.pattern_extraction import update_beliefs_from_session_patterns

    # Fake: 5 session_analyses ma senza planned_session corrispondente (session_type=None)
    fake_analyses = [
        {"activity_id": f"act_{i}", "fatigue_type": "muscular", "fatigue_confidence": 0.7, "created_at": f"2026-06-0{i+1}T10:00:00Z"}
        for i in range(5)
    ]
    # Nessuna planned_session corrispondente → session_type=None per tutte
    fake_planned = []  # nessun match
    fake_activities = [
        {"id": f"uuid_act_{i}", "external_id": f"act_{i}"}
        for i in range(5)
    ]

    created_belief_keys = []

    def fake_create_belief(key, *args, **kwargs):
        created_belief_keys.append(key)

    def make_fake_supabase():
        mock_sb = MagicMock()

        def table_side_effect(table_name):
            mock_table = MagicMock()
            mock_execute = MagicMock()

            if table_name == "session_analyses":
                mock_execute.data = fake_analyses
            elif table_name == "planned_sessions":
                mock_execute.data = fake_planned
            elif table_name == "activities":
                mock_execute.data = fake_activities
            else:
                mock_execute.data = []

            mock_chain = MagicMock()
            mock_chain.execute.return_value = mock_execute
            mock_chain.gte.return_value = mock_chain
            mock_chain.not_ = mock_chain
            mock_chain.is_.return_value = mock_chain
            mock_chain.select.return_value = mock_chain
            mock_chain.in_.return_value = mock_chain
            mock_chain.eq.return_value = mock_chain
            mock_table.select.return_value = mock_chain
            return mock_table

        mock_sb.table.side_effect = table_side_effect
        return mock_sb

    with patch("coach.coaching.pattern_extraction.get_supabase", return_value=make_fake_supabase()), \
         patch("coach.analytics.belief_engine.create_belief", side_effect=fake_create_belief):
        result = update_beliefs_from_session_patterns(days=14)

    none_keys = [k for k in created_belief_keys if "None" in k or k.endswith("_None")]
    assert len(none_keys) == 0, (
        f"Belief con session_type=None non devono essere creati, trovati: {none_keys}"
    )
