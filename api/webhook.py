"""
Vercel Serverless Function — Telegram Webhook Handler.
Точка входа для всех сообщений от Telegram.
"""

import json
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import BaseHTTPRequestHandler
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from bot.config import config
from bot.database import init_db
from bot.app import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)
_db_initialized = False


async def process_update(update_dict: dict):
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True
    update = Update.model_validate(update_dict)
    await dp.feed_update(bot=bot, update=update)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        secret_token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret_token != config.WEBHOOK_SECRET:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            return
        body = self.rfile.read(content_length)
        try:
            update_dict = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            self.send_response(400)
            self.end_headers()
            return
        try:
            asyncio.run(process_update(update_dict))
        except Exception as e:
            logger.exception(f"Error processing update: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "telegram-webhook"}')

    def log_message(self, format, *args):
        pass
