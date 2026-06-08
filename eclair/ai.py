import logging
from typing import Optional

from .config import GEMINI_MODEL, get_ai_client
from .memory import get_chat_history, get_context_bundle, maybe_extract_memory, record_turn
from .normalizer import IncomingContext
from .persona import get_system_instruction


logger = logging.getLogger(__name__)


async def summarize_media_for_memory(ctx: IncomingContext, media_part: Optional[object]) -> str:
    if not media_part or not ctx.media:
        return ""
    from google.genai import types

    try:
        prompt = (
            "Summarize this Telegram media for private memory only in one short factual sentence. "
            "Describe visible/audible/document content if knowable, including important objects, people, setting, text, or topic. "
            "Do not be chatty. Do not mention uncertainty unless needed. Return only the sentence.\n\n"
            f"Sender: {ctx.sender_name}\n"
            f"Media type: {ctx.media.kind}\n"
            f"Existing message context: {ctx.prompt_text()}"
        )
        response = get_ai_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[media_part, types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction="You write concise factual memory summaries of Telegram media. Return one sentence only."
            ),
        )
        return (response.text or "").strip()
    except Exception:
        logger.exception("Media memory summary failed")
        return ""


async def process_with_gemini(ctx: IncomingContext, media_part: Optional[object] = None, extra_context: str = "") -> str:
    from google.genai import types

    try:
        media_summary = await summarize_media_for_memory(ctx, media_part)
        if media_summary:
            extra_context = "\n".join(part for part in (extra_context, f"Media memory summary: {media_summary}") if part)
        context_bundle = get_context_bundle(ctx)
        prompt = ctx.prompt_text(extra_context)
        prompt_for_model = f"[Long-term context]\n{context_bundle}\n\n{prompt}" if context_bundle else prompt
        if ctx.chat_id:
            record_turn(ctx, "user", prompt)
            contents = get_chat_history(ctx.chat_id)
            contents[-1].parts = [types.Part.from_text(text=prompt_for_model)]
            if media_part:
                contents[-1].parts.insert(0, media_part)
        else:
            parts = []
            if media_part:
                parts.append(media_part)
            parts.append(types.Part.from_text(text=prompt_for_model))
            contents = [types.Content(role="user", parts=parts)]

        response = get_ai_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=get_system_instruction(ctx.effective_chat_type, ctx.user_id)
            ),
        )
        ai_text = response.text or ""
        if ctx.chat_id:
            record_turn(ctx, "model", ai_text)
            await maybe_extract_memory(ctx, ai_text)
        return ai_text
    except Exception:
        logger.exception("Gemini request failed")
        return "oops, error nid noi krub. try again dai pa"
