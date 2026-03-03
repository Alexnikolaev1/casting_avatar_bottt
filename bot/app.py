"""Главный роутер приложения."""

from aiogram import Router

from bot.database import is_user_banned
from bot.routers import admin_router, user_router
from bot.texts import BANNED

router = Router(name=__name__)
router.include_router(user_router)
router.include_router(admin_router)


@router.message.middleware()
async def ban_check_message_middleware(handler, event, data):
    if getattr(event, "from_user", None) and await is_user_banned(event.from_user.id):
        await event.answer(BANNED)
        return
    return await handler(event, data)


@router.callback_query.middleware()
async def ban_check_callback_middleware(handler, event, data):
    if getattr(event, "from_user", None) and await is_user_banned(event.from_user.id):
        await event.answer(BANNED, show_alert=True)
        return
    return await handler(event, data)
