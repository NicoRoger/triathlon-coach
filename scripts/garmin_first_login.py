"""Login iniziale Garmin: crea cache token, la stampa in base64 per GitHub Secret.

Esegui una volta in locale:
    python scripts/garmin_first_login.py

Poi copia l'output in GitHub Secret `GARMIN_SESSION_JSON`
(repo → Settings → Secrets and variables → Actions).

Re-eseguilo quando il watchdog segnala "AUTH: token Garmin non più valido".
Dal 06/10/2026 l'ingest salva da solo i token rinnovati (tabella
service_tokens, migration 2026-10-06): prima li perdeva a ogni run e il
refresh token del secret, a rotazione, scadeva al primo rinnovo.
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
        print("Installa: pip install garminconnect")
        sys.exit(1)

    email = input("Email Garmin: ").strip()
    password = getpass.getpass("Password: ")

    tokendir = Path.home() / ".garminconnect"
    tokendir.mkdir(exist_ok=True)
    os.environ["GARMINTOKENS"] = str(tokendir)

    # Con la verifica in due passaggi attiva Garmin chiede il codice ricevuto
    # via email/app: senza prompt_mfa il login falliva senza spiegazioni.
    g = Garmin(email, password, prompt_mfa=lambda: input("Codice MFA Garmin: ").strip())
    g.login()
    print(f"\nToken salvati in: {tokendir}")

    # Encode all files to base64 JSON
    files = {}
    for f in tokendir.iterdir():
        if f.is_file():
            files[f.name] = f.read_text()

    encoded = base64.b64encode(json.dumps(files).encode()).decode()
    print("\n=== GARMIN_SESSION_JSON (copia tutto) ===")
    print(encoded)
    print("\n=== Incollalo nel GitHub Secret GARMIN_SESSION_JSON ===")
    print("Poi lancia a mano il workflow 'ingest' (Actions → ingest → Run workflow).")


if __name__ == "__main__":
    main()
