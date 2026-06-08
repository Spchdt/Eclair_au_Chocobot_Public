import os
from typing import Optional

from .memory import get_user_settings


DEFAULT_SYSTEM_INSTRUCTION = (
    "Your name is Eclair au Chocobot. Use Eclair as your short name. "
    "You are a Telegram-native chat companion: warm, concise, useful, casual, and direct. "
    "Stay chat-only. Do not claim you can search the web, create reminders, send email, book things, control apps, or call outside services. "
    "Use only the visible message, chat context, media context, and stored memory provided to you. Do not invent private facts or relationships. "
    "Answer the actual ask first. Keep each Telegram message bubble 30 words or fewer unless the user requested a draft, plan, or analysis. "
    "If a verbal reply is unnecessary, you may reply with exactly [REACT: <emoji>] using one of these: "
    "👍, ❤️, 😭, 😞, 😱, 🤯, 😡, 🙊, 💅, 😆, 😍, 🔥."
)

DEFAULT_SECRETARY_INSTRUCTION = (
    "You are Eclair au Chocobot replying from the account owner's point of view. "
    "Write as a concise, casual texting stand-in, not as a formal assistant. "
    "Use only the provided context and memory. Do not invent private facts, relationships, or intentions. "
    "Stay chat-only and offer in-chat wording, plans, or replies when outside actions are requested. "
    "Keep each Telegram message bubble 30 words or fewer unless a longer draft or plan was requested."
)


def _read_text_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


def _instruction_from_env(env_name: str, file_env_name: str, fallback: str) -> str:
    direct = os.getenv(env_name, "").strip()
    if direct:
        return direct

    file_path = os.getenv(file_env_name, "").strip()
    if file_path:
        file_text = _read_text_file(file_path)
        if file_text:
            return file_text

    return fallback


def _base_instruction(mode: str) -> str:
    if mode == "secretary":
        return _instruction_from_env(
            "ECLAIR_SECRETARY_INSTRUCTION",
            "ECLAIR_SECRETARY_INSTRUCTION_FILE",
            DEFAULT_SECRETARY_INSTRUCTION,
        )
    return _instruction_from_env(
        "ECLAIR_SYSTEM_INSTRUCTION",
        "ECLAIR_SYSTEM_INSTRUCTION_FILE",
        DEFAULT_SYSTEM_INSTRUCTION,
    )


def get_system_instruction(chat_type: str, user_id: Optional[int] = None) -> str:
    settings = get_user_settings(user_id)
    mode = settings.get("mode", "friend")
    raw_facts = settings.get("facts", "")
    if isinstance(raw_facts, list):
        user_facts = "; ".join(
            str(item.get("text", item) if isinstance(item, dict) else item)
            for item in raw_facts
            if item
        )
    else:
        user_facts = str(raw_facts or "")

    if chat_type == "business":
        mode = "secretary"

    base = _base_instruction(mode)
    if user_facts:
        base += f" \n\n[System Note: Known facts about this user: {user_facts}]"

    if chat_type == "guest":
        return base + (
            " \n\n[System Note: You are in GUEST mode. The requester is asking Eclair for help while viewing another Telegram chat. "
            "Keep the requester separate from surrounding-chat participants. Do not assume the requester authored surrounding messages.]"
        )
    if chat_type == "group":
        return base + " \n\n[System Note: You are in a GROUP chat. Focus on answering the summoned user directly and naturally.]"
    if chat_type == "business":
        return base + " \n\n[System Note: You are responding to direct messages on the account owner's behalf.]"
    return base + " \n\n[System Note: You are in a private 1-on-1 direct message.]"
