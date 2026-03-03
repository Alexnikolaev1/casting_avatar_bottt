"""Набор роутеров приложения."""

from bot.routers.admin import router as admin_router
from bot.routers.user import router as user_router

__all__ = ["admin_router", "user_router"]
