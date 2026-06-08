import os
import tempfile
import unittest
from unittest.mock import patch

from eclair import persona


class PersonaTests(unittest.TestCase):
    def test_uses_public_default_without_private_prompt(self):
        with patch.dict(os.environ, {}, clear=True):
            instruction = persona.get_system_instruction("dm")

        self.assertIn("Telegram-native chat companion", instruction)
        self.assertIn("private 1-on-1", instruction)

    def test_uses_private_prompt_file_override(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as file:
            file.write("private prompt goes here")
            path = file.name

        try:
            with patch.dict(os.environ, {"ECLAIR_SYSTEM_INSTRUCTION_FILE": path}, clear=True):
                instruction = persona.get_system_instruction("dm")
        finally:
            os.unlink(path)

        self.assertIn("private prompt goes here", instruction)


if __name__ == "__main__":
    unittest.main()
