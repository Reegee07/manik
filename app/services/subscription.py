from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMember


async def is_subscribed(bot: Bot, channel_id: int, user_id: int) -> bool:
    """
    Проверка подписки на канал через getChatMember.
    Возвращает False, если бот не может проверить или пользователь не участник.
    """
    try:
        member: ChatMember = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
    except TelegramBadRequest:
        return False
    status = getattr(member, "status", None)
    return status in {"member", "administrator", "creator"}

