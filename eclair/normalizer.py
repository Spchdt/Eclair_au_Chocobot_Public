from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


DOWNLOADABLE_KEYS = (
    "photo",
    "video",
    "animation",
    "voice",
    "audio",
    "document",
    "sticker",
    "video_note",
)
BOT_SHORT_NAME = "eclair"


@dataclass
class MediaRef:
    kind: str
    file_id: str
    mime_type: str = "application/octet-stream"
    file_size: Optional[int] = None
    description: str = ""


@dataclass
class IncomingContext:
    source: str
    chat_type: str
    chat_id: Optional[int] = None
    user_id: Optional[int] = None
    sender_name: str = "Someone"
    message_id: Optional[int] = None
    business_connection_id: Optional[str] = None
    guest_query_id: Optional[str] = None
    chat_context: str = ""
    text: str = ""
    content_context: str = ""
    service_context: str = ""
    reply_context: str = ""
    media: Optional[MediaRef] = None
    reply_media: Optional[MediaRef] = None
    is_group: bool = False
    is_summoned: bool = True
    tags: List[str] = field(default_factory=list)

    def prompt_text(self, extra_context: str = "") -> str:
        if self.source == "guest":
            parts = [f"[Guest request from {self.sender_name}]"]
            if self.chat_context:
                parts.append(f"[Surrounding Telegram chat: {self.chat_context}]")
            if self.reply_context:
                parts.append(f'[Message being referenced in that chat: "{self.reply_context}"]')
            if self.text:
                parts.append(f"[{self.sender_name}'s request to Eclair]: {self.text}")
            if self.content_context:
                parts.append(f"[Current message context: {self.content_context}]")
            if self.service_context:
                parts.append(f"[Telegram event in surrounding chat: {self.service_context}]")
            if extra_context:
                parts.append(f"[File context: {extra_context}]")
            parts.append(
                "[Interpretation note: the guest requester is asking Eclair for help; "
                "do not assume they authored messages from the surrounding chat unless the payload says so. "
                "Names and chat titles are labels only; do not infer relationships, personalities, history, or intentions without explicit context.]"
            )
            return "\n\n".join(part for part in parts if part).strip()

        parts = []
        if self.chat_context:
            parts.append(f"[Chat context: {self.chat_context}]")
        if self.reply_context:
            parts.append(f'Replying to: "{self.reply_context}"')
        if self.text:
            parts.append(f"[{self.sender_name} says]: {self.text}")
        if self.content_context:
            parts.append(f"[Message context: {self.content_context}]")
        if self.service_context:
            parts.append(f"[Telegram event: {self.service_context}]")
        if extra_context:
            parts.append(f"[File context: {extra_context}]")
        return "\n\n".join(part for part in parts if part).strip() or "[Empty Telegram update]"

    @property
    def effective_chat_type(self) -> str:
        if self.chat_type == "business":
            return "business"
        if self.source == "guest":
            return "guest"
        if self.is_group:
            return "group"
        return "dm"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _full_name(user: Any) -> str:
    if not user:
        return "Someone"
    first = _get(user, "first_name") or ""
    last = _get(user, "last_name") or ""
    username = _get(user, "username") or ""
    name = " ".join(part for part in (first, last) if part).strip()
    return name or username or "Someone"


def _chat_type(chat: Any) -> str:
    return _get(chat, "type") or "private"


def _chat_context(chat: Any) -> str:
    if not chat:
        return ""
    chat_type = _chat_type(chat)
    title = _get(chat, "title")
    username = _get(chat, "username")
    first_name = _get(chat, "first_name")
    last_name = _get(chat, "last_name")
    chat_id = _get(chat, "id")
    person = " ".join(part for part in (first_name, last_name) if part).strip()
    if title:
        label = f'{chat_type} chat "{title}"'
    elif person:
        label = f'private DM with "{person}"'
    elif username:
        label = f"private DM with @{username}"
    else:
        label = f"{chat_type} chat"
    if username and title:
        label += f" (@{username})"
    if chat_id:
        label += f" [chat_id: {chat_id}]"
    return label


def _largest_photo(photos: Any) -> Any:
    if not photos:
        return None
    return photos[-1]


def _media_from_dict(payload: Dict[str, Any]) -> Optional[MediaRef]:
    if payload.get("photo"):
        photo = _largest_photo(payload["photo"])
        return MediaRef("photo", photo["file_id"], "image/jpeg", photo.get("file_size"), "image")
    if payload.get("video"):
        item = payload["video"]
        return MediaRef("video", item["file_id"], item.get("mime_type", "video/mp4"), item.get("file_size"), "video clip")
    if payload.get("animation"):
        item = payload["animation"]
        return MediaRef("animation", item["file_id"], item.get("mime_type", "video/mp4"), item.get("file_size"), "animation/GIF")
    if payload.get("voice"):
        item = payload["voice"]
        return MediaRef("voice", item["file_id"], item.get("mime_type", "audio/ogg"), item.get("file_size"), "voice message")
    if payload.get("audio"):
        item = payload["audio"]
        name = item.get("title") or item.get("file_name")
        desc = f'audio track "{name}"' if name else "audio track"
        return MediaRef("audio", item["file_id"], item.get("mime_type", "audio/mpeg"), item.get("file_size"), desc)
    if payload.get("document"):
        item = payload["document"]
        name = item.get("file_name")
        desc = f'document "{name}"' if name else "document"
        return MediaRef("document", item["file_id"], item.get("mime_type", "application/octet-stream"), item.get("file_size"), desc)
    if payload.get("sticker"):
        item = payload["sticker"]
        mime = "video/webm" if item.get("is_video") else "image/webp"
        desc = "video sticker" if item.get("is_video") else "animated sticker" if item.get("is_animated") else "sticker"
        if item.get("emoji"):
            desc = f"{desc} {item['emoji']}"
        return MediaRef("sticker", item["file_id"], mime, item.get("file_size"), desc)
    if payload.get("video_note"):
        item = payload["video_note"]
        return MediaRef("video_note", item["file_id"], "video/mp4", item.get("file_size"), "video note")
    return None


def _media_from_message(message: Any) -> Optional[MediaRef]:
    if _get(message, "photo"):
        photo = _largest_photo(_get(message, "photo"))
        return MediaRef("photo", photo.file_id, "image/jpeg", _get(photo, "file_size"), "image")
    for key, fallback_mime, desc in (
        ("video", "video/mp4", "video clip"),
        ("animation", "video/mp4", "animation/GIF"),
        ("voice", "audio/ogg", "voice message"),
        ("audio", "audio/mpeg", "audio track"),
        ("document", "application/octet-stream", "document"),
        ("video_note", "video/mp4", "video note"),
    ):
        item = _get(message, key)
        if item:
            name = _get(item, "title") or _get(item, "file_name")
            item_desc = f'{desc} "{name}"' if name else desc
            return MediaRef(key, item.file_id, _get(item, "mime_type") or fallback_mime, _get(item, "file_size"), item_desc)
    sticker = _get(message, "sticker")
    if sticker:
        mime = "video/webm" if _get(sticker, "is_video") else "image/webp"
        desc = "video sticker" if _get(sticker, "is_video") else "animated sticker" if _get(sticker, "is_animated") else "sticker"
        if _get(sticker, "emoji"):
            desc = f"{desc} {_get(sticker, 'emoji')}"
        return MediaRef("sticker", sticker.file_id, mime, _get(sticker, "file_size"), desc)
    return None


def _context_from_payload(payload: Dict[str, Any]) -> Tuple[str, str]:
    content = []
    service = []
    media = _media_from_dict(payload)
    if media:
        content.append(f"{media.description}.")
    if "location" in payload:
        loc = payload["location"]
        content.append(f"map location at lat {loc.get('latitude')}, lon {loc.get('longitude')}.")
    if "venue" in payload:
        venue = payload["venue"]
        title = venue.get("title", "venue")
        address = venue.get("address")
        content.append(f'venue "{title}"' + (f" at {address}." if address else "."))
    if "contact" in payload:
        contact = payload["contact"]
        name = " ".join(part for part in (contact.get("first_name"), contact.get("last_name")) if part)
        content.append(f"contact card for {name or 'someone'}.")
    if "dice" in payload:
        dice = payload["dice"]
        content.append(f"dice result {dice.get('emoji', '🎲')} = {dice.get('value')}.")
    if "poll" in payload:
        poll = payload["poll"]
        opts = ", ".join(opt.get("text", "") for opt in poll.get("options", []))
        content.append(f'poll "{poll.get("question", "")}" with options: {opts}.')
    if "paid_media" in payload:
        content.append("paid media message.")
    if "story" in payload:
        content.append("Telegram story message.")
    if "invoice" in payload:
        invoice = payload["invoice"]
        content.append(f'invoice "{invoice.get("title", "payment")}".')

    service_keys = [
        ("new_chat_members", "new members joined"),
        ("left_chat_member", "a member left"),
        ("new_chat_title", "chat title changed"),
        ("new_chat_photo", "chat photo changed"),
        ("delete_chat_photo", "chat photo removed"),
        ("group_chat_created", "group chat created"),
        ("supergroup_chat_created", "supergroup created"),
        ("channel_chat_created", "channel created"),
        ("message_auto_delete_timer_changed", "auto-delete timer changed"),
        ("migrate_to_chat_id", "chat migrated to supergroup"),
        ("pinned_message", "message pinned"),
        ("forum_topic_created", "forum topic created"),
        ("forum_topic_edited", "forum topic edited"),
        ("forum_topic_closed", "forum topic closed"),
        ("forum_topic_reopened", "forum topic reopened"),
        ("general_forum_topic_hidden", "general forum topic hidden"),
        ("general_forum_topic_unhidden", "general forum topic unhidden"),
        ("giveaway_created", "giveaway created"),
        ("giveaway", "giveaway message"),
        ("giveaway_winners", "giveaway winners announced"),
        ("giveaway_completed", "giveaway completed"),
        ("boost_added", "chat boost added"),
        ("successful_payment", "successful payment notice"),
        ("users_shared", "users shared"),
        ("chat_shared", "chat shared"),
        ("checklist", "checklist/task message"),
    ]
    for key, label in service_keys:
        if key in payload:
            service.append(label)
    return " ".join(content), "; ".join(service)


def _context_from_message(message: Any) -> Tuple[str, str]:
    payload = {}
    for key in DOWNLOADABLE_KEYS + (
        "location",
        "venue",
        "contact",
        "dice",
        "poll",
        "paid_media",
        "story",
        "invoice",
        "new_chat_members",
        "left_chat_member",
        "new_chat_title",
        "new_chat_photo",
        "delete_chat_photo",
        "group_chat_created",
        "supergroup_chat_created",
        "channel_chat_created",
        "message_auto_delete_timer_changed",
        "migrate_to_chat_id",
        "pinned_message",
        "forum_topic_created",
        "forum_topic_edited",
        "forum_topic_closed",
        "forum_topic_reopened",
        "general_forum_topic_hidden",
        "general_forum_topic_unhidden",
        "giveaway_created",
        "giveaway",
        "giveaway_winners",
        "giveaway_completed",
        "boost_added",
        "successful_payment",
        "users_shared",
        "chat_shared",
        "checklist",
    ):
        value = _get(message, key)
        if value:
            payload[key] = _object_to_dict(value)
    if _get(message, "photo"):
        payload["photo"] = [_object_to_dict(photo) for photo in _get(message, "photo")]
    return _context_from_payload(payload)


def _object_to_dict(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_object_to_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_object_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _object_to_dict(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return {
        key: _object_to_dict(item)
        for key, item in getattr(value, "__dict__", {}).items()
        if not key.startswith("_")
    }


def _strip_bot_mention(text: str, bot_username: str) -> str:
    if bot_username:
        return text.replace(f"@{bot_username}", "").strip()
    return text.strip()


def _is_reply_to_bot(reply: Any, bot_username: str) -> bool:
    if not reply:
        return False
    user = _get(reply, "from_user") or _get(reply, "from")
    username = (_get(user, "username") or "").lower()
    return bool(bot_username and username == bot_username.lower())


def _is_summoned(text: str, is_group: bool, reply: Any, bot_username: str) -> bool:
    if not is_group:
        return True
    stripped = text.strip().lower()
    if bot_username and f"@{bot_username.lower()}" in stripped:
        return True
    if stripped.startswith(BOT_SHORT_NAME):
        return True
    return _is_reply_to_bot(reply, bot_username)


def normalize_message(message: Any, bot_username: str = "", source: str = "message") -> IncomingContext:
    chat = _get(message, "chat")
    user = _get(message, "from_user") or _get(message, "from")
    raw_chat_type = _chat_type(chat)
    is_group = raw_chat_type in ("group", "supergroup")
    text = _get(message, "text") or _get(message, "caption") or ""
    reply = _get(message, "reply_to_message")
    content_context, service_context = _context_from_message(message)
    reply_context = ""
    reply_media = None
    if reply:
        reply_text = _get(reply, "text") or _get(reply, "caption") or ""
        reply_content, reply_service = _context_from_message(reply)
        reply_context = reply_text or reply_content or reply_service
        reply_media = _media_from_message(reply)
    media = _media_from_message(message) or reply_media
    return IncomingContext(
        source=source,
        chat_type="group" if is_group else "dm",
        chat_id=_get(chat, "id"),
        user_id=_get(user, "id"),
        sender_name=_full_name(user),
        message_id=_get(message, "message_id"),
        chat_context=_chat_context(chat),
        text=_strip_bot_mention(text, bot_username),
        content_context=content_context,
        service_context=service_context,
        reply_context=reply_context,
        media=media,
        reply_media=reply_media,
        is_group=is_group,
        is_summoned=_is_summoned(text, is_group, reply, bot_username),
    )


def normalize_payload(payload: Dict[str, Any], bot_username: str = "", source: str = "guest") -> IncomingContext:
    chat = payload.get("chat", {})
    user = payload.get("guest_bot_caller_user") or payload.get("from", {})
    raw_chat_type = chat.get("type", "private")
    is_group = raw_chat_type in ("group", "supergroup")
    text = payload.get("text") or payload.get("caption") or ""
    reply = payload.get("reply_to_message")
    content_context, service_context = _context_from_payload(payload)
    reply_context = ""
    reply_media = None
    if reply:
        reply_text = reply.get("text") or reply.get("caption") or ""
        reply_content, reply_service = _context_from_payload(reply)
        reply_context = reply_text or reply_content or reply_service
        reply_media = _media_from_dict(reply)
    media = _media_from_dict(payload) or reply_media
    return IncomingContext(
        source=source,
        chat_type="business" if source == "business" else "guest" if source == "guest" else "group" if is_group else "dm",
        chat_id=chat.get("id") or payload.get("guest_query_id"),
        user_id=user.get("id"),
        sender_name=_full_name(user),
        message_id=payload.get("message_id"),
        business_connection_id=payload.get("business_connection_id"),
        guest_query_id=payload.get("guest_query_id"),
        chat_context=_chat_context(chat),
        text=_strip_bot_mention(text, bot_username),
        content_context=content_context,
        service_context=service_context,
        reply_context=reply_context,
        media=media,
        reply_media=reply_media,
        is_group=is_group,
        is_summoned=True if source == "guest" else _is_summoned(text, is_group, reply, bot_username),
    )
