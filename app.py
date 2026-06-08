import asyncio
import logging

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

from eclair.config import ALLOWED_UPDATES, TOKEN, WEBHOOK_URL
from eclair.handlers import (
    handle_business_connection,
    handle_business_message,
    handle_guest_message,
    register_handlers,
)
from eclair.memory import memory_backup_loop, restore_memory_from_backup


logger = logging.getLogger(__name__)
app = FastAPI()
telegram_app = Application.builder().token(TOKEN).updater(None).build()
register_handlers(telegram_app)


@app.on_event("startup")
async def on_startup():
    await telegram_app.initialize()
    await restore_memory_from_backup(telegram_app)
    asyncio.create_task(memory_backup_loop(telegram_app))

    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(
            url=f"https://{WEBHOOK_URL}/webhook",
            allowed_updates=ALLOWED_UPDATES,
        )
        logger.info("Webhook active at https://%s/webhook", WEBHOOK_URL)


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    try:
        data = await request.json()

        if "guest_message" in data:
            return await handle_guest_message(telegram_app, data["guest_message"])

        if "business_connection" in data:
            return await handle_business_connection(data["business_connection"])

        if "business_message" in data:
            return await handle_business_message(telegram_app, data["business_message"])

        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception:
        logger.exception("Webhook execution failed")

    return {"status": "ok"}


@app.get("/")
def health_check():
    return {"status": "online"}
