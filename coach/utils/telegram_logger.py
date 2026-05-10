"""Utility per inviare messaggi Telegram e loggarli in bot_messages per reply threading."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import requests

from coach.utils.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def send_and_log_message(
    message: str,
    purpose: str,
    context_data: Optional[dict] = None,
    parent_workflow: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    reply_markup: Optional[dict] = None,
) -> Optional[int]:
    """Invia messaggio Telegram e logga in bot_messages per reply threading.

    Returns:
        message_id Telegram se successo, None altrimenti
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])

    payload: dict = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        msg_id: Optional[int] = resp.json().get("result", {}).get("message_id")

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
        logger.exception("Failed to send/log Telegram message (purpose=%s)", purpose)
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
