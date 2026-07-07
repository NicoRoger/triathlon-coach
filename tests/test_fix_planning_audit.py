"""Test fix audit planning 2026-07-02.

Copre:
  Fix 1 — scripts/send_notification.py: cutoff idempotenza a mezzanotte Rome
          con offset REALE (non hardcoded +02:00 → bug in inverno/CET).
  Fix 4a — coach/utils/telegram_logger.py: _log_bot_message ritenta 1 volta
          prima di arrendersi (brief inviato ma non registrato → doppione).
  Fix 8a — coach/planning/briefing.py: protocollo race-week completo solo per
          gare priority A; per gare B sezione leggera solo da T-2, niente taper.

Esecuzione: PYTHONPATH=. python -m pytest tests/test_fix_planning_audit.py -v
"""
from __future__ import annotations

import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel_path: str):
    """Carica un modulo da path relativo (stesso pattern di test_audit_resilience)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# ===========================================================================
# Fix 1 — cutoff idempotenza: mezzanotte Rome con offset reale (inverno CET)
# ===========================================================================

class _CutoffCaptureSB:
    """Fake supabase che cattura il valore passato a .gte()."""

    def __init__(self):
        self.gte_args: list[tuple[str, str]] = []

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, col, val):
        self.gte_args.append((col, val))
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return types.SimpleNamespace(data=[])


def test_fix1_idempotency_cutoff_uses_real_winter_offset(monkeypatch):
    """In inverno (CET, UTC+1) la mezzanotte Rome del 15/01 è 23:00 UTC del 14/01.
    L'hardcoded '+02:00' produceva 22:00 UTC → la finestra includeva l'ultima
    ora di ieri e un reminder di ieri sera (23:xx Rome) sopprimeva quello di oggi."""
    sn = _load("scripts.send_notification_fix1", "scripts/send_notification.py")

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 15, 7, 0, tzinfo=ZoneInfo("Europe/Rome"))

    fake = _CutoffCaptureSB()
    monkeypatch.setattr(sn, "datetime", _DT)
    monkeypatch.setattr(sn, "get_supabase", lambda: fake)

    assert sn._already_sent_today("debrief_reminder") is False
    assert len(fake.gte_args) == 1
    col, cutoff = fake.gte_args[0]
    assert col == "sent_at"
    parsed = datetime.fromisoformat(cutoff)
    expected = datetime(2026, 1, 14, 23, 0, tzinfo=timezone.utc)  # 00:00 Rome CET
    assert parsed == expected, (
        f"cutoff {cutoff} deve essere la mezzanotte Rome in UTC (23:00 del 14/01), "
        "non 22:00 (offset estivo hardcoded)"
    )


def test_fix1_idempotency_cutoff_summer_offset(monkeypatch):
    """In estate (CEST, UTC+2) la mezzanotte Rome del 15/07 è 22:00 UTC del 14/07."""
    sn = _load("scripts.send_notification_fix1b", "scripts/send_notification.py")

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 15, 7, 0, tzinfo=ZoneInfo("Europe/Rome"))

    fake = _CutoffCaptureSB()
    monkeypatch.setattr(sn, "datetime", _DT)
    monkeypatch.setattr(sn, "get_supabase", lambda: fake)

    sn._already_sent_today("debrief_reminder")
    _, cutoff = fake.gte_args[0]
    assert datetime.fromisoformat(cutoff) == datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc)


# ===========================================================================
# Fix 4a — _log_bot_message: 1 retry su errore DB transitorio
# ===========================================================================

class _FlakySB:
    """Fake supabase il cui execute() fallisce le prime `fail_times` volte."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.execute_calls = 0

    def table(self, name):
        return self

    def upsert(self, record, **k):
        return self

    def execute(self):
        self.execute_calls += 1
        if self.execute_calls <= self.fail_times:
            raise RuntimeError("transient DB error")
        return types.SimpleNamespace(data=[])


def _load_telegram_logger(mod_name: str):
    return _load(mod_name, "coach/utils/telegram_logger.py")


def test_fix4a_log_bot_message_retries_once_and_succeeds(monkeypatch):
    """Primo upsert fallisce (transitorio) → retry → registrato. Prima il
    fallimento veniva inghiottito subito → brief inviato ma non loggato →
    doppio brief al cron successivo."""
    tl = _load_telegram_logger("telegram_logger_fix4a")
    flaky = _FlakySB(fail_times=1)
    monkeypatch.setattr(tl, "get_supabase", lambda: flaky)

    tl._log_bot_message(telegram_message_id=42, chat_id=1, purpose="morning_brief")

    assert flaky.execute_calls == 2, "deve ritentare una volta dopo il primo errore"


def test_fix4a_log_bot_message_gives_up_after_retry_without_raising(monkeypatch):
    """Dopo il retry fallito si arrende SENZA propagare (best-effort)."""
    tl = _load_telegram_logger("telegram_logger_fix4a_b")
    flaky = _FlakySB(fail_times=10)
    monkeypatch.setattr(tl, "get_supabase", lambda: flaky)

    tl._log_bot_message(telegram_message_id=43, chat_id=1, purpose="morning_brief")  # no raise

    assert flaky.execute_calls == 2, "esattamente 1 retry, poi stop"


# ===========================================================================
# Fix 8a — race week: protocollo completo solo per gare A; B leggera da T-2
# ===========================================================================

def _race(priority: str, days: int) -> dict:
    return {
        "name": "Gara Test",
        "date": date(2026, 9, 6),
        "priority": priority,
        "distance": "cross_sprint",
        "days_to_race": days,
    }


def test_fix8a_race_section_applicable_gating():
    import coach.planning.briefing as b

    assert b._race_section_applicable(None) is False
    # Gara A: sezione race week per tutta la finestra T-7 → T-0
    assert b._race_section_applicable(_race("A", 7)) is True
    assert b._race_section_applicable(_race("A", 0)) is True
    # Gara B: NIENTE sezione prima di T-2 (il taper distruggerebbe il carico)
    assert b._race_section_applicable(_race("B", 7)) is False
    assert b._race_section_applicable(_race("B", 3)) is False
    # Gara B: sezione leggera da T-2
    assert b._race_section_applicable(_race("B", 2)) is True
    assert b._race_section_applicable(_race("B", 0)) is True


def test_fix8a_race_b_section_is_light_no_taper():
    """Per una gara B la sezione NON prescrive il taper completo."""
    import coach.planning.briefing as b

    out = b._build_race_week_section(_race("B", 2), date(2026, 9, 4))
    assert "niente taper" in out
    assert "gara B" in out
    # Niente indicazioni del protocollo completo A
    assert "check materiale" not in out
    assert "volume -40%" not in out
    assert "race_week_protocol" not in out


def test_fix8a_race_b_day0_not_full_race_day_protocol():
    """A T-0 di una gara B niente 'RACE DAY' completo (riservato alle A)."""
    import coach.planning.briefing as b

    out = b._build_race_week_section(_race("B", 0), date(2026, 9, 6))
    assert "RACE DAY" not in out
    assert "niente taper" in out


def test_fix8a_race_a_keeps_full_protocol():
    """Il protocollo completo per le gare A resta invariato (T-7: taper)."""
    import coach.planning.briefing as b

    out = b._build_race_week_section(_race("A", 7), date(2026, 8, 30))
    assert "taper" in out.lower()
    assert "volume -40%" in out

    out_day0 = b._build_race_week_section(_race("A", 0), date(2026, 9, 6))
    assert "RACE DAY" in out_day0
