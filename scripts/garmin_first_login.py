"""Login iniziale Garmin: crea cache token, la stampa in base64 per GitHub Secret.

Esegui una volta in locale:
    python scripts/garmin_first_login.py

Poi copia l'output in GitHub Secret `GARMIN_SESSION_JSON`.
Re-esegui se Garmin invalida la sessione (raro, ~6+ mesi).
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        from garminconnect import Garmin
    except ImportError:
        print("Installa: pip install python-garminconnect")
        sys.exit(1)

    email = input("Email Garmin: ").strip()
    password = getpass.getpass("Password: ")

    tokendir = Path.home() / ".garminconnect"
    tokendir.mkdir(exist_ok=True)

    g = Garmin(email, password)
    g.login()
    g.garth.dump(str(tokendir))
    print(f"\nToken salvati in: {tokendir}")

    # Encode all files to base64 JSON
    files = {}
    for f in tokendir.iterdir():
        if f.is_file():
            files[f.name] = f.read_text()

    encoded = base64.b64encode(json.dumps(files).encode()).decode()
    print("\n=== GARMIN_SESSION_JSON (copia tutto) ===")
    print(encoded)
    print("\n=== Aggiungi come GitHub Secret e Cloudflare secret ===")


if __name__ == "__main__":
    main()
