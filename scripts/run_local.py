#!/usr/bin/env python3
"""
Запуск бота локально через long-polling (для разработки).
НЕ использовать в продакшене!
"""

import asyncio
import contextlib
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import config
from bot.database import init_db, close_pool
from bot.app import router
from bot.worker import run_worker


async def _local_worker_loop():
    """Локальный воркер: обрабатывает очередь генераций в фоне."""
    while True:
        try:
            await run_worker(max_tasks=3)
        except Exception:
            logging.getLogger(__name__).exception("Local worker loop error")
        await asyncio.sleep(2)


async def main():
    print("Запуск бота в режиме long-polling (только для разработки)...")
    await init_db()
    print("База данных инициализирована")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    worker_task = asyncio.create_task(_local_worker_loop())

    print(f"Бот запущен! Нажми Ctrl+C для остановки.")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        await bot.session.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
