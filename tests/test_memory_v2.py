import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from eclair.normalizer import IncomingContext


def ctx(**kwargs):
    defaults = {
        "source": "message",
        "chat_type": "group",
        "chat_id": -100,
        "user_id": 123,
        "sender_name": "Mina",
        "chat_context": 'group chat "Trip"',
        "text": "remember i like ramen",
    }
    defaults.update(kwargs)
    return IncomingContext(**defaults)


class MemoryV2Tests(unittest.TestCase):
    def setUp(self):
        from eclair import memory

        self.memory = memory
        self.original = memory.memory_db
        self.original_memory_file = memory.MEMORY_FILE
        self.original_memory_needs_backup = memory.memory_needs_backup
        self.tmpdir = tempfile.TemporaryDirectory()
        memory.MEMORY_FILE = os.path.join(self.tmpdir.name, "memory.json")
        memory.replace_memory(memory._empty_memory())

    def tearDown(self):
        self.memory.replace_memory(self.original)
        self.memory.MEMORY_FILE = self.original_memory_file
        self.memory.memory_needs_backup = self.original_memory_needs_backup
        self.tmpdir.cleanup()

    def test_migrates_v1_memory(self):
        migrated = self.memory.migrate_memory_if_needed(
            {
                "users": {"123": {"mode": "secretary", "facts": "likes Thai-glish"}},
                "chats": {"-100": [{"role": "user", "text": "old"}]},
            }
        )

        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["users"]["123"]["mode"], "secretary")
        self.assertIn("likes Thai-glish", migrated["users"]["123"]["facts"][0]["text"])
        self.assertEqual(migrated["chats"]["-100"]["recent_messages"][0]["text"], "old")

    def test_record_turn_retains_last_20_and_profiles(self):
        sample = ctx()
        for index in range(25):
            self.memory.record_turn(sample, "user", f"message {index}")

        chat = self.memory.memory_db["chats"]["-100"]
        user = self.memory.memory_db["users"]["123"]

        self.assertEqual(len(chat["recent_messages"]), 20)
        self.assertEqual(chat["recent_messages"][0]["text"], "message 5")
        self.assertEqual(user["name"], "Mina")
        self.assertEqual(chat["participants"]["123"]["display_name"], "Mina")

    def test_manual_remember_forget_and_reset(self):
        sample = ctx()
        self.memory.remember_fact(sample, "Mina likes ramen")
        self.assertIn("Mina likes ramen", self.memory.format_memory_for_context(sample))

        removed = self.memory.forget_keyword(sample, "ramen")
        self.assertGreaterEqual(removed, 1)
        self.assertNotIn("ramen", self.memory.format_memory_for_context(sample).lower())

        self.memory.record_turn(sample, "user", "hello")
        self.memory.reset_chat_memory(sample.chat_id)
        self.assertEqual(self.memory.memory_db["chats"]["-100"]["recent_messages"], [])

    def test_reset_all_memory(self):
        sample = ctx()
        self.memory.remember_fact(sample, "Mina likes ramen")

        self.memory.reset_all_memory()

        self.assertEqual(self.memory.memory_db["schema_version"], 2)
        self.assertEqual(self.memory.memory_db["users"], {})
        self.assertEqual(self.memory.memory_db["chats"], {})

    def test_apply_extracted_memory(self):
        sample = ctx()
        extracted = {
            "user_facts": ["Mina likes ramen"],
            "chat_facts": ["Trip group plans Japan travel"],
            "participant_facts": {"123": ["Mina is the planner"]},
            "summary_update": "The chat is planning Japan travel.",
            "confidence": 0.9,
            "reason": "stable preferences and role",
        }

        changed = self.memory._apply_extracted_memory(sample, extracted, "test")

        self.assertTrue(changed)
        bundle = self.memory.get_context_bundle(sample)
        self.assertIn("Mina likes ramen", bundle)
        self.assertIn("Japan travel", bundle)
        self.assertIn("Mina is the planner", bundle)

    def test_invalid_extraction_json_is_ignored(self):
        self.assertIsNone(self.memory._extract_json("not json"))

    def test_guest_context_is_scoped(self):
        sample = ctx(source="guest", chat_id=55, chat_type="guest", chat_context='private DM with "Pim" [chat_id: 55]')
        self.memory.record_turn(sample, "user", "hi")

        self.assertIn("55", self.memory.memory_db["guest_contexts"])
        self.assertIn("Pim", self.memory.memory_db["guest_contexts"]["55"]["chat_context"])


class MemoryRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from eclair import memory

        self.memory = memory
        self.original = memory.memory_db
        self.original_memory_file = memory.MEMORY_FILE
        self.original_memory_needs_backup = memory.memory_needs_backup
        self.tmpdir = tempfile.TemporaryDirectory()
        memory.MEMORY_FILE = os.path.join(self.tmpdir.name, "memory.json")
        memory.replace_memory(memory._empty_memory())

    async def asyncTearDown(self):
        self.memory.replace_memory(self.original)
        self.memory.MEMORY_FILE = self.original_memory_file
        self.memory.memory_needs_backup = self.original_memory_needs_backup
        self.tmpdir.cleanup()

    async def test_secretary_observed_context_can_extract_without_reply(self):
        from eclair import handlers

        payload = {
            "business_connection_id": "bc-1",
            "from": {"id": 123, "first_name": "Mina"},
            "chat": {"id": 55, "type": "private", "first_name": "Pim"},
            "message_id": 12,
            "text": "remember Pim likes coffee",
        }
        telegram_app = SimpleNamespace(bot=SimpleNamespace(username="eclair_bot"))

        with patch.object(handlers.memory, "maybe_extract_memory", new=AsyncMock()) as extract, patch.object(
            handlers, "process_with_gemini", new=AsyncMock()
        ) as gemini:
            result = await handlers.handle_business_message(telegram_app, payload)

        self.assertEqual(result, {"ok": True})
        extract.assert_awaited_once()
        gemini.assert_not_called()

    async def test_media_summary_is_stored_in_user_turn(self):
        from eclair import ai, memory
        from eclair.normalizer import MediaRef

        sample = ctx(media=MediaRef("photo", "p1", "image/jpeg", 100, "image"))

        with patch.object(ai, "summarize_media_for_memory", new=AsyncMock(return_value="Mina sent an image showing a dog standing on a road.")), patch.object(
            ai, "get_context_bundle", return_value=""
        ), patch.object(ai, "get_ai_client") as client, patch.object(
            ai, "maybe_extract_memory", new=AsyncMock()
        ):
            fake_part = object()

            class FakeTypes:
                class Part:
                    @staticmethod
                    def from_text(text):
                        return SimpleNamespace(text=text)

                class Content:
                    def __init__(self, role, parts):
                        self.role = role
                        self.parts = parts

                class GenerateContentConfig:
                    def __init__(self, system_instruction):
                        self.system_instruction = system_instruction

            with patch.dict("sys.modules", {"google.genai": SimpleNamespace(types=FakeTypes)}):
                client.return_value.models.generate_content.return_value = SimpleNamespace(text="cute")
                await ai.process_with_gemini(sample, fake_part)

        stored = memory.memory_db["chats"]["-100"]["recent_messages"][0]["text"]
        self.assertIn("dog standing on a road", stored)

    async def test_reset_all_memory_owner_only(self):
        from eclair import handlers

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=123))
        context = SimpleNamespace()

        with patch.object(handlers, "is_owner_user", return_value=False), patch.object(handlers.memory, "reset_all_memory") as reset:
            await handlers.reset_all_memory_command(update, context)

        reset.assert_not_called()
        message.reply_text.assert_awaited()

    async def test_reset_all_memory_owner_can_reset(self):
        from eclair import handlers

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message, effective_user=SimpleNamespace(id=123))
        context = SimpleNamespace()

        with patch.object(handlers, "is_owner_user", return_value=True), patch.object(handlers.memory, "reset_all_memory") as reset:
            await handlers.reset_all_memory_command(update, context)

        reset.assert_called_once()
        message.reply_text.assert_awaited()


if __name__ == "__main__":
    unittest.main()
