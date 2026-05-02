"""Snapshot DB cifrato → Supabase Storage bucket dr-snapshots.

Esporta tutte le tabelle in JSON, cifra con AES-256-GCM, upload con timestamp.
Aggiorna docs/DR_INDEX.md per tracking versionato in git.

Restore: scripts/dr_restore.py <snapshot-id>.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from coach.utils.supabase_client import get_supabase
from coach.utils.health import record_health

logger = logging.getLogger(__name__)

TABLES = [
    "activities", "daily_wellness", "subjective_log", "physiology_zones",
    "daily_metrics", "mesocycles", "planned_sessions", "races", "health",
]
BUCKET = "dr-snapshots"


def export_all() -> dict:
    sb = get_supabase()
    out = {}
    for t in TABLES:
        # Pagine da 1000
        all_rows = []
        page = 0
        while True:
            res = sb.table(t).select("*").range(page * 1000, (page + 1) * 1000 - 1).execute()
            rows = res.data or []
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
            page += 1
        out[t] = all_rows
        logger.info("Exported %s: %d rows", t, len(all_rows))
    return out


def encrypt_blob(data: bytes, key_b64: str) -> bytes:
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise ValueError("DR_ENCRYPTION_KEY must be 32 bytes (AES-256)")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        snapshot = export_all()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        body = json.dumps(snapshot, default=str, separators=(",", ":")).encode()
        compressed = gzip.compress(body)
        encrypted = encrypt_blob(compressed, os.environ["DR_ENCRYPTION_KEY"])

        sb = get_supabase()
        path = f"snapshot_{ts}.bin"
        sb.storage.from_(BUCKET).upload(path, encrypted, {"content-type": "application/octet-stream"})

        # Update DR_INDEX.md
        index_path = Path("docs/DR_INDEX.md")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        existing = index_path.read_text() if index_path.exists() else "# DR Snapshot Index\n\n| timestamp | path | size_bytes |\n|---|---|---|\n"
        new_line = f"| {ts} | {path} | {len(encrypted)} |\n"
        # Append in cima alla tabella
        lines = existing.split("\n")
        # Trova la riga separatrice dell'intestazione
        for i, l in enumerate(lines):
            if l.startswith("|---"):
                lines.insert(i + 1, new_line.rstrip())
                break
        index_path.write_text("\n".join(lines))

        record_health("dr_snapshot", success=True, metadata={"path": path, "size": len(encrypted)})
        logger.info("DR snapshot: %s (%d bytes)", path, len(encrypted))
    except Exception as e:  # noqa: BLE001
        logger.exception("DR snapshot failed")
        record_health("dr_snapshot", success=False, error=str(e))
        raise


if __name__ == "__main__":
    main()
