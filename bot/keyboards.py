"""
Клавиатуры и кнопки бота.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import config
from bot.styles import STYLES

RENDER_MODE_LABELS = {
    "fantasy": "🎭 Больше фантазии",
    "similarity": "🧠 Больше сходства",
}

GENDER_LABELS = {
    "male": "👨 Мужчина",
    "female": "👩 Женщина",
}


def styles_keyboard(
    has_referral_discount: bool = False,
    render_mode: str = "similarity",
    gender_hint: str | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора стиля образа."""
    buttons = [[
        InlineKeyboardButton(
            text=("✅ " if render_mode == "fantasy" else "") + RENDER_MODE_LABELS["fantasy"],
            callback_data="set_mode:fantasy",
        ),
        InlineKeyboardButton(
            text=("✅ " if render_mode == "similarity" else "") + RENDER_MODE_LABELS["similarity"],
            callback_data="set_mode:similarity",
        ),
    ]]
    buttons.append([
        InlineKeyboardButton(
            text=("✅ " if gender_hint == "male" else "") + GENDER_LABELS["male"],
            callback_data="set_gender:male",
        ),
        InlineKeyboardButton(
            text=("✅ " if gender_hint == "female" else "") + GENDER_LABELS["female"],
            callback_data="set_gender:female",
        ),
    ])
    single_price = f"{config.PRICE_SINGLE // 100} руб."

    for style_id, style in STYLES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{style['emoji']} {style['name']} · {single_price}",
            callback_data=f"style:{style_id}"
        )])

    pack_price = f"{config.PRICE_PACK // 100} руб."
    buttons.append([InlineKeyboardButton(
        text=f"🔥 Премиум-пакет ({len(STYLES)} стилей) · {pack_price}",
        callback_data="style:pack"
    )])
    buttons.append([InlineKeyboardButton(text="💎 Баланс", callback_data="balance")])
    buttons.append([InlineKeyboardButton(text="📋 Мои образы", callback_data="my_generations")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить безопасно", url=payment_url)],
        [InlineKeyboardButton(text="✅ Я оплатил, проверить", callback_data="check_payment")],
        [InlineKeyboardButton(text="↩️ К выбору стилей", callback_data="back_to_styles")],
    ])


def share_keyboard(bot_username: str, ref_code: str) -> InlineKeyboardMarkup:
    share_text = (
        "Смотри что нейросеть сделала из моего фото 🔥 "
        "Попробуй сам — первый образ со скидкой 50%!"
    )
    ref_url = f"https://t.me/{bot_username}?start={ref_code}"
    share_url = f"https://t.me/share/url?url={ref_url}&text={share_text}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Поделиться и получить бонус", url=share_url)],
        [InlineKeyboardButton(text="✨ Создать новый образ", callback_data="new_generation")],
        [InlineKeyboardButton(text="💎 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="📋 Мои образы", callback_data="my_generations")],
    ])


def confirm_pack_keyboard() -> InlineKeyboardMarkup:
    pack_price = config.PRICE_PACK // 100
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да, хочу все образы — {pack_price} руб.", callback_data="confirm_pack")],
        [InlineKeyboardButton(text="← Выбрать один стиль", callback_data="back_to_styles")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ]])


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📬 Рассылка", callback_data="admin:broadcast")],
    ])
