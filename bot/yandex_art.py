"""
Интеграция с YandexART API.
Документация: https://yandex.cloud/ru/docs/foundation-models/image-generation/
"""

import asyncio
import aiohttp
import base64
import logging
from bot.config import config

logger = logging.getLogger(__name__)

API_BASE = "https://llm.api.cloud.yandex.net"
GENERATE_URL = f"{API_BASE}/foundationModels/v1/imageGenerationAsync"
OPERATION_URL = f"{API_BASE}/operations/{{operation_id}}"
MAX_PROMPT_LEN = 500
MAX_TOTAL_TEXT_LEN = 480
ULTRA_STYLE_HINTS = {
    "leader": (
        "Строгий деловой cinematic-портрет спикера на большой сцене. "
        "Реализм кожи и фактур, контрастный сценический свет, LED-фон и глубина пространства. "
        "Сходство лица максимальное, без смены человека."
    ),
    "cyberpunk": (
        "Кибер-панк + космос: яркий неон, sci-fi мегаполис, звездное небо/туманности/планеты на фоне. "
        "Атмосфера будущего, объемный свет, блики и частицы. "
        "Лицо и идентичность строго сохранить."
    ),
    "medieval": (
        "Реалистичный средневековый портрет в каменном замке: факелы, дымка, металл, ткань, глубокие тени. "
        "Кинематографичный исторический кадр без фэнтези-искажений. "
        "Лицо и пол строго сохранить."
    ),
    "cartoon": (
        "Строго 2D мультфильм: clean lineart, bold outlines, выразительный cel-shading, упрощенные формы, "
        "пластичная анимационная мимика, яркая стилизованная палитра. "
        "Именно анимационный кадр/мульт-иллюстрация, не фото и не 3D. "
        "Узнаваемость человека сохранить."
    ),
    "anime": (
        "Строго 2D японское аниме: clean lineart, cel-shading, key visual quality, выразительные аниме-глаза, "
        "стилизованные формы лица и волос, мягкий атмосферный фон. "
        "Именно аниме-иллюстрация/анимационный кадр, не фото и не 3D. "
        "Узнаваемость человека сохранить."
    ),
}

STYLE_NEGATIVE_EXTRAS = {
    "leader": "casual selfie, fashion editorial, fantasy armor, cartoon render, anime render",
    "cyberpunk": "daylight office scene, medieval castle, cozy home interior, flat studio background",
    "medieval": "neon city, cyber implants, spaceships, modern office suit, urban streetwear",
    "cartoon": "photorealistic skin pores, DSLR photo look, 3d CGI, realistic photo lighting, semi-realistic portrait, painterly oil style",
    "anime": "photorealistic skin pores, DSLR photo look, western cartoon style, 3d CGI",
}


def _headers() -> dict:
    return {
        "Authorization": f"Api-Key {config.YANDEX_API_KEY}",
        "x-folder-id": config.YANDEX_FOLDER_ID,
        "Content-Type": "application/json",
    }


def _model_uri() -> str:
    return f"art://{config.YANDEX_FOLDER_ID}/yandex-art/latest"


def _fit_prompt(prompt: str, max_len: int = MAX_PROMPT_LEN) -> str:
    """Ограничивает длину prompt под лимит YandexART."""
    if len(prompt) <= max_len:
        return prompt

    trimmed = prompt[:max_len]
    # Стараемся резать по последней границе предложения/фразы.
    cut_points = [trimmed.rfind("."), trimmed.rfind(","), trimmed.rfind(";"), trimmed.rfind(" ")]
    cut_idx = max(cut_points)
    if cut_idx > int(max_len * 0.6):
        trimmed = trimmed[:cut_idx]
    return trimmed.strip()


def _build_prompts(
    style: dict,
    render_mode: str = "similarity",
    gender_hint: str | None = None,
) -> tuple[str, str]:
    """Собирает промпты с приоритетом максимального сходства лица."""
    gender_lock = ""
    gender_style_hint = ""
    if gender_hint == "male":
        gender_lock = "На фото мужчина; сохрани тот же тип внешности, не меняй человека."
        gender_style_hint = (
            "Сохраняй естественный мужской тип внешности без радикальных изменений. "
            "Растительность на лице должна точно совпадать с исходным фото."
        )
    elif gender_hint == "female":
        gender_lock = "На фото женщина; сохрани тот же тип внешности, не меняй человека."
        gender_style_hint = (
            "Сохраняй естественный женский тип внешности без радикальных изменений. "
            "Растительность на лице должна точно совпадать с исходным фото."
        )

    identity_tail = "Нельзя менять идентичность, нельзя делать другое лицо, без ретуши и искажений."
    if style["id"] in ("anime", "cartoon"):
        identity_tail = (
            "Нельзя менять идентичность и лицо человека; "
            "допустима только художественная стилизация без потери узнаваемости."
        )

    identity_prompt = (
        f"{gender_lock} "
        "КРИТИЧНО: это должен быть тот же самый человек с исходного фото. "
        "Приоритет: 1) идентичность лица, 2) пол и возраст, 3) стиль окружения. "
        "Сохрани лицо человека максимально узнаваемым и идентичным исходному фото: "
        "черты лица, форма глаз, носа, губ, линия челюсти, кожа, возраст и пропорции. "
        "Растительность на лице строго как в исходнике: не добавляй и не убирай бороду/усы/щетину. "
        f"{identity_tail} "
        "Композиция: не крупный план, портрет по пояс или 3/4, лицо занимает примерно 20-30% кадра. "
        "В кадре должно быть много стилизованного окружения и деталей фона. "
        "Same person, same facial geometry, preserve identity."
    )

    identity_prompt = _fit_prompt(identity_prompt, max_len=300)
    style_budget = max(80, MAX_TOTAL_TEXT_LEN - len(identity_prompt) - 1)
    # Для аниме/мультфильма даже в similarity режиме держим более подробный стиль,
    # иначе модель часто скатывается в реализм.
    if render_mode == "fantasy" or style["id"] in ("anime", "cartoon"):
        source_style_prompt = style["prompt"]
    else:
        source_style_prompt = ULTRA_STYLE_HINTS.get(style["id"], style["prompt"])
    source_style_prompt += (
        " Камера средняя дистанция, не close-up; важны художественный фон и контекст сцены."
    )
    if gender_style_hint:
        source_style_prompt += " " + gender_style_hint

    # Используем negative_prompt стиля + общие запреты + style-specific анти-паттерны.
    style_negative = style.get("negative_prompt", "")
    style_extra_negative = STYLE_NEGATIVE_EXTRAS.get(style["id"], "")
    global_negative = (
        "wrong person, wrong facial geometry, face identity drift, "
        "added beard, added moustache, added stubble, removed beard, removed moustache, removed stubble, "
        "extreme close-up, blurred face, deformed face, extra limbs, bad anatomy, low quality, text, watermark"
    )
    combined_negative = ", ".join(
        filter(None, [style_negative, style_extra_negative, global_negative])
    )
    if combined_negative:
        source_style_prompt += f" Исключить: {combined_negative}."
    style_prompt = _fit_prompt(source_style_prompt, max_len=style_budget)
    return identity_prompt, style_prompt


def _build_safe_fallback_prompts(style: dict) -> tuple[str, str]:
    """Ультрабезопасный fallback-профиль на случай модерации."""
    identity_prompt = (
        "Сохрани того же человека и узнаваемое лицо как на исходном фото. "
        "Портрет не крупным планом, с художественным фоном и деталями окружения."
    )
    style_prompt = ULTRA_STYLE_HINTS.get(style["id"], style["description"])
    return _fit_prompt(identity_prompt, max_len=220), _fit_prompt(style_prompt, max_len=220)


async def _image_to_base64(url: str) -> str:
    """Скачивает изображение по URL и конвертирует в base64."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Cannot download source image: {resp.status}")
            data = await resp.read()
    return base64.b64encode(data).decode("utf-8")


async def start_generation(style: dict, photo_url: str) -> str:
    """
    Запускает асинхронную генерацию изображения.
    Возвращает operation_id для дальнейшего опроса.
    """
    logger.info(f"Starting generation for style={style['id']}, photo={photo_url}")

    image_b64 = await _image_to_base64(photo_url)

    identity_prompt, style_prompt = _build_prompts(style)
    if len(style_prompt) < len(style["prompt"]):
        logger.warning(
            "Style prompt was truncated for style=%s from %s to %s chars",
            style["id"],
            len(style["prompt"]),
            len(style_prompt),
        )

    payload = {
        "modelUri": _model_uri(),
        "generationOptions": {
            "seed": "12345",
            "aspectRatio": {
                "widthRatio": "3",
                "heightRatio": "4"
            },
        },
        "messages": [
            {
                "weight": config.YANDEX_IDENTITY_WEIGHT,
                "text": identity_prompt,
            },
            {
                "weight": config.YANDEX_STYLE_WEIGHT,
                "text": style_prompt,
            },
            {
                # Для максимального сходства лица держим референс на максимальном весе.
                "weight": config.YANDEX_REFERENCE_WEIGHT,
                "image": {
                    "data": image_b64,
                    "mimeType": "image/jpeg",
                }
            }
        ],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            GENERATE_URL,
            json=payload,
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status not in (200, 201, 202):
                text = await resp.text()
                raise RuntimeError(f"YandexART start failed [{resp.status}]: {text}")

            data = await resp.json()
            operation_id = data.get("id")
            if not operation_id:
                raise RuntimeError(f"No operation_id in response: {data}")

            logger.info(f"Generation started, operation_id={operation_id}")
            return operation_id


async def start_generation_with_params(
    style: dict,
    photo_url: str,
    seed: str,
    style_weight_override: str | None = None,
    render_mode: str = "similarity",
    gender_hint: str | None = None,
) -> str:
    """Запускает генерацию с переопределением seed и веса стилевого текста."""
    logger.info(
        "Starting generation (custom params) for style=%s seed=%s photo=%s",
        style["id"],
        seed,
        photo_url,
    )
    image_b64 = await _image_to_base64(photo_url)
    identity_prompt, style_prompt = _build_prompts(style, render_mode=render_mode, gender_hint=gender_hint)
    style_weight = style_weight_override or config.YANDEX_STYLE_WEIGHT

    payload = {
        "modelUri": _model_uri(),
        "generationOptions": {
            "seed": seed,
            "aspectRatio": {
                "widthRatio": "3",
                "heightRatio": "4",
            },
        },
        "messages": [
            {
                "weight": config.YANDEX_IDENTITY_WEIGHT,
                "text": identity_prompt,
            },
            {
                "weight": style_weight,
                "text": style_prompt,
            },
            {
                "weight": config.YANDEX_REFERENCE_WEIGHT,
                "image": {
                    "data": image_b64,
                    "mimeType": "image/jpeg",
                },
            },
        ],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            GENERATE_URL,
            json=payload,
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status in (200, 201, 202):
                data = await resp.json()
                operation_id = data.get("id")
                if not operation_id:
                    raise RuntimeError(f"No operation_id in response: {data}")
                logger.info("Generation started, operation_id=%s", operation_id)
                return operation_id

            text = await resp.text()
            # Если сработала модерация, пробуем упрощенный безопасный prompt.
            if resp.status == 400 and "violate the terms of use" in text.lower():
                fallback_identity, fallback_style = _build_safe_fallback_prompts(style)
                fallback_payload = {
                    "modelUri": _model_uri(),
                    "generationOptions": payload["generationOptions"],
                    "messages": [
                        {"weight": config.YANDEX_IDENTITY_WEIGHT, "text": fallback_identity},
                        {"weight": style_weight, "text": fallback_style},
                        payload["messages"][2],
                    ],
                }
                logger.warning("Policy fallback used for style=%s", style["id"])
                async with session.post(
                    GENERATE_URL,
                    json=fallback_payload,
                    headers=_headers(),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as retry_resp:
                    if retry_resp.status not in (200, 201, 202):
                        retry_text = await retry_resp.text()
                        raise RuntimeError(f"YandexART start failed [{retry_resp.status}]: {retry_text}")
                    retry_data = await retry_resp.json()
                    operation_id = retry_data.get("id")
                    if not operation_id:
                        raise RuntimeError(f"No operation_id in response: {retry_data}")
                    logger.info("Generation started after policy fallback, operation_id=%s", operation_id)
                    return operation_id

            raise RuntimeError(f"YandexART start failed [{resp.status}]: {text}")


async def poll_operation(operation_id: str) -> str:
    """
    Ждёт завершения операции и возвращает base64-строку результирующего изображения.
    Выбрасывает TimeoutError или RuntimeError при неудаче.
    """
    url = OPERATION_URL.format(operation_id=operation_id)
    max_attempts = config.MAX_POLL_ATTEMPTS
    interval = config.POLL_INTERVAL_SEC

    async with aiohttp.ClientSession() as session:
        for attempt in range(1, max_attempts + 1):
            async with session.get(
                url,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Poll failed [{resp.status}]: {text}")

                data = await resp.json()
                logger.debug(f"Poll attempt {attempt}/{max_attempts}: done={data.get('done')}")

                if data.get("done"):
                    if "error" in data:
                        err = data["error"]
                        raise RuntimeError(
                            f"Generation error {err.get('code')}: {err.get('message')}"
                        )
                    # Успех: достаём изображение
                    image_b64 = (
                        data.get("response", {}).get("image")
                        or data.get("response", {}).get("imageBase64")
                    )
                    if not image_b64:
                        raise RuntimeError(f"No image in response: {data}")
                    logger.info(f"Generation completed after {attempt} polls")
                    return image_b64

            await asyncio.sleep(interval)

    raise TimeoutError(
        f"Generation timed out after {max_attempts * interval} seconds (operation_id={operation_id})"
    )


async def generate_image(style: dict, photo_url: str) -> bytes:
    """
    Полный цикл: запускает генерацию, ждёт результата.
    Возвращает байты итогового изображения (JPEG/PNG).
    """
    operation_id = await start_generation(style, photo_url)
    image_b64 = await poll_operation(operation_id)
    return base64.b64decode(image_b64)


async def generate_image_with_params(
    style: dict,
    photo_url: str,
    seed: str,
    style_weight_override: str | None = None,
    render_mode: str = "similarity",
    gender_hint: str | None = None,
) -> bytes:
    """Генерация изображения с кастомным seed/весом стиля."""
    operation_id = await start_generation_with_params(
        style=style,
        photo_url=photo_url,
        seed=seed,
        style_weight_override=style_weight_override,
        render_mode=render_mode,
        gender_hint=gender_hint,
    )
    image_b64 = await poll_operation(operation_id)
    return base64.b64decode(image_b64)
