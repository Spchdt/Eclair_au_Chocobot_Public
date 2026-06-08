import logging

from . import memory
from .ai import process_with_gemini
from .config import is_owner_user, owner_user_ids
from .normalizer import IncomingContext, normalize_message, normalize_payload
from .telegram_io import (
    answer_guest_query,
    build_media_part,
    process_ai_reply,
    safe_reply,
    set_typing,
)


logger = logging.getLogger(__name__)


def _bot_username(bot) -> str:
    return getattr(bot, "username", None) or ""


async def start_command(update, context) -> None:
    welcome_message = (
        "👋 *Sawasdee krub!*\n\n"
        "I'm *Éclair au Chocobot* — Eclair for short, your Telegram-native AI friend laew.\n"
        "Tag me, reply to me, or start with `eclair` in groups. Send pics, voice notes, docs, stickers, locations, polls, all that chaos.\n\n"
        "Mode commands: /secretary | /friend"
    )
    await safe_reply(update.effective_message, welcome_message)


async def set_secretary_mode(update, context) -> None:
    memory.set_user_mode(update.effective_user.id, "secretary")
    await safe_reply(update.effective_message, "secretary mode activated. i'll answer as your sassy stand-in.")


async def set_friend_mode(update, context) -> None:
    memory.set_user_mode(update.effective_user.id, "friend")
    await safe_reply(update.effective_message, "friend mode activated. sassy time laew.")


async def show_memory_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    ctx = normalize_message(message, _bot_username(context.bot), "message")
    await safe_reply(message, memory.format_memory_for_context(ctx))


async def remember_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    fact = " ".join(getattr(context, "args", []) or []).strip()
    if not fact:
        await safe_reply(message, "tell me what to remember, bro. `/remember <fact>`")
        return
    ctx = normalize_message(message, _bot_username(context.bot), "message")
    memory.remember_fact(ctx, fact)
    await safe_reply(message, "remembered. finally, something worth storing.")


async def forget_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    keyword = " ".join(getattr(context, "args", []) or []).strip()
    if not keyword:
        await safe_reply(message, "give me a keyword to forget, be so serious.")
        return
    ctx = normalize_message(message, _bot_username(context.bot), "message")
    removed = memory.forget_keyword(ctx, keyword)
    await safe_reply(message, f"forgot {removed} matching memory item(s).")


async def reset_memory_command(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    ctx = normalize_message(message, _bot_username(context.bot), "message")
    memory.reset_chat_memory(ctx.chat_id)
    await safe_reply(message, "reset this chat memory. clean slate laew.")


async def reset_all_memory_command(update, context) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    if not is_owner_user(user.id):
        await safe_reply(message, "nope. owner-only brain wipe, obviously.")
        return
    memory.reset_all_memory()
    await safe_reply(message, "all memory reset. eclair is now suspiciously fresh.")


async def whoami_command(update, context) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    status = "yes" if is_owner_user(user.id) else "no"
    configured = "yes" if owner_user_ids() else "no"
    await safe_reply(message, f"your telegram id is `{user.id}`. owner match: {status}. owner env set: {configured}.")


async def _reply_for_context(bot, ctx: IncomingContext) -> str:
    media_part, file_context = await build_media_part(bot, ctx)
    if ctx.chat_id and ctx.effective_chat_type != "guest":
        await set_typing(ctx.chat_id, ctx.business_connection_id)
    ai_reply = await process_with_gemini(ctx, media_part, file_context)
    return await process_ai_reply(ai_reply, ctx)


async def handle_standard_message(update, context) -> None:
    message = update.effective_message
    if not message:
        return
    ctx = normalize_message(message, _bot_username(context.bot), "message")
    if ctx.is_group and not ctx.is_summoned:
        return
    reply = await _reply_for_context(context.bot, ctx)
    if reply:
        await safe_reply(message, reply)


async def handle_guest_message(telegram_app, payload: dict) -> dict:
    ctx = normalize_payload(payload, _bot_username(telegram_app.bot), "guest")
    if not ctx.guest_query_id:
        return {"ok": True}
    reply = await _reply_for_context(telegram_app.bot, ctx)
    await answer_guest_query(ctx.guest_query_id, reply or "✨")
    return {"status": "guest_replied_natively"}


async def handle_business_connection(payload: dict) -> dict:
    conn_id = payload.get("id")
    can_reply = payload.get("can_reply", False)
    logger.info("Business connection received: id=%s can_reply=%s", conn_id, can_reply)
    return {"ok": True}


async def handle_business_message(telegram_app, payload: dict) -> dict:
    ctx = normalize_payload(payload, _bot_username(telegram_app.bot), "business")
    if not ctx.chat_id:
        return {"ok": True}
    memory.record_turn(ctx, "user", f"[Observed secretary context]\n{ctx.prompt_text()}", passive=True)
    await memory.maybe_extract_memory(ctx, passive=True)
    return {"ok": True}


def register_handlers(telegram_app) -> None:
    from telegram.ext import CommandHandler, MessageHandler, filters

    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("secretary", set_secretary_mode))
    telegram_app.add_handler(CommandHandler("friend", set_friend_mode))
    telegram_app.add_handler(CommandHandler("memory", show_memory_command))
    telegram_app.add_handler(CommandHandler("remember", remember_command))
    telegram_app.add_handler(CommandHandler("forget", forget_command))
    telegram_app.add_handler(CommandHandler("resetmemory", reset_memory_command))
    telegram_app.add_handler(CommandHandler("resetallmemory", reset_all_memory_command))
    telegram_app.add_handler(CommandHandler("whoami", whoami_command))
    telegram_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_standard_message))
