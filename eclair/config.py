import os


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_HOSTNAME")
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
MEMORY_FILE = os.getenv("MEMORY_FILE", "memory.json")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "20971520"))
BOT_SHORT_NAME = "eclair"
OWNER_USER_ID = os.getenv("OWNER_USER_ID")

ALLOWED_UPDATES = [
    "message",
    "guest_message",
    "business_message",
    "business_connection",
]

ai_client = None


def owner_user_ids():
    raw = os.getenv("OWNER_USER_ID") or OWNER_USER_ID or ""
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_owner_user(user_id):
    return str(user_id).strip() in owner_user_ids()


def get_ai_client():
    global ai_client
    if ai_client is None:
        from google import genai

        ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return ai_client
