"""Token Garmin persistiti tra i run (guasto del 30/09/2026).

garminconnect usa refresh token a rotazione: il refresh fatto in un run
GitHub Actions finiva in una cartella temporanea e si perdeva, quindi dal run
successivo il refresh token del secret era già invalidato → 401 a ogni run.
"""
from __future__ import annotations

import base64
import importlib
import json
import sys
import types
from types import SimpleNamespace

import pytest


def _jwt(exp: int) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'exp': exp})}.sig"


def _tokens(exp: int, refresh: str) -> str:
    return json.dumps({"di_token": _jwt(exp), "di_refresh_token": refresh, "di_client_id": "c"})


def _secret(tokens: str) -> str:
    return base64.b64encode(json.dumps({"garmin_tokens.json": tokens}).encode()).decode()


class _Table:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.row = db, name, {}, None

    def select(self, *a): return self
    def eq(self, k, v): self.filters[k] = v; return self
    def limit(self, n): return self

    def upsert(self, row, on_conflict=None):
        self.row = row
        return self

    def execute(self):
        if self.db.get("broken"):
            raise RuntimeError('relation "service_tokens" does not exist')
        rows = self.db.setdefault(self.name, {})
        if self.row is not None:
            rows[self.row["name"]] = self.row
            return SimpleNamespace(data=[self.row])
        hit = rows.get(self.filters.get("name"))
        return SimpleNamespace(data=[hit] if hit else [])


def _is_project(name: str) -> bool:
    return name.split(".")[0] in ("coach", "scripts", "garminconnect")


@pytest.fixture
def env(monkeypatch):
    """garmin.py reale con DB finto e garminconnect finto che simula la
    rotazione: se l'access token è scaduto, il login lo rinnova e scrive un
    refresh token NUOVO; un refresh token già usato viene rifiutato (401)."""
    saved = {k: v for k, v in sys.modules.items() if _is_project(k)}
    for k in saved:
        del sys.modules[k]

    db: dict = {}
    garmin_state = {"used_refresh": set(), "now": 1000, "refreshes": 0}

    class AuthError(Exception):
        pass

    AuthError.__name__ = "GarminConnectAuthenticationError"

    class FakeGarmin:
        def login(self):
            import os
            from pathlib import Path
            path = Path(os.environ["GARMINTOKENS"]) / "garmin_tokens.json"
            data = json.loads(path.read_text())
            exp = json.loads(base64.urlsafe_b64decode(data["di_token"].split(".")[1] + "=="))["exp"]
            if exp > garmin_state["now"]:
                return None, None
            if data["di_refresh_token"] in garmin_state["used_refresh"]:
                raise AuthError("Failed to retrieve social profile")
            garmin_state["used_refresh"].add(data["di_refresh_token"])
            garmin_state["refreshes"] += 1
            path.write_text(_tokens(garmin_state["now"] + 3600, f"r{garmin_state['refreshes']}"))
            if garmin_state.get("api_rejects"):
                raise AuthError("Failed to retrieve social profile")
            return None, None

    fake = types.ModuleType("garminconnect")
    fake.Garmin = FakeGarmin
    sys.modules["garminconnect"] = fake
    try:
        garmin = importlib.import_module("coach.ingest.garmin")
        athlete = importlib.import_module("coach.utils.athlete")
        sbmod = importlib.import_module("coach.utils.supabase_client")
        client = SimpleNamespace(table=lambda name: _Table(db, name))
        monkeypatch.setattr(sbmod, "get_supabase", lambda: client)
        monkeypatch.setattr(athlete, "legacy_single_athlete_mode", lambda: True)
        yield SimpleNamespace(garmin=garmin, db=db, state=garmin_state, monkeypatch=monkeypatch)
    finally:
        for k in [k for k in sys.modules if _is_project(k)]:
            del sys.modules[k]
        sys.modules.update(saved)


def test_rotated_tokens_survive_to_the_next_run(env):
    """Run 1: access token scaduto → refresh → token nuovi salvati.
    Run 2 (stesso secret): usa i token salvati, non il refresh token bruciato."""
    env.monkeypatch.setenv("GARMIN_SESSION_JSON", _secret(_tokens(500, "r0")))
    env.garmin._login()                       # run 1: refresh r0 → r1
    stored = env.db["service_tokens"]["garmin:test-athlete"]["payload"]
    assert json.loads(stored)["di_refresh_token"] == "r1"

    env.state["now"] = 10_000                 # l'access token di r1 scade
    env.garmin._login()                       # run 2: deve partire da r1, non da r0
    assert env.state["refreshes"] == 2


def test_without_persistence_the_second_run_fails(env):
    """Riproduce il guasto: senza tabella, il run 2 riusa r0 → 401."""
    env.db["broken"] = True
    env.monkeypatch.setenv("GARMIN_SESSION_JSON", _secret(_tokens(500, "r0")))
    env.garmin._login()
    env.state["now"] = 10_000
    with pytest.raises(Exception, match="social profile"):
        env.garmin._login()


def test_tokens_rotated_by_a_failed_login_are_saved(env):
    """07/10: l'API rifiuta il token, la libreria fa il refresh (ruotando il
    refresh token) e poi fallisce. Il refresh token nuovo va salvato lo stesso,
    altrimenti il tentativo successivo riparte da quello bruciato del secret."""
    env.monkeypatch.setenv("GARMIN_SESSION_JSON", _secret(_tokens(500, "r0")))
    env.state["api_rejects"] = True
    with pytest.raises(Exception, match="social profile"):
        env.garmin._login()
    stored = env.db["service_tokens"]["garmin:test-athlete"]["payload"]
    assert json.loads(stored)["di_refresh_token"] == "r1"

    env.state["api_rejects"] = False           # tentativo successivo
    env.state["now"] = 10_000
    env.garmin._login()
    assert env.state["refreshes"] == 2


def test_freshly_regenerated_secret_wins_over_stale_db(env):
    env.db["service_tokens"] = {"garmin:test-athlete": {
        "name": "garmin:test-athlete", "payload": _tokens(900, "old")}}
    env.monkeypatch.setenv("GARMIN_SESSION_JSON", _secret(_tokens(50_000, "fresh")))
    _, chosen = env.garmin._restore_garmin_session()
    assert json.loads(chosen)["di_refresh_token"] == "fresh"


def test_auth_error_tells_how_to_fix(env, monkeypatch):
    env.db["broken"] = True
    env.monkeypatch.setenv("GARMIN_SESSION_JSON", _secret(_tokens(500, "r0")))
    env.state["used_refresh"].add("r0")
    recorded = {}
    monkeypatch.setattr(env.garmin, "record_health",
                        lambda comp, success, error=None, **k: recorded.update(error=error))
    with pytest.raises(Exception, match="social profile"):
        env.garmin.main()
    assert recorded["error"].startswith("AUTH:")
    assert "garmin_first_login.py" in recorded["error"]
