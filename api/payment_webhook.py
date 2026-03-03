"""
Vercel Serverless Function — ЮKassa Payment Webhook Handler.
Обрабатывает уведомления об оплате от ЮKassa.
"""

import json
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import BaseHTTPRequestHandler
from aiogram import Bot
from bot.config import config
from bot.database import (
    get_payment, update_payment_status, update_generation,
    get_generation, add_total_spent, init_db
)
from bot.storage import enqueue_generation_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_db_initialized = False


async def handle_notification(data: dict):
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True

    event_type = data.get("event")
    payment_obj = data.get("object", {})
    payment_id = payment_obj.get("id")

    logger.info(f"Payment notification: event={event_type}, payment_id={payment_id}")

    if event_type == "payment.succeeded":
        await handle_payment_succeeded(payment_id, payment_obj)
    elif event_type == "payment.canceled":
        await handle_payment_canceled(payment_id)
    else:
        logger.info(f"Ignoring event: {event_type}")


async def handle_payment_succeeded(payment_id: str, payment_obj: dict):
    payment = await get_payment(payment_id)
    if not payment:
        logger.error(f"Payment {payment_id} not found in DB")
        return

    if payment["status"] == "succeeded":
        logger.info(f"Payment {payment_id} already processed (idempotent)")
        return

    await update_payment_status(payment_id, "succeeded")
    await add_total_spent(payment["user_id"], payment["amount"])

    bot = Bot(token=config.BOT_TOKEN)
    try:
        await bot.send_message(
            payment["user_id"],
            "✅ <b>Оплата прошла!</b> Начинаю создавать твой образ...\n"
            "Обычно это занимает 20-40 секунд. Ожидай! 🎨",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Cannot notify user {payment['user_id']}: {e}")
    finally:
        await bot.session.close()

    # Ставим в очередь генерации
    for gen_id in payment["generation_ids"]:
        gen = await get_generation(gen_id)
        if not gen:
            logger.error(f"Generation {gen_id} not found")
            continue

        await update_generation(gen_id, "queued")
        await enqueue_generation_task({
            "generation_id": gen_id,
            "user_id": payment["user_id"],
            "style_id": gen["style_id"],
            "photo_url": gen["source_photo_url"],
        })
        logger.info(f"Enqueued generation {gen_id} for user {payment['user_id']}")


async def handle_payment_canceled(payment_id: str):
    payment = await get_payment(payment_id)
    if not payment:
        return
    await update_payment_status(payment_id, "canceled")
    for gen_id in payment["generation_ids"]:
        await update_generation(gen_id, "canceled")
    logger.info(f"Payment {payment_id} canceled")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            return

        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from YuKassa: {e}")
            self.send_response(400)
            self.end_headers()
            return

        try:
            asyncio.run(handle_notification(data))
        except Exception as e:
            logger.exception(f"Error handling payment notification: {e}")

        # Всегда возвращаем 200 — иначе ЮKassa будет слать повторно
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "payment-webhook"}')

    def log_message(self, format, *args):
        pass
