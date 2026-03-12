from __future__ import annotations

from aiogram import Router

from app.handlers.start_menu import router as start_menu_router
from app.handlers.booking import router as booking_router
from app.handlers.admin import router as admin_router


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(start_menu_router)
    root.include_router(booking_router)
    root.include_router(admin_router)
    return root

