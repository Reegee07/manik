from __future__ import annotations

from html import escape
from typing import Iterable
from collections import defaultdict


def h(text: str) -> str:
    return escape(text or "")


def fmt_booking_for_user(day: str, time: str) -> str:
    return (
        "<b>Ваша запись</b>\n\n"
        f"📅 <b>Дата:</b> {h(day)}\n"
        f"⏰ <b>Время:</b> {h(time)}\n"
    )


def fmt_booking_for_admin(
    booking_id: int,
    user_id: int,
    username: str | None,
    day: str,
    time: str,
    name: str,
    phone: str,
    title: str = "Новая запись",
) -> str:
    uname = (username or "").strip()
    uname_part = f" (@{h(uname)})" if uname else ""
    return (
        f"<b>{h(title)}</b>\n\n"
        f"🆔 <b>ID записи:</b> {booking_id}\n"
        f"👤 <b>Пользователь:</b> <code>{user_id}</code>{uname_part}\n"
        f"📅 <b>Дата:</b> {h(day)}\n"
        f"⏰ <b>Время:</b> {h(time)}\n"
        f"🙍 <b>Имя:</b> {h(name)}\n"
        f"📞 <b>Телефон:</b> {h(phone)}\n"
    )


def fmt_day_schedule(day: str, slots: list[tuple[str, str]]) -> str:
    """
    slots: (time, status) where status in free/booked/inactive
    """
    lines = [f"<b>Расписание на {h(day)}</b>", ""]
    if not slots:
        lines.append("<i>Слоты не добавлены</i>")
        return "\n".join(lines)

    for t, st in slots:
        if st == "booked":
            mark = "⛔️"
            st_txt = "занято"
        elif st == "inactive":
            mark = "🚫"
            st_txt = "слот выключен"
        else:
            mark = "✅"
            st_txt = "свободно"
        lines.append(f"{mark} <b>{h(t)}</b> — <i>{st_txt}</i>")
    return "\n".join(lines)


def fmt_week_bookings(start_day: str, end_day: str, bookings: Iterable[object]) -> str:
    """
    bookings: items with fields day,time,id,user_id,username,name,phone
    """
    by_day: dict[str, list[object]] = defaultdict(list)
    for b in bookings:
        by_day[str(getattr(b, "day"))].append(b)

    lines: list[str] = [f"<b>Записи на неделю</b>\n{h(start_day)} — {h(end_day)}", ""]
    if not by_day:
        lines.append("<i>Записей нет</i>")
        return "\n".join(lines)

    for day in sorted(by_day.keys()):
        lines.append(f"<b>{h(day)}</b>")
        for b in sorted(by_day[day], key=lambda x: (getattr(x, "time"), getattr(x, "id"))):
            time = getattr(b, "time")
            booking_id = getattr(b, "id")
            user_id = getattr(b, "user_id")
            username = (getattr(b, "username", None) or "").strip()
            uname_part = f" (@{h(username)})" if username else ""
            name = getattr(b, "name")
            phone = getattr(b, "phone")
            lines.append(
                f"⏰ <b>{h(time)}</b> — {h(name)} ({h(phone)})\n"
                f"    👤 <code>{user_id}</code>{uname_part}  |  🆔 <code>{booking_id}</code>"
            )
        lines.append("")

    return "\n".join(lines).rstrip()

