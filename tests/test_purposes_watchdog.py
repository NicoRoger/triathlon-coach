"""WP2 — registry purpose + watchdog a copertura totale."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from coach.utils.purposes import ALL_PURPOSES
from scripts.send_notification import NOTIF_PURPOSE
from scripts.watchdog import (
    CADENCE_THRESHOLDS_HOURS,
    DEFAULT_THRESHOLD_HOURS,
    THRESHOLDS_HOURS,
    compute_alerts,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def _row(comp, success_hours_ago=None, failure=False):
    r = {"component": comp, "last_success_at": None, "last_failure_at": None, "last_error": None}
    if success_hours_ago is not None:
        r["last_success_at"] = (NOW - timedelta(hours=success_hours_ago)).isoformat()
    if failure:
        r["last_failure_at"] = NOW.isoformat()
        r["last_error"] = "boom"
    return r


def test_notif_purpose_values_in_registry():
    """I purpose del mapping notifiche DEVONO esistere nel registry: la
    divergenza invio↔check è stata causa di 2 bug storici (doppio debrief,
    3× weekly review)."""
    for v in NOTIF_PURPOSE.values():
        assert v in ALL_PURPOSES, f"purpose '{v}' non nel registry coach/utils/purposes.py"


def test_unknown_component_is_monitored_with_default():
    """Copertura totale: un componente MAI elencato nelle mappe viene comunque
    monitorato (soglia default) appena compare in health — impossibile
    dimenticarsene."""
    comp = "job_futuro_mai_visto"
    assert comp not in THRESHOLDS_HOURS and comp not in CADENCE_THRESHOLDS_HOURS
    fresh = compute_alerts([_row(comp, success_hours_ago=1)], NOW)
    stale = compute_alerts([_row(comp, success_hours_ago=DEFAULT_THRESHOLD_HOURS + 5)], NOW)
    # (gli alert dei CORE mancanti sono attesi: si filtra sul componente nuovo)
    assert not any(comp in a for a in fresh)
    assert any(comp in a for a in stale)


def test_core_missing_row_alerts_noncore_stub_does_not():
    """CORE assente → alert (audit L4). Riga stub non-core (tutta null, es.
    debrief_evening storica) → silenzio; ma se ha fallimenti registrati → alert."""
    alerts = compute_alerts([_row("debrief_evening")], NOW)
    missing_core = [a for a in alerts if "garmin_sync" in a]
    stub_alerts = [a for a in alerts if "debrief_evening" in a]
    assert missing_core, "core assente deve generare alert"
    assert not stub_alerts, "stub non-core senza fallimenti non deve allertare"

    failing = compute_alerts([_row("debrief_evening", failure=True)], NOW)
    assert any("debrief_evening" in a for a in failing)


def test_cadence_override_respected():
    """Un job settimanale (soglia 200h) non allerta a 100h, allerta a 250h."""
    ok = compute_alerts([_row("pattern_extraction", success_hours_ago=100)], NOW)
    assert not any("pattern_extraction" in a for a in ok)
    late = compute_alerts([_row("pattern_extraction", success_hours_ago=250)], NOW)
    assert any("pattern_extraction" in a for a in late)
