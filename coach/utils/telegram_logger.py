"""Utility per inviare messaggi Telegram e loggarli in bot_messages per reply threading."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from html import unescape
from typing import Optional

import requests

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _html_to_plain(message: str) -> str:
    """Rimuove i tag HTML e decodifica le entità — fallback quando Telegram
    rifiuta il parse_mode HTML (es. testo con '<', '>' non escaped)."""
    no_tags = re.sub(r"<[^>]+>", "", message)
    return unescape(no_tags)


def send_and_log_message(
    message: str,
    purpose: str,
    context_data: Optional[dict] = None,
    parent_workflow: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    reply_markup: Optional[dict] = None,
) -> Optional[int]:
    """Invia messaggio Telegram e logga in bot_messages per reply threading.

    Resilienza: se Telegram rifiuta l'HTML (400 Bad Request / ok=false per
    entità malformate), ritenta automaticamente in testo semplice. Un errore di
    formattazione non deve mai azzerare il messaggio (es. il brief mattutino).

    Returns:
        message_id Telegram se successo, None altrimenti
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])

    base_payload: dict = {
        "chat_id": chat_id,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        base_payload["reply_markup"] = reply_markup

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Tentativo 1: HTML. Tentativo 2 (fallback): testo semplice senza tag.
    attempts = [
        {**base_payload, "text": message, "parse_mode": "HTML"},
        {**base_payload, "text": _html_to_plain(message)},
    ]

    for i, payload in enumerate(attempts):
        is_fallback = i > 0
        try:
            resp = requests.post(url, json=payload, timeout=30)
            body: dict = {}
            try:
                body = resp.json()
            except Exception:
                pass

            # 400 o ok=false su HTML → ritenta in plain text
            parse_rejected = (resp.status_code == 400) or (
                resp.ok and not body.get("ok")
            )
            if parse_rejected and not is_fallback:
                logger.warning(
                    "Telegram ha rifiutato l'HTML (purpose=%s): %s. Ritento in testo semplice.",
                    purpose, body.get("description", resp.text[:200]),
                )
                continue

            resp.raise_for_status()
            if not body.get("ok"):
                logger.error(
                    "Telegram API ok=false (purpose=%s): %s",
                    purpose, body.get("description", body),
                )
                return None

            if is_fallback:
                logger.warning("Telegram inviato in testo semplice (fallback HTML, purpose=%s)", purpose)

            msg_id: Optional[int] = (body.get("result") or {}).get("message_id")
            if msg_id:
                _log_bot_message(
                    telegram_message_id=msg_id,
                    chat_id=chat_id,
                    purpose=purpose,
                    context_data=context_data,
                    parent_workflow=parent_workflow,
                    expires_at=expires_at,
                )
            return msg_id

        except Exception:
            if not is_fallback:
                logger.warning(
                    "Invio HTML fallito (purpose=%s), ritento in testo semplice.", purpose,
                    exc_info=True,
                )
                continue
            logger.exception("Failed to send/log Telegram message (purpose=%s)", purpose)
            return None

    return None


def _log_bot_message(
    telegram_message_id: int,
    chat_id: int,
    purpose: str,
    context_data: Optional[dict] = None,
    parent_workflow: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> None:
    record: dict = {
        "telegram_message_id": telegram_message_id,
        "chat_id": chat_id,
        "purpose": purpose,
    }
    if context_data is not None:
        record["context_data"] = context_data
    if parent_workflow is not None:
        record["parent_workflow"] = parent_workflow
    if expires_at is not None:
        record["expires_at"] = expires_at.isoformat()

    try:
        sb = get_supabase()
        sb.table("bot_messages").upsert(record, on_conflict="telegram_message_id").execute()
    except Exception:
        logger.exception("Failed to log bot_message (id=%s, purpose=%s)", telegram_message_id, purpose)
