from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware

from app.config import Config
from app.database.repo import Repo
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class ContextMiddleware(BaseMiddleware):
    def __init__(self, config: Config, repo: Repo, scheduler: AsyncIOScheduler):
        super().__init__()
        self._config = config
        self._repo = repo
        self._scheduler = scheduler

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        data["config"] = self._config
        data["repo"] = self._repo
        data["scheduler"] = self._scheduler
        return await handler(event, data)

