#!/usr/bin/env python3
"""Тест генерации одного образа (без оплаты, для проверки API)."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from bot.yandex_art import generate_image
from bot.styles import get_style


TEST_PHOTO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/400px-Camponotus_flavomarginatus_ant.jpg"


async def main():
    style_id = sys.argv[1] if len(sys.argv) > 1 else "leader"
    style = get_style(style_id)

    if not style:
        print(f"Неизвестный стиль: {style_id}")
        print(f"Доступные: leader, medieval, cartoon, anime, cyberpunk")
        return

    print(f"Запускаем генерацию для стиля: {style['name']}")
    print(f"Фото: {TEST_PHOTO_URL}")
    print("Ожидайте 20-60 секунд...")

    try:
        image_bytes = await generate_image(style, TEST_PHOTO_URL)
        output_path = f"test_result_{style_id}.jpg"
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        print(f"Успешно! Результат сохранён в {output_path} ({len(image_bytes)} байт)")
    except Exception as e:
        print(f"Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
