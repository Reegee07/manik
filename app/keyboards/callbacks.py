from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CalCb(CallbackData, prefix="cal"):
    action: str  # nav/select/ignore
    y: int
    m: int
    d: int  # 0 если не используется


class BookingCb(CallbackData, prefix="book"):
    action: str  # time/cancel
    day: str  # YYYY-MM-DD
    time: str  # HH:MM


class AdminCb(CallbackData, prefix="adm"):
    action: str
    day: str = ""  # YYYY-MM-DD optional
    time: str = ""  # HH:MM optional
    booking_id: int = 0


class AdminCalCb(CallbackData, prefix="admcal"):
    action: str  # nav/select/ignore
    y: int
    m: int
    d: int  # 0 если не используется


class AdminTimeCb(CallbackData, prefix="admtime"):
    time: str  # HH-MM (":" нельзя)

