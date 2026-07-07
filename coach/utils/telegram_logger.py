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

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    first_msg_id: Optional[int] = None
    markup_msg_id: Optional[int] = None

    for i, chunk in enumerate(chunks):
        base_payload: dict = {
            "chat_id": chat_id,
            "disable_web_page_preview": True,
        }
        # reply_markup solo sull'ultimo chunk (bottoni in fondo)
        if reply_markup and i == len(chunks) - 1:
            base_payload["reply_markup"] = reply_markup

        mid = _post_chunk(url, base_payload, chunk, purpose)
        if mid is None:
            # Invio fallito anche col fallback testo semplice: interrompo.
            # NON ritorno subito: l'eventuale parziale già inviato (first_msg_id)
            # va comunque loggato, altrimenti l'idempotency non lo vede e il
            # cron successivo duplica il messaggio.
            break
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


def _html_to_plain(message: str) -> str:
    """Rimuove i tag HTML e decodifica le entità — fallback quando Telegram
    rifiuta il parse_mode HTML (es. testo con '<', '>' non escaped)."""
    return unescape(re.sub(r"<[^>]+>", "", message))


def _post_chunk(url: str, base_payload: dict, text: str, purpose: str) -> Optional[int]:
    """Invia un singolo chunk: prima in HTML, poi (fallback) in testo semplice se
    Telegram rifiuta il parse (400 / ok:false). Un errore di formattazione non
    deve mai azzerare il messaggio (es. il brief mattutino). Ritorna message_id."""
    attempts = [
        {**base_payload, "text": text, "parse_mode": "HTML"},
        {**base_payload, "text": _html_to_plain(text)},
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

            parse_rejected = (resp.status_code == 400) or (resp.ok and not body.get("ok"))
            if parse_rejected and not is_fallback:
                logger.warning(
                    "Telegram ha rifiutato l'HTML (purpose=%s): %s. Ritento in testo semplice.",
                    purpose, body.get("description", resp.text[:200]),
                )
                continue

            resp.raise_for_status()
            if not body.get("ok"):
                logger.error("Telegram ok:false (purpose=%s): %s", purpose, body)
                return None

            if is_fallback:
                logger.warning("Telegram inviato in testo semplice (fallback HTML, purpose=%s)", purpose)
            return body.get("result", {}).get("message_id")

        except Exception:
            if not is_fallback:
                logger.warning(
                    "Invio HTML fallito (purpose=%s), ritento in testo semplice.",
                    purpose, exc_info=True,
                )
                continue
            logger.exception("Failed to send Telegram chunk (purpose=%s)", purpose)
            return None
    return None


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
        # guard `current`: con current vuoto e riga lunga esattamente = limit
        # veniva appeso un chunk vuoto.
        if current and len(current) + len(line) + 1 > limit:
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

    # 1 retry: un fallimento transitorio qui significa "brief inviato ma non
    # registrato" → l'idempotency non lo vede e il cron successivo lo duplica.
    for attempt in range(2):
        try:
            sb = get_supabase()
            sb.table("bot_messages").upsert(record, on_conflict="telegram_message_id").execute()
            return
        except Exception:
            if attempt == 0:
                logger.warning(
                    "Failed to log bot_message (id=%s, purpose=%s) — retrying once",
                    telegram_message_id, purpose, exc_info=True,
                )
            else:
                logger.exception(
                    "Failed to log bot_message after retry (id=%s, purpose=%s)",
                    telegram_message_id, purpose,
                )
