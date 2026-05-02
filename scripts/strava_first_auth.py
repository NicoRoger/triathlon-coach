"""Esegui scambio OAuth Strava: code → refresh_token. Una sola volta in setup.

Procedura:
1. Vai su Strava → Settings → My API Application, copia Client ID e Secret
2. Apri in browser:
   https://www.strava.com/oauth/authorize?client_id=<CLIENT_ID>&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all,profile:read_all
3. Autorizza, copia il `code` dall'URL di redirect (anche se la pagina dà errore di
   connessione: il code è nell'URL)
4. Esegui questo script con il code

    python scripts/strava_first_auth.py
"""
from __future__ import annotations

import getpass
import json
import sys

import requests


def main() -> None:
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client Secret: ")
    code = input("Code (dall'URL di redirect): ").strip()

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Errore: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    print("\n✅ OAuth completato")
    print(f"refresh_token: {data['refresh_token']}")
    print(f"access_token (vita ~6h): {data['access_token']}")
    print("\n=== Aggiungi a GitHub Secrets ===")
    print(f"STRAVA_CLIENT_ID={client_id}")
    print(f"STRAVA_CLIENT_SECRET=<già hai>")
    print(f"STRAVA_REFRESH_TOKEN={data['refresh_token']}")


if __name__ == "__main__":
    main()
