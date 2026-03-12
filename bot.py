from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import load_config
from app.database.connection import connect
from app.database.schema import init_db
from app.database.repo import Repo
from app.handlers import get_root_router
from app.middlewares.context import ContextMiddleware
from app.services.scheduler import restore_reminders_on_start


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    config = load_config()

    # Логируем часть токена, чтобы убедиться, что он совпадает с тем,
    # который ты проверял через /getMe в браузере.
    masked_token = f"{config.bot_token[:8]}...{config.bot_token[-6:]}"
    logging.getLogger(__name__).info("Using BOT_TOKEN: %s", masked_token)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    conn = await connect(config.db_path)
    await init_db(conn)
    repo = Repo(conn)

    scheduler = AsyncIOScheduler(timezone=None)
    scheduler.start()
    await restore_reminders_on_start(scheduler, repo, bot)

    dp = Dispatcher()
    dp.update.middleware(ContextMiddleware(config=config, repo=repo, scheduler=scheduler))
    dp.include_router(get_root_router())

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

