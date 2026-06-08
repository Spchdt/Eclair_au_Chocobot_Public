import logging
import re
import uuid
from typing import Optional, Tuple

try:
    from telegram.error import BadRequest
except Exception:
    class BadRequest(Exception):
        pass

from . import memory
from .config import MAX_FILE_SIZE, TOKEN
from .normalizer import IncomingContext


logger = logging.getLogger(__name__)


def split_message(text: str, limit: int = 3900):
    text = text or ""
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def split_chat_bubbles(text: str, limit: int = 650):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    bubbles = []
    sections = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    current = ""
    for section in sections:
        if len(section) > limit:
            if current:
                bubbles.append(current)
                current = ""
            bubbles.extend(split_message(section, limit))
            continue
        candidate = f"{current}\n\n{section}".strip() if current else section
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                bubbles.append(current)
            current = section
    if current:
        bubbles.append(current)
    return bubbles


def split_word_bubbles(text: str, max_words: int = 30):
    bubbles = []
    for chunk in split_chat_bubbles(text):
        words = chunk.split()
        if len(words) <= max_words:
            bubbles.append(chunk)
            continue
        for index in range(0, len(words), max_words):
            bubbles.append(" ".join(words[index:index + max_words]))
    return bubbles


async def set_typing(chat_id: int, business_conn_id: Optional[str] = None) -> None:
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            payload = {"chat_id": chat_id, "action": "typing"}
            if business_conn_id:
                payload["business_connection_id"] = business_conn_id
            await client.post(f"https://api.telegram.org/bot{TOKEN}/sendChatAction", json=payload)
    except Exception:
        logger.exception("Could not send typing action")


async def set_reaction(chat_id: int, message_id: int, emoji: str) -> None:
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TOKEN}/setMessageReaction",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reaction": [{"type": "emoji", "emoji": emoji}],
                },
            )
    except Exception:
        logger.exception("Could not set message reaction")


async def process_ai_reply(reply_text: str, ctx: IncomingContext) -> str:
    match = re.search(r"\[REACT:\s*(.+?)\]", reply_text or "")
    if match:
        emoji = match.group(1).strip()
        mode = memory.get_user_settings(ctx.user_id).get("mode")
        if ctx.message_id and ctx.chat_id and mode != "secretary" and ctx.effective_chat_type not in ("business", "guest"):
            await set_reaction(ctx.chat_id, ctx.message_id, emoji)
        reply_text = re.sub(r"\[REACT:\s*(.+?)\]", "", reply_text or "").strip()
        if ctx.effective_chat_type == "guest" and not reply_text:
            reply_text = emoji
    return reply_text or ""


async def safe_reply(message, text: str) -> None:
    for chunk in split_word_bubbles(text):
        try:
            await message.reply_text(chunk, parse_mode="Markdown")
        except BadRequest:
            await message.reply_text(chunk)


async def send_business_message(chat_id: int, conn_id: str, text: str) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        for chunk in split_word_bubbles(text):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
                "business_connection_id": conn_id,
            }
            res = await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)
            if res.status_code >= 400:
                payload.pop("parse_mode", None)
                await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)


async def answer_guest_query(guest_query_id: str, text: str) -> None:
    import httpx

    text = text or "✨"
    inline_result = {
        "type": "article",
        "id": str(uuid.uuid4()),
        "title": "AI Answer",
        "input_message_content": {
            "message_text": text[:4096],
            "parse_mode": "Markdown",
        },
    }
    async with httpx.AsyncClient() as client:
        payload = {"guest_query_id": str(guest_query_id), "result": inline_result}
        res = await client.post(f"https://api.telegram.org/bot{TOKEN}/answerGuestQuery", json=payload)
        if res.status_code >= 400:
            inline_result["input_message_content"].pop("parse_mode", None)
            res = await client.post(f"https://api.telegram.org/bot{TOKEN}/answerGuestQuery", json=payload)
        logger.info("answerGuestQuery returned status=%s body=%s", res.status_code, res.text)


async def build_media_part(bot, ctx: IncomingContext) -> Tuple[Optional[object], str]:
    media = ctx.media
    if not media:
        return None, ""
    if media.file_size and media.file_size > MAX_FILE_SIZE:
        return None, f"{media.description} is too large to inspect directly ({media.file_size} bytes)."
    try:
        from google.genai import types

        file = await bot.get_file(media.file_id)
        file_size = getattr(file, "file_size", None)
        if file_size and file_size > MAX_FILE_SIZE:
            return None, f"{media.description} is too large to inspect directly ({file_size} bytes)."
        file_bytes = await file.download_as_bytearray()
        return types.Part.from_bytes(data=file_bytes, mime_type=media.mime_type), ""
    except Exception as e:
        return None, f"Could not download {media.description}: {e}"
