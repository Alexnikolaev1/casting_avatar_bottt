#!/usr/bin/env python3
"""Установка вебхука Telegram. Запуск: python scripts/set_webhook.py"""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

async def main():
    from aiogram import Bot
    from bot.config import config
    bot = Bot(token=config.BOT_TOKEN)
    vercel_url = os.environ.get("VERCEL_URL") or input("URL проекта (например, my-bot.vercel.app): ").strip()
    if not vercel_url.startswith("https://"):
        vercel_url = f"https://{vercel_url}"
    webhook_url = f"{vercel_url}/api/webhook"
    print(f"Устанавливаю вебхук: {webhook_url}")
    await bot.delete_webhook(drop_pending_updates=True)
    result = await bot.set_webhook(url=webhook_url, secret_token=config.WEBHOOK_SECRET,
        allowed_updates=["message", "callback_query"])
    if result:
        info = await bot.get_webhook_info()
        print(f"✅ Готово! URL: {info.url}")
    else:
        print("❌ Ошибка установки вебхука")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
