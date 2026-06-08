# Eclair au Chocobot

<p align="left">
  <img src="assets/eclair-logo.png" alt="Eclair au Chocobot logo" width="180" height="180">
</p>

Eclair au Chocobot is a Telegram bot powered by Gemini. It is built for short, Telegram-native replies, media-aware context, lightweight long-term memory, guest-message support, and an optional secretary mode for Telegram Business messages.

## Features

- Normal Telegram chat replies in private chats and summoned group messages.
- Guest-message handling for Telegram inline/guest contexts.
- Telegram Business message observation for secretary-style context.
- Media support for photos, videos, voice notes, audio, documents, stickers, video notes, locations, polls, contact cards, invoices, and service events.
- Curated memory with schema migration, manual remember/forget commands, and optional Telegram backup-channel sync.
- Owner-only global memory reset with `/whoami` debugging for Telegram user IDs.
- Send-time message splitting so replies stay Telegram-friendly.
- Optional private persona prompts loaded from environment variables or files.

## Public Repo Safety

Do not commit real runtime memory, secrets, or private persona prompts.

- `memory.json` is ignored because it can contain chat history, user facts, Telegram IDs, and private context.
- `.env` files are ignored because they contain tokens and deployment settings.
- Private prompt files should live outside the repo or under `private/`, which is ignored.
- Use `memory.example.json` and `.env.example` as safe public templates.

This public repository is sanitized for distribution. Keep runtime memory, tokens, and private persona prompts outside Git.

## Environment Variables

Copy `.env.example` into your deployment environment and fill in the values there.

| Name | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather. |
| `GEMINI_API_KEY` | Yes | Gemini API key for `google-genai`. |
| `RENDER_EXTERNAL_HOSTNAME` | For webhook deploys | Render hostname used to set `https://<host>/webhook`. |
| `BACKUP_CHANNEL_ID` | No | Telegram channel/chat ID used for memory backup documents. |
| `OWNER_USER_ID` | No | Comma-separated Telegram user IDs allowed to run `/resetallmemory`. |
| `GEMINI_MODEL` | No | Defaults to `gemini-3.1-flash-lite`. |
| `MEMORY_FILE` | No | Defaults to `memory.json`. |
| `MAX_FILE_SIZE` | No | Maximum inspected media size in bytes. Defaults to 20 MB. |
| `ECLAIR_SYSTEM_INSTRUCTION` | No | Private full prompt override for normal mode. |
| `ECLAIR_SYSTEM_INSTRUCTION_FILE` | No | Path to a private normal-mode prompt file. |
| `ECLAIR_SECRETARY_INSTRUCTION` | No | Private full prompt override for secretary mode. |
| `ECLAIR_SECRETARY_INSTRUCTION_FILE` | No | Path to a private secretary-mode prompt file. |

Prompt variables take priority over prompt-file variables. If neither is set, the bot uses the safe public defaults in `eclair/persona.py`.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

Run the app locally:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

For Telegram webhooks, expose the app publicly and configure `RENDER_EXTERNAL_HOSTNAME` so startup can register:

```text
https://<RENDER_EXTERNAL_HOSTNAME>/webhook
```

## Render Deploy

Recommended start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Set the environment variables in Render instead of committing `.env` files.

## Bot Commands

- `/start` shows the welcome message.
- `/friend` switches the caller to friend mode.
- `/secretary` switches the caller to secretary mode.
- `/memory` shows the current durable context bundle.
- `/remember <fact>` manually stores a fact.
- `/forget <keyword>` removes matching memory facts.
- `/resetmemory` resets memory for the current chat.
- `/resetallmemory` resets all memory for configured owners only.
- `/whoami` shows the caller's Telegram ID and owner-match status.

## Tests

```bash
PYTHONPYCACHEPREFIX=/private/tmp/eclair_pycache python3 -m unittest discover -s tests -v
```

The memory tests use temporary files so they do not modify real runtime memory.
