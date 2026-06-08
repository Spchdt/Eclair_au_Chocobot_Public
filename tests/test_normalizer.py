import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from eclair.normalizer import normalize_message, normalize_payload


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


class NormalizerTests(unittest.TestCase):
    def test_standard_text_group_mention_is_summoned(self):
        message = ns(
            chat=ns(id=-100, type="group"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text="@eclair_bot help with this",
            caption=None,
            reply_to_message=None,
        )

        ctx = normalize_message(message, "eclair_bot")

        self.assertTrue(ctx.is_group)
        self.assertTrue(ctx.is_summoned)
        self.assertEqual(ctx.text, "help with this")
        self.assertEqual(ctx.sender_name, "Mina")

    def test_standard_group_without_summon_is_silent(self):
        message = ns(
            chat=ns(id=-100, type="group"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text="random group chatter",
            caption=None,
            reply_to_message=None,
        )

        ctx = normalize_message(message, "eclair_bot")

        self.assertTrue(ctx.is_group)
        self.assertFalse(ctx.is_summoned)

    def test_photo_caption_normalizes_media(self):
        photo = ns(file_id="photo-1", file_size=123)
        message = ns(
            chat=ns(id=1, type="private"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text=None,
            caption="look",
            photo=[photo],
            reply_to_message=None,
        )

        ctx = normalize_message(message, "eclair_bot")

        self.assertEqual(ctx.text, "look")
        self.assertEqual(ctx.media.kind, "photo")
        self.assertEqual(ctx.media.file_id, "photo-1")
        self.assertIn("image", ctx.content_context)

    def test_audio_document_and_sticker_payloads(self):
        audio = normalize_payload(
            {
                "guest_query_id": "g1",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {"id": 2, "type": "private"},
                "audio": {"file_id": "a1", "title": "Song", "mime_type": "audio/mpeg"},
            },
            "eclair_bot",
            "guest",
        )
        doc = normalize_payload(
            {
                "guest_query_id": "g2",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {"id": 2, "type": "private"},
                "document": {"file_id": "d1", "file_name": "notes.pdf"},
            },
            "eclair_bot",
            "guest",
        )
        sticker = normalize_payload(
            {
                "guest_query_id": "g3",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {"id": 2, "type": "private"},
                "sticker": {"file_id": "s1", "emoji": "💅", "is_animated": True},
            },
            "eclair_bot",
            "guest",
        )

        self.assertEqual(audio.media.kind, "audio")
        self.assertIn("Song", audio.content_context)
        self.assertEqual(doc.media.kind, "document")
        self.assertIn("notes.pdf", doc.content_context)
        self.assertEqual(sticker.media.kind, "sticker")
        self.assertIn("💅", sticker.content_context)

    def test_location_venue_contact_dice_poll_payloads(self):
        payload = {
            "guest_query_id": "g1",
            "from": {"id": 1, "first_name": "Mina"},
            "chat": {"id": 2, "type": "private"},
            "location": {"latitude": 13.7, "longitude": 100.5},
            "venue": {"title": "Cafe", "address": "Bangkok"},
            "contact": {"first_name": "Art"},
            "dice": {"emoji": "🎲", "value": 6},
            "poll": {"question": "Dinner", "options": [{"text": "ramen"}, {"text": "sushi"}]},
        }

        ctx = normalize_payload(payload, "eclair_bot", "guest")

        self.assertIn("lat 13.7", ctx.content_context)
        self.assertIn("Cafe", ctx.content_context)
        self.assertIn("contact card", ctx.content_context)
        self.assertIn("= 6", ctx.content_context)
        self.assertIn("Dinner", ctx.content_context)

    def test_reply_context_and_reply_media(self):
        payload = {
            "guest_query_id": "g1",
            "from": {"id": 1, "first_name": "Mina"},
            "chat": {"id": 2, "type": "private"},
            "text": "what is this",
            "reply_to_message": {
                "photo": [{"file_id": "p1", "file_size": 100}],
                "caption": "old image",
            },
        }

        ctx = normalize_payload(payload, "eclair_bot", "guest")

        self.assertEqual(ctx.reply_context, "old image")
        self.assertEqual(ctx.media.file_id, "p1")

    def test_standard_reply_to_media_uses_reply_media(self):
        reply = ns(
            text=None,
            caption="old image",
            photo=[ns(file_id="p1", file_size=100)],
        )
        message = ns(
            chat=ns(id=1, type="private"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text="what is this",
            caption=None,
            reply_to_message=reply,
        )

        ctx = normalize_message(message, "eclair_bot")

        self.assertEqual(ctx.reply_context, "old image")
        self.assertEqual(ctx.media.file_id, "p1")

    def test_service_payloads_become_event_context(self):
        ctx = normalize_payload(
            {
                "guest_query_id": "g1",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {"id": 2, "type": "private"},
                "pinned_message": {"text": "important"},
                "forum_topic_created": {"name": "Plans"},
                "checklist": {"title": "Tasks"},
            },
            "eclair_bot",
            "guest",
        )

        self.assertIn("message pinned", ctx.service_context)
        self.assertIn("forum topic created", ctx.service_context)
        self.assertIn("checklist", ctx.service_context)

    def test_guest_payload_includes_surrounding_chat_context(self):
        ctx = normalize_payload(
            {
                "guest_query_id": "g1",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {
                    "id": 99,
                    "type": "private",
                    "first_name": "Pim",
                    "username": "pimmy",
                },
                "text": "what should i say",
            },
            "eclair_bot",
            "guest",
        )

        self.assertIn("private DM with", ctx.chat_context)
        self.assertIn("Pim", ctx.chat_context)
        self.assertFalse(ctx.is_group)
        self.assertIn("[Guest request from Mina]", ctx.prompt_text())
        self.assertIn("[Surrounding Telegram chat: private DM with \"Pim\"", ctx.prompt_text())
        self.assertIn("[Mina's request to Eclair]: what should i say", ctx.prompt_text())
        self.assertIn("do not assume they authored messages from the surrounding chat", ctx.prompt_text())
        self.assertIn("Names and chat titles are labels only", ctx.prompt_text())

    def test_guest_group_context_keeps_requester_separate_from_group(self):
        ctx = normalize_payload(
            {
                "guest_query_id": "g1",
                "from": {"id": 1, "first_name": "Mina"},
                "chat": {
                    "id": -100,
                    "type": "supergroup",
                    "title": "Trip Plans",
                    "username": "tripplans",
                },
                "text": "what should i say here",
                "reply_to_message": {"text": "we need to book today"},
            },
            "eclair_bot",
            "guest",
        )

        prompt = ctx.prompt_text()

        self.assertTrue(ctx.is_group)
        self.assertIn("[Guest request from Mina]", prompt)
        self.assertIn('Surrounding Telegram chat: supergroup chat "Trip Plans"', prompt)
        self.assertIn('[Message being referenced in that chat: "we need to book today"]', prompt)
        self.assertIn("[Mina's request to Eclair]: what should i say here", prompt)
        self.assertIn("do not infer relationships, personalities, history, or intentions", prompt)

    def test_guest_payload_prefers_guest_caller_user(self):
        ctx = normalize_payload(
            {
                "guest_query_id": "g1",
                "from": {"id": 2, "first_name": "Original"},
                "guest_bot_caller_user": {"id": 1, "first_name": "Mina"},
                "chat": {"id": -100, "type": "supergroup", "title": "Trip Plans"},
                "text": "@eclair_bot what should i say",
            },
            "eclair_bot",
            "guest",
        )

        self.assertEqual(ctx.user_id, 1)
        self.assertEqual(ctx.sender_name, "Mina")
        self.assertIn("[Guest request from Mina]", ctx.prompt_text())


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_unsummoned_does_not_call_gemini(self):
        from eclair import handlers

        message = ns(
            chat=ns(id=-100, type="group"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text="random",
            caption=None,
            reply_to_message=None,
        )
        update = ns(effective_message=message)
        context = ns(bot=ns(username="eclair_bot"))

        with patch.object(handlers, "process_with_gemini", new=AsyncMock()) as mocked:
            await handlers.handle_standard_message(update, context)

        mocked.assert_not_called()

    async def test_group_mention_calls_gemini(self):
        from eclair import handlers

        message = ns(
            chat=ns(id=-100, type="group"),
            from_user=ns(id=1, first_name="Mina", last_name=None, username="mina"),
            message_id=10,
            text="@eclair_bot hi",
            caption=None,
            reply_to_message=None,
            reply_text=AsyncMock(),
        )
        update = ns(effective_message=message)
        context = ns(bot=ns(username="eclair_bot"))

        with patch.object(handlers, "build_media_part", new=AsyncMock(return_value=(None, ""))), patch.object(
            handlers, "set_typing", new=AsyncMock()
        ), patch.object(handlers, "process_with_gemini", new=AsyncMock(return_value="hi")), patch.object(
            handlers, "process_ai_reply", new=AsyncMock(return_value="hi")
        ):
            await handlers.handle_standard_message(update, context)

        message.reply_text.assert_awaited()

    async def test_guest_message_answers_guest_query_without_typing_action(self):
        from eclair import handlers

        payload = {
            "guest_query_id": "guest-1",
            "from": {"id": 1, "first_name": "Mina"},
            "chat": {"id": -100, "type": "supergroup", "title": "Trip Plans"},
            "text": "hi",
        }
        telegram_app = ns(bot=ns(username="eclair_bot"))

        with patch.object(handlers, "build_media_part", new=AsyncMock(return_value=(None, ""))), patch.object(
            handlers, "set_typing", new=AsyncMock()
        ) as typing, patch.object(handlers, "process_with_gemini", new=AsyncMock(return_value="[REACT: 💅]")), patch.object(
            handlers, "answer_guest_query", new=AsyncMock()
        ) as answer:
            await handlers.handle_guest_message(telegram_app, payload)

        typing.assert_not_awaited()
        answer.assert_awaited_once()

    async def test_business_message_observes_without_replying(self):
        from eclair import handlers

        payload = {
            "business_connection_id": "bc-1",
            "from": {"id": 1, "first_name": "Mina"},
            "chat": {"id": 2, "type": "private", "first_name": "Pim"},
            "message_id": 12,
            "text": "see you tomorrow",
        }
        telegram_app = ns(bot=ns(username="eclair_bot"))

        with patch.object(handlers.memory, "record_turn") as record, patch.object(
            handlers.memory, "maybe_extract_memory", new=AsyncMock()
        ), patch.object(
            handlers, "process_with_gemini", new=AsyncMock()
        ) as gemini:
            result = await handlers.handle_business_message(telegram_app, payload)

        self.assertEqual(result, {"ok": True})
        record.assert_called_once()
        gemini.assert_not_called()

    async def test_too_large_media_falls_back_to_metadata(self):
        from eclair.normalizer import IncomingContext, MediaRef
        from eclair.telegram_io import build_media_part

        ctx = IncomingContext(
            source="message",
            chat_type="dm",
            media=MediaRef("document", "d1", "application/pdf", 999999999, "huge document"),
        )
        bot = ns(get_file=AsyncMock())

        media_part, file_context = await build_media_part(bot, ctx)

        self.assertIsNone(media_part)
        self.assertIn("too large", file_context)
        bot.get_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
