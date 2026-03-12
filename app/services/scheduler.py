from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot

from app.database.repo import Repo, Booking
from app.services.datetime_utils import parse_dt


REMINDER_TEXT_TEMPLATE = (
    "Напоминаем, что вы записаны на наращивание ресниц завтра в {time}.\n"
    "Ждём вас ️"
)


def reminder_job_id(booking_id: int) -> str:
    return f"reminder_{booking_id}"


async def send_reminder(bot: Bot, user_id: int, time_str: str) -> None:
    await bot.send_message(
        chat_id=user_id,
        text=REMINDER_TEXT_TEMPLATE.format(time=time_str),
        parse_mode="HTML",
    )


async def schedule_reminder_if_needed(
    scheduler: AsyncIOScheduler,
    repo: Repo,
    bot: Bot,
    booking: Booking,
) -> None:
    dt_visit = parse_dt(booking.day, booking.time)
    run_at = dt_visit - timedelta(hours=24)
    now = datetime.now()
    if run_at <= now:
        # Запись меньше чем за 24 часа — напоминание не создаём
        await repo.delete_reminder(booking.id)
        try:
            scheduler.remove_job(reminder_job_id(booking.id))
        except Exception:
            pass
        return

    job_id = reminder_job_id(booking.id)
    # Если джоб уже есть — перезапишем
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=run_at),
        id=job_id,
        replace_existing=True,
        kwargs={"bot": bot, "user_id": booking.user_id, "time_str": booking.time},
        misfire_grace_time=60 * 60,  # 1 час на случай простоя
    )
    await repo.upsert_reminder(booking.id, job_id=job_id, run_at_iso=run_at.isoformat(sep=" ", timespec="seconds"))


async def remove_reminder(
    scheduler: AsyncIOScheduler,
    repo: Repo,
    booking_id: int,
) -> None:
    job_id = await repo.get_reminder_job_id(booking_id)
    if job_id:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
    await repo.delete_reminder(booking_id)


async def restore_reminders_on_start(
    scheduler: AsyncIOScheduler,
    repo: Repo,
    bot: Bot,
) -> None:
    """
    Восстанавливает напоминания для всех будущих активных записей.
    """
    bookings = await repo.list_active_bookings_from_now()
    for b in bookings:
        await schedule_reminder_if_needed(scheduler, repo, bot, b)

