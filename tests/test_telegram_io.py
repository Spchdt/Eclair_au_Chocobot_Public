import unittest

from eclair.telegram_io import split_chat_bubbles, split_word_bubbles


class TelegramIOTests(unittest.TestCase):
    def test_split_chat_bubbles_keeps_short_reply_single(self):
        self.assertEqual(split_chat_bubbles("ok bro"), ["ok bro"])

    def test_split_chat_bubbles_breaks_long_sections(self):
        text = "first bit\n\n" + ("long " * 180) + "\n\nlast bit"

        bubbles = split_chat_bubbles(text, limit=120)

        self.assertGreater(len(bubbles), 2)
        self.assertTrue(all(len(bubble) <= 120 for bubble in bubbles))
        self.assertEqual(bubbles[0], "first bit")
        self.assertEqual(bubbles[-1], "last bit")

    def test_split_word_bubbles_limits_to_30_words(self):
        text = " ".join(f"word{i}" for i in range(45))

        bubbles = split_word_bubbles(text)

        self.assertEqual(len(bubbles), 2)
        self.assertTrue(all(len(bubble.split()) <= 30 for bubble in bubbles))


if __name__ == "__main__":
    unittest.main()
