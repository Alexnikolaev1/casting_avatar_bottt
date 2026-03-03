"""Административные команды и callback'и."""

import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.database import get_pool, get_stats
from bot.keyboards import admin_keyboard
from bot.states import UserFlow

router = Router(name=__name__)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await message.answer("🔧 Панель администратора:", reply_markup=admin_keyboard())


@router.callback_query(F.data == "admin:stats")
async def handle_admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    stats = await get_stats()
    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"📈 Новых за 24ч: <b>{stats['today_users']}</b>\n\n"
        f"🎨 Всего генераций: <b>{stats['total_generations']}</b>\n"
        f"✅ Завершено: <b>{stats['completed_generations']}</b>\n\n"
        f"💰 Выручка (всего): <b>{stats['total_revenue_rub']:.0f} руб.</b>\n"
        f"📦 Оплат за 24ч: <b>{stats['today_payments']}</b>"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast")
async def handle_admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(UserFlow.waiting_for_broadcast)
    await callback.message.answer(
        "📬 Введи текст рассылки (поддерживает HTML).\n"
        "Отправь /cancel чтобы отменить.",
    )
    await callback.answer()


@router.message(UserFlow.waiting_for_broadcast, Command("cancel"))
async def handle_broadcast_cancel(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS:
        return
    await state.set_state(UserFlow.waiting_for_photo)
    await message.answer("Рассылка отменена.")


@router.message(UserFlow.waiting_for_broadcast)
async def handle_broadcast_text(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    text = message.text or message.caption or ""
    if not text:
        await message.answer("Введи текст для рассылки.")
        return

    await state.set_state(UserFlow.waiting_for_photo)
    await message.answer("⏳ Начинаю рассылку...")

    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT telegram_id FROM users WHERE is_banned = FALSE")

    sent = 0
    failed = 0
    for row in users:
        try:
            await bot.send_message(row["telegram_id"], text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/sec, в пределах лимита

    await message.answer(
        f"✅ Рассылка завершена!\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
    )
