import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import BACKUP_CHANNEL_ID, GEMINI_MODEL, MEMORY_FILE, get_ai_client


SCHEMA_VERSION = 2
MAX_RECENT_TURNS = 20
EXTRACTION_INTERVAL = 8
memory_needs_backup = False
logger = logging.getLogger(__name__)


def _empty_memory() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "users": {},
        "chats": {},
        "guest_contexts": {},
    }


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def load_memory() -> Dict[str, Any]:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return migrate_memory_if_needed(json.load(f))
        except Exception:
            logger.exception("Could not load memory file")
    return _empty_memory()


def migrate_memory_if_needed(mem: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    mem = mem or _empty_memory()
    if mem.get("schema_version") == SCHEMA_VERSION:
        mem.setdefault("users", {})
        mem.setdefault("chats", {})
        mem.setdefault("guest_contexts", {})
        return mem

    migrated = _empty_memory()
    for user_id, profile in mem.get("users", {}).items():
        if not isinstance(profile, dict):
            continue
        new_profile = _default_user_profile()
        new_profile["mode"] = profile.get("mode", "friend")
        facts = profile.get("facts", "")
        if facts:
            if isinstance(facts, list):
                new_profile["facts"] = facts
            else:
                new_profile["facts"] = [{"text": str(facts), "source": "migration", "created_at": _now()}]
        migrated["users"][str(user_id)] = new_profile

    for chat_id, history in mem.get("chats", {}).items():
        chat = _default_chat_profile()
        if isinstance(history, list):
            for item in history[-MAX_RECENT_TURNS:]:
                if isinstance(item, dict):
                    chat["recent_messages"].append(
                        {
                            "role": item.get("role", "user"),
                            "text": item.get("text", ""),
                            "created_at": _now(),
                            "source": "migration",
                        }
                    )
        elif isinstance(history, dict):
            chat.update(history)
        migrated["chats"][str(chat_id)] = chat
    return migrated


memory_db = load_memory()


def replace_memory(mem: Dict[str, Any]) -> None:
    global memory_db
    memory_db = migrate_memory_if_needed(mem)


def save_memory(mem: Optional[Dict[str, Any]] = None) -> None:
    global memory_needs_backup
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem or memory_db, f, indent=4)
        memory_needs_backup = True
    except Exception:
        logger.exception("Could not save memory")


def _default_user_profile() -> Dict[str, Any]:
    return {
        "mode": "friend",
        "name": "",
        "username": "",
        "facts": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


def _default_chat_profile() -> Dict[str, Any]:
    return {
        "summary": "",
        "chat_context": "",
        "facts": [],
        "participants": {},
        "recent_messages": [],
        "observed_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _default_participant_profile() -> Dict[str, Any]:
    return {
        "display_name": "",
        "username": "",
        "facts": [],
        "recent_context": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


def _chat_key(chat_id: Optional[int]) -> Optional[str]:
    return str(chat_id) if chat_id is not None else None


def _user_key(user_id: Optional[int]) -> Optional[str]:
    return str(user_id) if user_id is not None else None


def _get_chat(chat_id: Optional[int]) -> Optional[Dict[str, Any]]:
    key = _chat_key(chat_id)
    if not key:
        return None
    return memory_db.setdefault("chats", {}).setdefault(key, _default_chat_profile())


def _get_user(user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    key = _user_key(user_id)
    if not key:
        return None
    return memory_db.setdefault("users", {}).setdefault(key, _default_user_profile())


def get_user_settings(user_id: Optional[int]) -> Dict[str, Any]:
    user = _get_user(user_id)
    return user or {}


def set_user_mode(user_id: int, mode: str) -> None:
    user = _get_user(user_id)
    if not user:
        return
    user["mode"] = mode
    user["updated_at"] = _now()
    save_memory()


def _fact_text(fact: Any) -> str:
    if isinstance(fact, dict):
        return str(fact.get("text", ""))
    return str(fact)


def _append_unique_fact(items: List[Any], text: str, source: str, confidence: float = 1.0) -> None:
    text = (text or "").strip()
    if not text:
        return
    normalized = text.lower()
    if any(_fact_text(item).strip().lower() == normalized for item in items):
        return
    items.append({"text": text, "source": source, "confidence": confidence, "created_at": _now()})


def upsert_user_profile(ctx) -> None:
    user = _get_user(ctx.user_id)
    if not user:
        return
    if ctx.sender_name and ctx.sender_name != "Someone":
        user["name"] = ctx.sender_name
    user["updated_at"] = _now()


def upsert_chat_profile(ctx) -> None:
    chat = _get_chat(ctx.chat_id)
    if not chat:
        return
    if ctx.chat_context:
        chat["chat_context"] = ctx.chat_context
    chat["updated_at"] = _now()
    if ctx.user_id:
        participant = chat.setdefault("participants", {}).setdefault(str(ctx.user_id), _default_participant_profile())
        if ctx.sender_name and ctx.sender_name != "Someone":
            participant["display_name"] = ctx.sender_name
        participant["updated_at"] = _now()


def _turn_from_context(ctx, role: str, text: str, passive: bool = False) -> Dict[str, Any]:
    turn = {
        "role": role,
        "text": text,
        "source": ctx.source,
        "chat_type": ctx.effective_chat_type,
        "user_id": ctx.user_id,
        "sender_name": ctx.sender_name,
        "chat_context": ctx.chat_context,
        "passive": passive,
        "created_at": _now(),
    }
    if getattr(ctx, "media", None):
        turn["media"] = {
            "kind": ctx.media.kind,
            "description": ctx.media.description,
            "mime_type": ctx.media.mime_type,
            "file_size": ctx.media.file_size,
        }
    return turn


def record_turn(ctx, role: str, text: str, passive: bool = False) -> None:
    chat = _get_chat(ctx.chat_id)
    if not chat or not text:
        return
    upsert_user_profile(ctx)
    upsert_chat_profile(ctx)
    chat["recent_messages"].append(_turn_from_context(ctx, role, text, passive))
    chat["recent_messages"] = chat["recent_messages"][-MAX_RECENT_TURNS:]
    chat["observed_count"] = int(chat.get("observed_count", 0)) + 1
    if ctx.source == "guest" and ctx.chat_context:
        memory_db.setdefault("guest_contexts", {})[_chat_key(ctx.chat_id) or ctx.guest_query_id or "unknown"] = {
            "chat_context": ctx.chat_context,
            "updated_at": _now(),
        }
    save_memory()


def add_message_to_history(chat_id: Optional[int], role: str, text: str) -> None:
    class LegacyContext:
        source = "legacy"
        effective_chat_type = "dm"
        user_id = None
        sender_name = "Someone"
        chat_context = ""
        guest_query_id = None

        def __init__(self, chat_id):
            self.chat_id = chat_id

    record_turn(LegacyContext(chat_id), role, text)


def observe_context(chat_id: Optional[int], text: str) -> None:
    class ObservedContext:
        source = "business"
        effective_chat_type = "business"
        user_id = None
        sender_name = "Someone"
        chat_context = ""
        guest_query_id = None

        def __init__(self, chat_id):
            self.chat_id = chat_id

    if chat_id and text:
        record_turn(ObservedContext(chat_id), "user", f"[Observed secretary context]\n{text}", passive=True)


def get_context_bundle(ctx) -> str:
    chat = _get_chat(ctx.chat_id) or {}
    user = _get_user(ctx.user_id) or {}
    participants = chat.get("participants", {})
    participant = participants.get(str(ctx.user_id), {}) if ctx.user_id else {}

    parts = []
    if chat.get("chat_context"):
        parts.append(f"Chat identity: {chat['chat_context']}")
    if chat.get("summary"):
        parts.append(f"Chat summary: {chat['summary']}")
    user_facts = [_fact_text(fact) for fact in user.get("facts", []) if _fact_text(fact)]
    if user_facts:
        parts.append("Known facts about this user: " + "; ".join(user_facts[-8:]))
    chat_facts = [_fact_text(fact) for fact in chat.get("facts", []) if _fact_text(fact)]
    if chat_facts:
        parts.append("Known facts about this chat: " + "; ".join(chat_facts[-8:]))
    participant_facts = [_fact_text(fact) for fact in participant.get("facts", []) if _fact_text(fact)]
    if participant_facts:
        parts.append("Known chat-specific facts about this participant: " + "; ".join(participant_facts[-6:]))
    recent = chat.get("recent_messages", [])[-6:]
    if recent:
        recent_text = " | ".join(f"{item.get('sender_name') or item.get('role')}: {item.get('text', '')[:160]}" for item in recent)
        parts.append("Recent context: " + recent_text)
    return "\n".join(parts)


def get_chat_history(chat_id: Optional[int]) -> List[Any]:
    from google.genai import types

    chat = _get_chat(chat_id)
    if not chat:
        return []
    history = []
    for msg in chat.get("recent_messages", [])[-10:]:
        role = "model" if msg.get("role") == "model" else "user"
        history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.get("text", ""))]))
    return history


def _should_extract(ctx, text: str) -> bool:
    lowered = (text or "").lower()
    triggers = ("remember", "don't forget", "dont forget", "my name is", "this is", "call me")
    if any(trigger in lowered for trigger in triggers):
        return True
    chat = _get_chat(ctx.chat_id)
    return bool(chat and int(chat.get("observed_count", 0)) % EXTRACTION_INTERVAL == 0)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    candidate = match.group(0) if match else text
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _apply_extracted_memory(ctx, extracted: Dict[str, Any], source: str) -> bool:
    confidence = float(extracted.get("confidence", 0.7) or 0.7)
    if confidence < 0.45:
        return False
    chat = _get_chat(ctx.chat_id)
    user = _get_user(ctx.user_id)
    changed = False

    if user:
        for fact in extracted.get("user_facts", []) or []:
            before = len(user["facts"])
            _append_unique_fact(user["facts"], str(fact), source, confidence)
            changed = changed or len(user["facts"]) != before

    if chat:
        for fact in extracted.get("chat_facts", []) or []:
            before = len(chat["facts"])
            _append_unique_fact(chat["facts"], str(fact), source, confidence)
            changed = changed or len(chat["facts"]) != before

        participant_facts = extracted.get("participant_facts", {}) or {}
        if isinstance(participant_facts, list) and ctx.user_id:
            participant_facts = {str(ctx.user_id): participant_facts}
        if isinstance(participant_facts, dict):
            for user_id, facts in participant_facts.items():
                participant = chat.setdefault("participants", {}).setdefault(str(user_id), _default_participant_profile())
                for fact in facts or []:
                    before = len(participant["facts"])
                    _append_unique_fact(participant["facts"], str(fact), source, confidence)
                    changed = changed or len(participant["facts"]) != before

        summary = (extracted.get("summary_update") or "").strip()
        if summary:
            chat["summary"] = summary
            changed = True
    if changed:
        save_memory()
    return changed


async def maybe_extract_memory(ctx, ai_reply: Optional[str] = None, passive: bool = False) -> None:
    prompt_text = ctx.prompt_text()
    if not _should_extract(ctx, prompt_text):
        return
    source = "secretary_observed" if passive or ctx.effective_chat_type == "business" else ctx.source
    extraction_prompt = (
        "Extract only durable memory from this Telegram context. Return strict JSON only with keys: "
        "user_facts, chat_facts, participant_facts, summary_update, confidence, reason. "
        "Save names, nicknames, preferences, relationships, recurring projects, group roles, inside jokes, and important decisions. "
        "Ignore temporary mood, one-off locations, private documents, contact cards, payment data, and random chatter unless explicitly asked to remember.\n\n"
        f"Existing context:\n{get_context_bundle(ctx)}\n\n"
        f"New message:\n{prompt_text}\n\n"
        f"AI reply:\n{ai_reply or ''}"
    )
    try:
        from google.genai import types

        response = get_ai_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=extraction_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction="You are a strict JSON memory extraction engine. Return JSON only."
            ),
        )
        extracted = _extract_json(response.text or "")
        if extracted:
            _apply_extracted_memory(ctx, extracted, source)
    except Exception:
        logger.exception("Memory extraction failed")


def remember_fact(ctx, fact: str) -> None:
    chat = _get_chat(ctx.chat_id)
    user = _get_user(ctx.user_id)
    if user:
        _append_unique_fact(user["facts"], fact, "manual")
    if chat:
        _append_unique_fact(chat["facts"], fact, "manual")
    save_memory()


def forget_keyword(ctx, keyword: str) -> int:
    keyword = (keyword or "").lower().strip()
    if not keyword:
        return 0
    removed = 0
    containers = []
    user = _get_user(ctx.user_id)
    chat = _get_chat(ctx.chat_id)
    if user:
        containers.append(user.get("facts", []))
    if chat:
        containers.append(chat.get("facts", []))
        for participant in chat.get("participants", {}).values():
            containers.append(participant.get("facts", []))
    for items in containers:
        before = len(items)
        items[:] = [item for item in items if keyword not in _fact_text(item).lower()]
        removed += before - len(items)
    if removed:
        save_memory()
    return removed


def reset_chat_memory(chat_id: Optional[int]) -> None:
    chat = _get_chat(chat_id)
    if chat:
        memory_db["chats"][str(chat_id)] = _default_chat_profile()
        save_memory()


def reset_all_memory() -> None:
    replace_memory(_empty_memory())
    save_memory()


def format_memory_for_context(ctx) -> str:
    bundle = get_context_bundle(ctx)
    return bundle or "nothing permanent yet. very blank slate energy."


async def restore_memory_from_backup(telegram_app) -> None:
    if not BACKUP_CHANNEL_ID:
        return
    try:
        chat = await telegram_app.bot.get_chat(BACKUP_CHANNEL_ID)
        if chat.pinned_message and chat.pinned_message.document:
            file = await telegram_app.bot.get_file(chat.pinned_message.document.file_id)
            file_bytes = await file.download_as_bytearray()
            with open(MEMORY_FILE, "wb") as f:
                f.write(file_bytes)
            replace_memory(load_memory())
            save_memory()
            logger.info("Memory restored from Telegram backup channel")
    except Exception:
        logger.exception("Could not restore memory from Telegram")


async def memory_backup_loop(telegram_app) -> None:
    global memory_needs_backup
    while True:
        await asyncio.sleep(60)
        if memory_needs_backup and BACKUP_CHANNEL_ID:
            try:
                with open(MEMORY_FILE, "rb") as f:
                    msg = await telegram_app.bot.send_document(
                        chat_id=BACKUP_CHANNEL_ID,
                        document=f,
                        caption="Database Backup",
                    )
                await telegram_app.bot.pin_chat_message(
                    chat_id=BACKUP_CHANNEL_ID,
                    message_id=msg.message_id,
                    disable_notification=True,
                )
                memory_needs_backup = False
            except Exception:
                logger.exception("Memory backup failed")
