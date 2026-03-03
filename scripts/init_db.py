#!/usr/bin/env python3
"""Скрипт для инициализации базы данных."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from bot.database import init_db, close_pool


async def main():
    print("Инициализируем базу данных...")
    await init_db()
    await close_pool()
    print("Готово! Таблицы созданы.")


if __name__ == "__main__":
    asyncio.run(main())
