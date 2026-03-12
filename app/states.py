from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_day = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()


class AdminStates(StatesGroup):
    waiting_day = State()
    waiting_time = State()
    waiting_booking_id = State()

