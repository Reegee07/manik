from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import CalCb, BookingCb, AdminCb, AdminCalCb, AdminTimeCb
from app.services.datetime_utils import month_grid, format_day


def main_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записаться", callback_data="menu:book")
    kb.button(text="🧾 Моя запись", callback_data="menu:my")
    kb.button(text="❌ Отменить запись", callback_data="menu:cancel")
    kb.adjust(2, 1)

    kb.button(text="💰 Прайсы", callback_data="menu:prices")
    kb.button(text="🖼 Портфолио", callback_data="menu:portfolio")
    kb.adjust(2, 1, 2)

    if is_admin:
        kb.button(text="⚙️ Админ-панель", callback_data="menu:admin")
        kb.adjust(2, 1, 2, 1)
    return kb.as_markup()


def bottom_menu_kb(is_admin: bool) -> ReplyKeyboardMarkup:
    """
    Нижняя клавиатура (ReplyKeyboardMarkup).
    """
    row: list[KeyboardButton] = [KeyboardButton(text="🏠 Меню")]
    if is_admin:
        row.append(KeyboardButton(text="⚙️ Админ-меню"))
    else:
        row.append(KeyboardButton(text="🧾 Моя запись"))
    return ReplyKeyboardMarkup(
        keyboard=[row],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие…",
    )


def subscription_gate_kb(channel_link: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Подписаться", url=channel_link),
    )
    kb.row(
        InlineKeyboardButton(text="🔁 Проверить подписку", callback_data="sub:check"),
    )
    kb.row(
        InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"),
    )
    return kb.as_markup()


def calendar_kb(
    year: int,
    month: int,
    available_days: set[str],
    min_d: date,
    max_d: date,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # Шапка навигации
    kb.row(
        InlineKeyboardButton(text="◀️", callback_data=CalCb(action="nav_prev", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text=f"{year}-{month:02d}", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="▶️", callback_data=CalCb(action="nav_next", y=year, m=month, d=0).pack()),
    )

    # Дни недели
    kb.row(
        InlineKeyboardButton(text="Пн", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Вт", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Ср", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Чт", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Пт", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Сб", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Вс", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack()),
    )

    for week in month_grid(year, month):
        row_btns: list[InlineKeyboardButton] = []
        for d in week:
            if d is None:
                row_btns.append(
                    InlineKeyboardButton(text=" ", callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack())
                )
                continue
            day_str = format_day(d)
            in_range = (min_d <= d <= max_d)
            is_avail = day_str in available_days
            if in_range and is_avail:
                row_btns.append(
                    InlineKeyboardButton(
                        text=f"🟢{d.day:02d}",
                        callback_data=CalCb(action="select", y=d.year, m=d.month, d=d.day).pack(),
                    )
                )
            else:
                row_btns.append(
                    InlineKeyboardButton(
                        text=f"⚪️{d.day:02d}",
                        callback_data=CalCb(action="ignore", y=year, m=month, d=0).pack(),
                    )
                )
        kb.row(*row_btns)

    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()


def admin_calendar_kb(
    year: int,
    month: int,
    min_d: date,
    max_d: date,
    open_days: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    Календарь для админки: все дни в диапазоне кликабельны (без проверки слотов).
    """
    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(text="◀️", callback_data=AdminCalCb(action="nav_prev", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text=f"{year}-{month:02d}", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="▶️", callback_data=AdminCalCb(action="nav_next", y=year, m=month, d=0).pack()),
    )

    kb.row(
        InlineKeyboardButton(text="Пн", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Вт", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Ср", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Чт", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Пт", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Сб", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
        InlineKeyboardButton(text="Вс", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack()),
    )

    open_days = open_days or set()

    for week in month_grid(year, month):
        row_btns: list[InlineKeyboardButton] = []
        for d in week:
            if d is None:
                row_btns.append(
                    InlineKeyboardButton(text=" ", callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack())
                )
                continue
            in_range = (min_d <= d <= max_d)
            day_str = format_day(d)
            if in_range:
                is_open = day_str in open_days
                label = f"🟢{d.day:02d}" if is_open else f"⚪️{d.day:02d}"
                row_btns.append(
                    InlineKeyboardButton(
                        text=label,
                        callback_data=AdminCalCb(action="select", y=d.year, m=d.month, d=d.day).pack(),
                    )
                )
            else:
                row_btns.append(
                    InlineKeyboardButton(
                        text=f"·{d.day:02d}",
                        callback_data=AdminCalCb(action="ignore", y=year, m=month, d=0).pack(),
                    )
                )
        kb.row(*row_btns)

    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()


def admin_time_suggestions_kb(times: Sequence[str]) -> InlineKeyboardMarkup:
    """
    Подсказки времени для админки (можно и вручную ввести).
    """
    kb = InlineKeyboardBuilder()
    for t in times:
        encoded = t.replace(":", "-")
        kb.button(text=f"⏰ {t}", callback_data=AdminTimeCb(time=encoded).pack())
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text="⌨️ Ввести вручную", callback_data="adm:manual_time"))
    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()


def times_kb(day: str, times: Sequence[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not times:
        kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
        return kb.as_markup()
    for t in times:
        # В callback_data нельзя использовать двоеточие (":"), поэтому кодируем время,
        # заменяя ":" на "-" и декодируем обратно в хендлере.
        encoded_time = t.replace(":", "-")
        kb.button(text=f"⏰ {t}", callback_data=BookingCb(action="time", day=day, time=encoded_time).pack())
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text="↩️ Назад к календарю", callback_data=f"book:back_cal:{day}"))
    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()


def confirm_booking_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="book:confirm")
    kb.button(text="❌ Отмена", callback_data="book:abort")
    kb.adjust(2)
    return kb.as_markup()


def portfolio_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Смотреть портфолио", url="https://ru.pinterest.com/crystalwithluv/_created/"))
    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить рабочий день", callback_data=AdminCb(action="open_day").pack())
    kb.button(text="🚫 Закрыть день полностью", callback_data=AdminCb(action="close_day").pack())
    kb.button(text="➕ Добавить слот", callback_data=AdminCb(action="add_slot").pack())
    kb.button(text="➖ Удалить слот", callback_data=AdminCb(action="del_slot").pack())
    kb.button(text="📋 Расписание на дату", callback_data=AdminCb(action="view_day").pack())
    kb.button(text="📅 Записи на неделю", callback_data=AdminCb(action="view_week").pack())
    kb.button(text="📆 Рабочие дни", callback_data=AdminCb(action="work_days").pack())
    kb.button(text="🔁 Перенести запись", callback_data=AdminCb(action="move_booking").pack())
    kb.button(text="🗑 Отменить запись (по ID)", callback_data=AdminCb(action="cancel_booking").pack())
    kb.adjust(2, 2, 2, 2, 1)
    kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))
    return kb.as_markup()

