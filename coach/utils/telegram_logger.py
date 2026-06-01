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
    # Bug fix audit I5: env var con .get + validazione, niente KeyError/ValueError
    # non gestiti fuori dal try.
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id_raw = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id_raw:
        logger.error("Telegram non configurato (TELEGRAM_BOT_TOKEN/CHAT_ID mancanti)")
        return None
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        logger.error("TELEGRAM_CHAT_ID non numerico: %r", chat_id_raw)
        return None

    # Bug fix audit I5: split a ~4000 char (limite Telegram 4096) — un messaggio
    # lungo (es. weekly analysis) altrimenti riceve HTTP 400 e viene perso.
    chunks = _split_message(message, 4000)

    first_msg_id: Optional[int] = None
    markup_msg_id: Optional[int] = None
    try:
        for i, chunk in enumerate(chunks):
            payload: dict = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            # reply_markup solo sull'ultimo chunk (bottoni in fondo)
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            # Bug fix audit I5: Telegram può rispondere HTTP 200 con ok:false.
            if not body.get("ok"):
                logger.error("Telegram ok:false (purpose=%s): %s", purpose, body)
                return first_msg_id
            mid = body.get("result", {}).get("message_id")
            if i == 0:
                first_msg_id = mid
            if reply_markup and i == len(chunks) - 1:
                markup_msg_id = mid

        # Logga il messaggio rilevante per il reply threading: quello con i
        # bottoni se presente, altrimenti il primo.
        log_id = markup_msg_id or first_msg_id
        if log_id:
            _log_bot_message(
                telegram_message_id=log_id,
                chat_id=chat_id,
                purpose=purpose,
                context_data=context_data,
                parent_workflow=parent_workflow,
                expires_at=expires_at,
            )

        return markup_msg_id or first_msg_id

    except Exception:
        logger.exception("Failed to send/log Telegram message (purpose=%s)", purpose)
        return first_msg_id


def _split_message(text: str, limit: int) -> list[str]:
    """Divide un messaggio in chunk <= limit, preferendo i confini di riga."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        # riga singola più lunga del limite → hard split
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


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
