from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import calendar


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


def today() -> date:
    return datetime.now().date()


def parse_day(day_str: str) -> date:
    return datetime.strptime(day_str, DATE_FMT).date()


def format_day(d: date) -> str:
    return d.strftime(DATE_FMT)


def parse_dt(day_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{day_str} {time_str}", "%Y-%m-%d %H:%M")


def month_grid(year: int, month: int) -> list[list[date | None]]:
    """
    Сетка месяца: недели по 7 элементов (понедельник..воскресенье),
    где элементы — date или None (пустые клетки).
    """
    cal = calendar.Calendar(firstweekday=0)  # Monday
    weeks: list[list[date | None]] = []
    week: list[date | None] = []
    for d in cal.itermonthdates(year, month):
        if d.month != month:
            week.append(None)
        else:
            week.append(d)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        weeks.append(week + [None] * (7 - len(week)))
    return weeks

