"""Diagnostica auth Garmin dal runner CI (non stampa token né segreti).

Distingue "token non valido" da "Garmin rifiuta questo client/rete":
1. età e scadenza dei token (secret e service_tokens) e quale viene usato
2. chiamata API con requests e con curl_cffi (impronta TLS da browser)
3. se l'API risponde 401: refresh del token (i token ruotati vengono salvati
   in service_tokens) e nuova chiamata

    PYTHONPATH=. python -m scripts.garmin_diag
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

from coach.ingest import garmin

API = "https://connectapi.garmin.com/userprofile-service/socialProfile"
HEADERS_OF_INTEREST = ("server", "cf-ray", "www-authenticate", "content-type", "x-request-id")


def _claims(payload: Optional[str]) -> dict:
    if not payload:
        return {}
    try:
        token = json.loads(payload).get("di_token") or ""
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:  # noqa: BLE001
        return {}


def _ts(v) -> str:
    return datetime.fromtimestamp(float(v), timezone.utc).isoformat() if v else "?"


def _describe(label: str, payload: Optional[str]) -> None:
    if not payload:
        print(f"[{label}] assente")
        return
    data = json.loads(payload)
    c = _claims(payload)
    print(f"[{label}] emesso={_ts(c.get('iat'))} scade={_ts(c.get('exp'))} "
          f"client_id={c.get('client_id') or data.get('di_client_id')} "
          f"refresh_token={'sì' if data.get('di_refresh_token') else 'NO'}")


def _call(label: str, get, token: str) -> int:
    from garminconnect.client import _native_headers  # type: ignore
    headers = _native_headers({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        r = get(API, headers=headers, timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] errore di rete: {type(exc).__name__}: {exc}")
        return -1
    hdr = {k: r.headers.get(k) for k in HEADERS_OF_INTEREST if r.headers.get(k)}
    body = (r.text or "")[:200].replace("\n", " ")
    print(f"[{label}] HTTP {r.status_code} headers={hdr} body={body!r}")
    return r.status_code


def _probe(token: str) -> int:
    status = _call("requests", requests.get, token)
    try:
        from curl_cffi import requests as creq  # type: ignore
        _call("curl_cffi chrome", lambda u, **kw: creq.get(u, impersonate="chrome", **kw), token)
    except ImportError:
        print("[curl_cffi] non installato")
    return status


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    try:
        ip = requests.get("https://api.ipify.org", timeout=10).text
        print(f"IP runner: {ip}")
    except Exception:  # noqa: BLE001
        pass

    tokendir, chosen = garmin._restore_garmin_session()
    secret = json.loads(base64.b64decode(os.environ["GARMIN_SESSION_JSON"]))
    secret_tokens = secret.get(garmin.TOKEN_FILE)
    _describe("secret", secret_tokens if isinstance(secret_tokens, str) else json.dumps(secret_tokens))
    _describe("service_tokens", garmin._load_stored_tokens())
    print(f"In uso: {'secret' if chosen == secret_tokens else 'service_tokens'}")

    data = json.loads(chosen)
    if _probe(data["di_token"]) != 401:
        return

    print("API 401 → provo il refresh del token")
    from garminconnect import Garmin  # type: ignore
    g = Garmin()
    g.client.load(str(tokendir))
    try:
        g.client._refresh_di_token()
    except Exception as exc:  # noqa: BLE001
        print(f"[refresh] FALLITO: {exc}")
        return
    g.client.dump(str(tokendir))
    garmin._save_tokens(tokendir, chosen)  # il refresh token è ruotato: va salvato
    _describe("dopo refresh", (tokendir / garmin.TOKEN_FILE).read_text())
    _probe(g.client.di_token)


if __name__ == "__main__":
    main()
