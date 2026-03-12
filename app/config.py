from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int

    channel_id: int
    channel_link: str

    schedule_channel_id: int

    db_path: str


def load_config() -> Config:
    """
    Загружает конфиг из переменных окружения (или .env рядом с bot.py).
    """
    # Явно загружаем .env из корня проекта (там, где лежит bot.py),
    # и переопределяем переменные окружения его значениями.
    project_root = Path(__file__).resolve().parent.parent
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=True)

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")

    def _get_int(name: str) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            raise RuntimeError(f"{name} is not set")
        try:
            return int(raw)
        except ValueError as e:
            raise RuntimeError(f"{name} must be int") from e

    admin_id = _get_int("ADMIN_ID")
    channel_id = _get_int("CHANNEL_ID")

    channel_link = os.getenv("CHANNEL_LINK", "").strip()
    if not channel_link:
        raise RuntimeError("CHANNEL_LINK is not set")

    schedule_channel_id_raw = os.getenv("SCHEDULE_CHANNEL_ID", "").strip()
    schedule_channel_id = int(schedule_channel_id_raw) if schedule_channel_id_raw else channel_id

    db_path = os.getenv("DB_PATH", "").strip() or "bot.sqlite3"

    return Config(
        bot_token=bot_token,
        admin_id=admin_id,
        channel_id=channel_id,
        channel_link=channel_link,
        schedule_channel_id=schedule_channel_id,
        db_path=db_path,
    )

