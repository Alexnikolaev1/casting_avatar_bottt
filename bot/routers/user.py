"""Пользовательские команды и callback'и."""

import asyncio
import logging
import uuid

import aiohttp
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.database import (
    add_free_generation,
    add_total_spent,
    create_generation,
    create_payment as db_create_payment,
    get_generation,
    get_or_create_user,
    get_payment,
    get_pool,
    get_user,
    get_user_by_ref_code,
    get_user_generations,
    set_referred_by,
    update_payment_status,
    update_generation,
    use_free_generation,
)
from bot.keyboards import payment_keyboard, styles_keyboard
from bot.states import UserFlow
from bot.storage import enqueue_generation_task, upload_bytes_to_blob
from bot.styles import PACK_STYLE_IDS, STYLES, get_style
from bot.texts import (
    ERROR_GENERIC,
    HELP_TEXT,
    MY_GENERATIONS_EMPTY,
    NEED_PHOTO_FIRST,
    PACK_SELECTED,
    PHOTO_RECEIVED,
    PHOTO_TOO_SMALL,
    REFERRAL_INFO,
    STYLE_PICKER_TITLE,
    STYLE_SELECTED,
    WELCOME,
    WELCOME_REF,
)
from bot.ui import format_generations_text
from bot.yukassa import create_payment as yukassa_create_payment, get_payment_info

logger = logging.getLogger(__name__)
router = Router(name=__name__)

RENDER_MODE_MAP = {
    "fantasy": "🎭 Больше фантазии",
    "similarity": "🧠 Больше сходства",
}
GENDER_MAP = {
    "male": "👨 Мужчина",
    "female": "👩 Женщина",
}


async def _safe_edit_text(callback: CallbackQuery, text: str):
    try:
        await callback.message.edit_text(text)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error):
            await callback.answer("Этот шаг уже обработан, выбери другой стиль или отправь новое фото.")
            return
        raise


def _styles_text(render_mode: str, gender_hint: str | None) -> str:
    mode_label = RENDER_MODE_MAP.get(render_mode, RENDER_MODE_MAP["similarity"])
    gender_label = GENDER_MAP.get(gender_hint, "не выбран")
    return (
        f"{STYLE_PICKER_TITLE}\n\n"
        f"Режим: <b>{mode_label}</b>\n"
        f"Пол: <b>{gender_label}</b>\n\n"
        f"Сначала выбери режим и пол, потом стиль."
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    args = (message.text or "").split(maxsplit=1)
    ref_code = args[1].strip() if len(args) > 1 else None
    is_ref = False

    if ref_code and ref_code != user.get("referral_code"):
        referrer = await get_user_by_ref_code(ref_code)
        if referrer and referrer["telegram_id"] != message.from_user.id:
            await set_referred_by(message.from_user.id, referrer["telegram_id"])
            await add_free_generation(referrer["telegram_id"], 1)
            try:
                await bot.send_message(
                    referrer["telegram_id"],
                    "🎉 По твоей реферальной ссылке пришёл новый пользователь!\n"
                    "Тебе начислена 1 бесплатная генерация 🎁",
                )
            except Exception:
                logger.info("Cannot notify referrer %s", referrer["telegram_id"])
            is_ref = True

    # Для текущей экономики выдаём минимум 2 бесплатные генерации
    # пользователям, у которых ещё не было оплат.
    if user.get("total_spent", 0) == 0 and user.get("free_generations", 0) < 2:
        topup = 2 - user.get("free_generations", 0)
        await add_free_generation(message.from_user.id, topup)

    await state.set_state(UserFlow.waiting_for_photo)
    await state.update_data(photo_url=None, render_mode="similarity", gender_hint=None)

    name = message.from_user.first_name or "друг"
    text = WELCOME_REF.format(name=name) if is_ref else WELCOME.format(name=name)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    pool = await get_pool()
    async with pool.acquire() as conn:
        invited = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referred_by = $1",
            message.from_user.id,
        )
    text = REFERRAL_INFO.format(
        bot_username=config.BOT_USERNAME,
        ref_code=user["referral_code"],
        invited=invited,
        free_gens=user["free_generations"],
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("mygenerations"))
async def cmd_my_generations(message: Message):
    generations = await get_user_generations(message.from_user.id, limit=5)
    if not generations:
        await message.answer(MY_GENERATIONS_EMPTY)
        return
    await message.answer(format_generations_text(generations), parse_mode="HTML")


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "💎 <b>Твой баланс</b>\n\n"
        f"🎁 Бесплатных генераций: <b>{user.get('free_generations', 0)}</b>\n"
        f"💳 Потрачено всего: <b>{(user.get('total_spent', 0) / 100):.0f} руб.</b>",
        parse_mode="HTML",
    )


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext, bot: Bot):
    processing_msg = await message.answer("⏳ Загружаю и проверяю фото...")
    photo = message.photo[-1]

    file_url = ""
    try:
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{file.file_path}"
        timeout = aiohttp.ClientTimeout(total=90, connect=20, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await processing_msg.edit_text(
                        "😔 Не удалось скачать фото из Telegram. Попробуй отправить его ещё раз.",
                    )
                    return
                photo_bytes = await resp.read()
    except asyncio.TimeoutError:
        await processing_msg.edit_text(
            "⏰ Фото загружалось слишком долго. Отправь фото ещё раз (лучше как сжатое изображение).",
        )
        return
    except Exception as error:
        logger.exception("Telegram file download failed: %s", error)
        await processing_msg.edit_text(
            "😔 Не удалось обработать фото. Попробуй отправить другое изображение.",
        )
        return

    if len(photo_bytes) < 15_000:
        await processing_msg.edit_text(PHOTO_TOO_SMALL)
        return

    # Основной путь — сохраняем исходник в Blob.
    # Локальный fallback — используем Telegram file URL, если Blob ещё не настроен.
    source_photo_url = file_url
    try:
        source_photo_url = await upload_bytes_to_blob(
            photo_bytes,
            f"sources/{message.from_user.id}_{photo.file_id}.jpg",
        )
    except Exception as error:
        logger.warning(
            "Blob upload failed, using Telegram file URL as source: %s",
            error,
        )
        if not source_photo_url:
            await processing_msg.edit_text(ERROR_GENERIC)
            return

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    has_ref_discount = False
    state_data = await state.get_data()
    render_mode = state_data.get("render_mode", "similarity")
    gender_hint = state_data.get("gender_hint")

    await state.set_state(UserFlow.waiting_for_style)
    await state.update_data(
        photo_url=source_photo_url,
        has_ref_discount=has_ref_discount,
        render_mode=render_mode,
        gender_hint=gender_hint,
    )
    await processing_msg.edit_text(
        _styles_text(render_mode, gender_hint),
        reply_markup=styles_keyboard(
            has_referral_discount=has_ref_discount,
            render_mode=render_mode,
            gender_hint=gender_hint,
        ),
        parse_mode="HTML",
    )


@router.message(~F.photo, UserFlow.waiting_for_photo)
async def handle_no_photo(message: Message):
    await message.answer(
        "📸 Мне нужно твоё фото! Отправь изображение (не файл), "
        "на котором хорошо видно лицо.",
    )


@router.callback_query(F.data.startswith("style:"))
async def handle_style_choice(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photo_url = data.get("photo_url")
    has_ref_discount = data.get("has_ref_discount", False)
    render_mode = data.get("render_mode", "similarity")
    gender_hint = data.get("gender_hint")

    if not photo_url:
        await callback.answer(NEED_PHOTO_FIRST, show_alert=True)
        return

    if gender_hint not in ("male", "female"):
        await callback.answer("Укажи пол кнопками выше, чтобы сохранить сходство.", show_alert=True)
        return

    style_id = callback.data.split(":", 1)[1]
    await callback.answer()
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name,
    )

    if style_id == "pack":
        await _handle_pack_choice(callback, state, user, photo_url, render_mode, gender_hint)
        return

    style = get_style(style_id)
    if not style:
        await callback.message.answer(ERROR_GENERIC)
        return

    if user["free_generations"] > 0 and await use_free_generation(callback.from_user.id):
        generation_id = await create_generation(callback.from_user.id, style_id, photo_url)
        await enqueue_generation_task(
            {
                "generation_id": generation_id,
                "user_id": callback.from_user.id,
                "style_id": style_id,
                "photo_url": photo_url,
                "render_mode": render_mode,
                "gender_hint": gender_hint,
            }
        )
        await state.set_state(UserFlow.waiting_for_photo)
        await callback.message.edit_text(
            f"🎁 Использую твою бесплатную генерацию!\n"
            f"🎨 Создаю образ <b>{style['emoji']} {style['name']}</b>...",
            parse_mode="HTML",
        )
        return

    price = config.PRICE_SINGLE
    price_rub = price // 100
    generation_id = await create_generation(callback.from_user.id, style_id, photo_url)
    idempotence_key = str(uuid.uuid4())

    try:
        payment_result = await yukassa_create_payment(
            amount_kopecks=price,
            user_id=callback.from_user.id,
            generation_ids=[generation_id],
            style_id=style_id,
            is_pack=False,
            return_url=f"https://t.me/{config.BOT_USERNAME}",
            idempotence_key=idempotence_key,
        )
    except Exception as error:
        await update_generation(generation_id, "failed", error_message="payment_init_failed")
        logger.exception("Payment creation failed: %s", error)
        await _safe_edit_text(
            callback,
            "😔 Не удалось создать платёж. Попробуй позже или напиши /start",
        )
        return

    await db_create_payment(
        payment_id=payment_result["payment_id"],
        user_id=callback.from_user.id,
        generation_ids=[generation_id],
        amount=price,
        style_id=style_id,
        is_pack=False,
        idempotence_key=idempotence_key,
    )

    await state.update_data(
        pending_payment_id=payment_result["payment_id"],
        pending_generation_ids=[generation_id],
        pending_render_mode=render_mode,
        pending_gender_hint=gender_hint,
    )
    text = STYLE_SELECTED.format(
        style_name=f"{style['emoji']} {style['name']}",
        price=price_rub,
    )
    await callback.message.edit_text(
        text,
        reply_markup=payment_keyboard(payment_result["confirmation_url"]),
        parse_mode="HTML",
    )


async def _handle_pack_choice(
    callback: CallbackQuery,
    state: FSMContext,
    user: dict,
    photo_url: str,
    render_mode: str,
    gender_hint: str,
):
    price = config.PRICE_PACK
    price_rub = price // 100
    save_rub = (len(PACK_STYLE_IDS) * config.PRICE_SINGLE - price) // 100

    style_list = "\n".join(
        f"• {STYLES[style_id]['emoji']} {STYLES[style_id]['name']}"
        for style_id in PACK_STYLE_IDS
        if style_id in STYLES
    )
    text = PACK_SELECTED.format(
        count=len(PACK_STYLE_IDS),
        style_list=style_list,
        price=price_rub,
        save=save_rub,
    )

    generation_ids: list[int] = []
    for style_id in PACK_STYLE_IDS:
        generation_id = await create_generation(
            user["telegram_id"],
            style_id,
            photo_url,
            is_pack=True,
        )
        generation_ids.append(generation_id)

    idempotence_key = str(uuid.uuid4())
    try:
        payment_result = await yukassa_create_payment(
            amount_kopecks=price,
            user_id=user["telegram_id"],
            generation_ids=generation_ids,
            style_id="pack",
            is_pack=True,
            return_url=f"https://t.me/{config.BOT_USERNAME}",
            idempotence_key=idempotence_key,
        )
    except Exception as error:
        for generation_id in generation_ids:
            await update_generation(generation_id, "failed", error_message="payment_init_failed")
        logger.exception("Pack payment creation failed: %s", error)
        await _safe_edit_text(callback, "😔 Не удалось создать платёж. Попробуй позже.")
        return

    await db_create_payment(
        payment_id=payment_result["payment_id"],
        user_id=user["telegram_id"],
        generation_ids=generation_ids,
        amount=price,
        style_id="pack",
        is_pack=True,
        idempotence_key=idempotence_key,
    )
    await state.update_data(
        pending_payment_id=payment_result["payment_id"],
        pending_generation_ids=generation_ids,
        pending_render_mode=render_mode,
        pending_gender_hint=gender_hint,
    )
    await callback.message.edit_text(
        text,
        reply_markup=payment_keyboard(payment_result["confirmation_url"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_styles")
async def handle_back_to_styles(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    has_ref = data.get("has_ref_discount", False)
    render_mode = data.get("render_mode", "similarity")
    gender_hint = data.get("gender_hint")
    await callback.message.edit_text(
        _styles_text(render_mode, gender_hint),
        reply_markup=styles_keyboard(
            has_referral_discount=has_ref,
            render_mode=render_mode,
            gender_hint=gender_hint,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_mode:"))
async def handle_set_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    if mode not in ("fantasy", "similarity"):
        await callback.answer()
        return

    data = await state.get_data()
    if not data.get("photo_url"):
        await callback.answer("Сначала отправь фото", show_alert=True)
        return

    await state.update_data(render_mode=mode)
    has_ref = data.get("has_ref_discount", False)
    gender_hint = data.get("gender_hint")
    await callback.message.edit_text(
        _styles_text(mode, gender_hint),
        reply_markup=styles_keyboard(
            has_referral_discount=has_ref,
            render_mode=mode,
            gender_hint=gender_hint,
        ),
        parse_mode="HTML",
    )
    await callback.answer("Режим обновлён")


@router.callback_query(F.data.startswith("set_gender:"))
async def handle_set_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split(":", 1)[1]
    if gender not in ("male", "female"):
        await callback.answer()
        return

    data = await state.get_data()
    if not data.get("photo_url"):
        await callback.answer("Сначала отправь фото", show_alert=True)
        return

    render_mode = data.get("render_mode", "similarity")
    has_ref = data.get("has_ref_discount", False)
    await state.update_data(gender_hint=gender)
    await callback.message.edit_text(
        _styles_text(render_mode, gender),
        reply_markup=styles_keyboard(
            has_referral_discount=has_ref,
            render_mode=render_mode,
            gender_hint=gender,
        ),
        parse_mode="HTML",
    )
    await callback.answer("Пол сохранен")


@router.callback_query(F.data == "check_payment")
async def handle_check_payment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payment_id = data.get("pending_payment_id")
    generation_ids = data.get("pending_generation_ids") or []
    render_mode = data.get("pending_render_mode", data.get("render_mode", "similarity"))
    gender_hint = data.get("pending_gender_hint", data.get("gender_hint"))

    if not payment_id or not generation_ids:
        await callback.answer("Не нашёл активный платёж. Выбери стиль снова.", show_alert=True)
        return

    try:
        payment_info = await get_payment_info(payment_id)
    except Exception as error:
        logger.exception("Payment status check failed: %s", error)
        await callback.answer("Не удалось проверить оплату, попробуй через 10 секунд.", show_alert=True)
        return

    status = payment_info.get("status")
    if status != "succeeded":
        await callback.answer("Оплата ещё не подтверждена. Если оплатил только что, подожди 5-10 секунд.", show_alert=True)
        return

    payment = await get_payment(payment_id)
    if payment and payment.get("status") != "succeeded":
        await update_payment_status(payment_id, "succeeded")
        await add_total_spent(callback.from_user.id, payment["amount"])

    enqueued = 0
    for generation_id in generation_ids:
        generation = await get_generation(generation_id)
        if not generation:
            continue
        if generation.get("status") in ("queued", "processing", "completed"):
            continue
        await update_generation(generation_id, "queued")
        await enqueue_generation_task(
            {
                "generation_id": generation_id,
                "user_id": callback.from_user.id,
                "style_id": generation["style_id"],
                "photo_url": generation["source_photo_url"],
                "render_mode": render_mode,
                "gender_hint": gender_hint,
            }
        )
        enqueued += 1

    await state.set_state(UserFlow.waiting_for_photo)
    await state.update_data(pending_payment_id=None, pending_generation_ids=None, photo_url=None)

    if enqueued:
        await callback.message.answer(
            "✅ Оплата подтверждена! Запустил генерацию, пришлю результат как будет готов.\n"
            "Если генерация сорвётся, 1 попытка автоматически вернётся на баланс.",
        )
    else:
        await callback.message.answer("✅ Оплата уже подтверждена. Генерация уже запущена.")
    await callback.answer()


@router.callback_query(F.data == "new_generation")
async def handle_new_generation(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.waiting_for_photo)
    await state.update_data(photo_url=None)
    await callback.message.answer("📸 Отправь фото — создадим новый образ!")
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.waiting_for_photo)
    await callback.message.edit_text("Отменено. Отправь новое фото когда будешь готов.")
    await callback.answer()


@router.callback_query(F.data == "my_generations")
async def handle_my_generations_cb(callback: CallbackQuery):
    generations = await get_user_generations(callback.from_user.id, limit=5)
    if not generations:
        await callback.answer(MY_GENERATIONS_EMPTY, show_alert=True)
        return
    await callback.message.answer(
        format_generations_text(generations, compact=True),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "balance")
async def handle_balance(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        user = await get_or_create_user(callback.from_user.id, callback.from_user.username)
    await callback.message.answer(
        "💎 <b>Твой баланс</b>\n\n"
        f"🎁 Бесплатных генераций: <b>{user.get('free_generations', 0)}</b>\n"
        f"💳 Потрачено всего: <b>{(user.get('total_spent', 0) / 100):.0f} руб.</b>",
        parse_mode="HTML",
    )
    await callback.answer()
