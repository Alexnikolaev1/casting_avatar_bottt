"""
Воркер для обработки очереди генераций.
Вызывается через Vercel Cron каждую минуту.
"""

import logging
import secrets
from aiogram import Bot
from aiogram.types import BufferedInputFile

from bot.config import config
from bot.database import (
    update_generation, get_user, init_db, add_free_generation
)
from bot.storage import dequeue_generation_task, upload_bytes_to_blob, download_from_url
from bot.yandex_art import generate_image_with_params
from bot.styles import get_style
from bot.keyboards import share_keyboard
from bot.face_blend import blend_face

logger = logging.getLogger(__name__)
_db_initialized = False


def _make_variant_seeds() -> tuple[str, str, str]:
    """Генерирует разные seed для каждого запуска задачи."""
    max_seed = 2_147_483_647
    s1 = secrets.randbelow(max_seed - 1) + 1
    s2 = ((s1 + 104_729) % max_seed) or 1
    s3 = ((s1 + 1_299_709) % max_seed) or 1
    return str(s1), str(s2), str(s3)


def _mode_profile(
    render_mode: str,
    gender_hint: str | None = None,
    style_id: str | None = None,
) -> dict:
    if render_mode in ("fantasy", "style"):
        base = {
            "w1": 0.30,
            "w2": 0.22,
            "w3": 0.14,
            "blend": float(config.FACE_BLEND_FANTASY_STRENGTH),
            "core_blend": float(config.FACE_BLEND_FANTASY_CORE_STRENGTH),
        }
    else:
        base = {
            "w1": float(config.YANDEX_STYLE_WEIGHT),
            "w2": float(config.YANDEX_SECOND_VARIANT_STYLE_WEIGHT),
            "w3": float(config.YANDEX_THIRD_VARIANT_STYLE_WEIGHT),
            "blend": float(config.FACE_BLEND_SIMILARITY_STRENGTH),
            "core_blend": float(config.FACE_BLEND_SIMILARITY_CORE_STRENGTH),
        }

    # Для мультфильма/аниме усиливаем стилизацию, иначе режим выглядит слишком реалистично.
    if style_id in ("cartoon", "anime"):
        if render_mode in ("fantasy", "style"):
            base["w1"] = max(base["w1"], 0.60)
            base["w2"] = max(base["w2"], 0.48)
            base["w3"] = max(base["w3"], 0.36)
            base["blend"] = min(base["blend"], 0.42)
            base["core_blend"] = min(base["core_blend"], 0.82)
        else:
            base["w1"] = max(base["w1"], 0.42)
            base["w2"] = max(base["w2"], 0.34)
            base["w3"] = max(base["w3"], 0.26)
            base["blend"] = min(base["blend"], 0.50)
            base["core_blend"] = min(base["core_blend"], 0.88)

    # Аниме особенно чувствителен к face blend: делаем мягче,
    # чтобы не возвращать генерацию к фотореализму.
    if style_id == "anime":
        if render_mode in ("fantasy", "style"):
            base["w1"] = max(base["w1"], 0.66)
            base["w2"] = max(base["w2"], 0.54)
            base["w3"] = max(base["w3"], 0.42)
            base["blend"] = min(base["blend"], 0.30)
            base["core_blend"] = min(base["core_blend"], 0.72)
        else:
            base["w1"] = max(base["w1"], 0.50)
            base["w2"] = max(base["w2"], 0.40)
            base["w3"] = max(base["w3"], 0.30)
            base["blend"] = min(base["blend"], 0.34)
            base["core_blend"] = min(base["core_blend"], 0.76)

    # Для мультфильма тоже усиливаем 2D-стилизацию, чтобы не получался "почти реализм".
    if style_id == "cartoon":
        if render_mode in ("fantasy", "style"):
            base["w1"] = max(base["w1"], 0.64)
            base["w2"] = max(base["w2"], 0.52)
            base["w3"] = max(base["w3"], 0.40)
            base["blend"] = min(base["blend"], 0.32)
            base["core_blend"] = min(base["core_blend"], 0.74)
        else:
            base["w1"] = max(base["w1"], 0.48)
            base["w2"] = max(base["w2"], 0.38)
            base["w3"] = max(base["w3"], 0.28)
            base["blend"] = min(base["blend"], 0.36)
            base["core_blend"] = min(base["core_blend"], 0.78)

    # Если пользователь явно выбрал пол, ужесточаем параметры сходства.
    if gender_hint in ("male", "female"):
        penalty = 0.03 if style_id in ("cartoon", "anime") else 0.08
        base["w1"] = max(0.06, base["w1"] - penalty)
        base["w2"] = max(0.04, base["w2"] - penalty)
        base["w3"] = max(0.03, base["w3"] - max(0.02, penalty - 0.01))
        base["blend"] = min(0.80, base["blend"] + 0.08)
        base["core_blend"] = min(1.00, base["core_blend"] + 0.04)

    return {
        "w1": f"{base['w1']:.2f}",
        "w2": f"{base['w2']:.2f}",
        "w3": f"{base['w3']:.2f}",
        "blend": base["blend"],
        "core_blend": base["core_blend"],
    }


async def run_worker(max_tasks: int = 3):
    """Основной цикл воркера. Обрабатывает до max_tasks задач за один запуск."""
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True
    bot = Bot(token=config.BOT_TOKEN)

    processed = 0
    try:
        for _ in range(max_tasks):
            task = await dequeue_generation_task()
            if not task:
                logger.info("Queue is empty, worker done")
                break

            logger.info(f"Processing task: {task}")
            await process_task(task, bot)
            processed += 1

    finally:
        await bot.session.close()

    logger.info(f"Worker finished, processed {processed} tasks")
    return processed


async def process_task(task: dict, bot: Bot):
    """Обрабатывает одну задачу генерации."""
    generation_id = task["generation_id"]
    user_id = task["user_id"]
    style_id = task["style_id"]
    photo_url = task["photo_url"]
    render_mode = task.get("render_mode", "similarity")
    gender_hint = task.get("gender_hint")
    mode_profile = _mode_profile(render_mode, gender_hint=gender_hint, style_id=style_id)

    style = get_style(style_id)
    if not style:
        logger.error(f"Unknown style: {style_id}")
        await update_generation(generation_id, "failed", error_message="Unknown style")
        return

    try:
        # Помечаем как "в обработке"
        await update_generation(generation_id, "processing")
        seed_1, seed_2, seed_3 = _make_variant_seeds()

        await bot.send_message(
            user_id,
            f"🎨 Начинаю создавать твой образ <b>{style['emoji']} {style['name']}</b>...\n"
            f"Обычно это занимает 20–40 секунд. Скоро пришлю! ✨",
            parse_mode="HTML",
        )

        # Генерируем 1 или 2 варианта (второй с более мягкой стилизацией для лучшего сходства)
        variants: list[bytes] = []
        first_error: Exception | None = None
        try:
            image_bytes = await generate_image_with_params(
                style=style,
                photo_url=photo_url,
                seed=seed_1,
                style_weight_override=mode_profile["w1"],
                render_mode=render_mode,
                gender_hint=gender_hint,
            )
            variants.append(image_bytes)
        except Exception as error:
            first_error = error

        if config.YANDEX_MULTI_VARIANT:
            try:
                second_variant = await generate_image_with_params(
                    style=style,
                    photo_url=photo_url,
                    seed=seed_2,
                    style_weight_override=mode_profile["w2"],
                    render_mode=render_mode,
                    gender_hint=gender_hint,
                )
                variants.append(second_variant)
            except Exception as error:
                logger.warning("Second variant generation failed: %s", error)

        if config.YANDEX_THIRD_VARIANT:
            try:
                third_variant = await generate_image_with_params(
                    style=style,
                    photo_url=photo_url,
                    seed=seed_3,
                    style_weight_override=mode_profile["w3"],
                    render_mode=render_mode,
                    gender_hint=gender_hint,
                )
                variants.append(third_variant)
            except Exception as error:
                logger.warning("Third variant generation failed: %s", error)

        if not variants:
            if first_error:
                raise first_error
            raise RuntimeError("All generation variants failed")

        if config.FACE_BLEND_ENABLED:
            try:
                source_bytes = await download_from_url(photo_url)
                variants = [
                    blend_face(
                        source_bytes,
                        variant,
                        strength=mode_profile["blend"],
                        core_strength=mode_profile["core_blend"],
                    )
                    for variant in variants
                ]
            except Exception as error:
                logger.warning("Face blend stage failed, using raw variants: %s", error)

        image_bytes = variants[0]

        # Загружаем в Blob (если не настроен локально — продолжаем без сохранения URL)
        result_url = None
        try:
            result_url = await upload_bytes_to_blob(
                image_bytes,
                f"results/{user_id}_{generation_id}.jpg",
            )
        except Exception as error:
            logger.warning(
                "Blob upload failed for result image, continuing without result URL: %s",
                error,
            )

        # Обновляем запись
        await update_generation(generation_id, "completed", result_url=result_url)

        # Получаем пользователя для реферального кода
        user = await get_user(user_id)
        ref_code = user["referral_code"] if user else "ref"

        # Отправляем результат
        photo_file = BufferedInputFile(image_bytes, filename=f"portrait_{style_id}.jpg")
        await bot.send_photo(
            user_id,
            photo=photo_file,
            caption=(
                f"✅ <b>Твой образ готов (вариант 1)!</b>\n\n"
                f"{style['emoji']} <b>{style['name']}</b>\n\n"
                f"Поделись с другом — вы получите бонусные генерации! 🎁"
            ),
            parse_mode="HTML",
        )

        if len(variants) > 1:
            alt_file = BufferedInputFile(variants[1], filename=f"portrait_{style_id}_alt.jpg")
            await bot.send_photo(
                user_id,
                photo=alt_file,
                caption=(
                    f"🧪 <b>Вариант 2 (максимум сходства)</b>\n"
                    f"Сделал ещё более мягкую стилизацию — выбери, что нравится больше."
                ),
                parse_mode="HTML",
            )

        if len(variants) > 2:
            alt_file_2 = BufferedInputFile(variants[2], filename=f"portrait_{style_id}_ultra.jpg")
            await bot.send_photo(
                user_id,
                photo=alt_file_2,
                caption=(
                    f"🔒 <b>Вариант 3 (ультра-сходство)</b>\n"
                    f"Минимум стилизации, максимум сохранения лица."
                ),
                parse_mode="HTML",
            )

        kb = share_keyboard(config.BOT_USERNAME, ref_code)
        await bot.send_message(user_id, "Что дальше?", reply_markup=kb)

        logger.info(f"Generation {generation_id} completed for user {user_id}")

    except TimeoutError:
        await update_generation(generation_id, "failed", error_message="Timeout")
        await add_free_generation(user_id, 1)
        await bot.send_message(
            user_id,
            "⏰ Генерация заняла слишком долго. Что-то пошло не так на стороне нейросети.\n"
            "Я уже вернул 1 генерацию на твой баланс — попробуй снова."
        )
        logger.warning(f"Generation {generation_id} timed out")

    except Exception as e:
        error_msg = str(e)
        await update_generation(generation_id, "failed", error_message=error_msg[:500])
        await add_free_generation(user_id, 1)
        await bot.send_message(
            user_id,
            "😔 При создании образа произошла ошибка. Уже разбираемся!\n"
            "Я уже вернул 1 генерацию на твой баланс — можно запускать снова."
        )
        logger.exception(f"Generation {generation_id} failed: {e}")
