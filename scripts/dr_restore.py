"""Restore da snapshot DR cifrato.

Uso:
    PYTHONPATH=. python -m scripts.dr_restore <snapshot_path>

Esempio:
    python -m scripts.dr_restore snapshot_20250429T020000Z.bin

ATTENZIONE: sovrascrive le tabelle. Eseguire SOLO su DB ricreato vuoto o per
recovery completo. Per test, fare prima dump locale come backup.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)
BUCKET = "dr-snapshots"

# Ordine importante per FK — deriva dalla stessa lista dello snapshot, così
# le due non possono divergere: quando una migration aggiunge una tabella la
# si dichiara in UN posto solo.
#
# L'ordine precedente metteva `physiology_zones` PRIMA di `activities`, ma
# physiology_zones.test_activity_id è FK verso activities(id) e nei dump reali
# è popolato: il restore esplodeva a metà (races e mesocycles già scritti,
# activities e wellness mai) lasciando il DB inconsistente proprio durante un
# disaster recovery.
from scripts.dr_snapshot import TABLES as RESTORE_ORDER  # noqa: E402


def decrypt(blob: bytes, key_b64: str) -> bytes:
    key = base64.b64decode(key_b64)
    aesgcm = AESGCM(key)
    nonce, ct = blob[:12], blob[12:]
    return aesgcm.decrypt(nonce, ct, None)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.dr_restore <snapshot_path>")
        sys.exit(2)

    path = sys.argv[1]
    sb = get_supabase()

    # Download from storage
    encrypted = sb.storage.from_(BUCKET).download(path)
    decrypted = decrypt(encrypted, os.environ["DR_ENCRYPTION_KEY"])
    decompressed = gzip.decompress(decrypted)
    snapshot = json.loads(decompressed)

    print("Snapshot contiene:")
    for t, rows in snapshot.items():
        print(f"  {t}: {len(rows)} righe")

    confirm = input("\nProcedere con restore? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Annullato.")
        return

    for table in RESTORE_ORDER:
        rows = snapshot.get(table, [])
        if not rows:
            continue
        # Insert a batch di 500
        for i in range(0, len(rows), 500):
            batch = rows[i:i + 500]
            sb.table(table).upsert(batch).execute()
        logger.info("Restored %s: %d rows", table, len(rows))

    print("\n✅ Restore completato.")


if __name__ == "__main__":
    main()
