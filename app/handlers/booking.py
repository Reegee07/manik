from __future__ import annotations

from datetime import date, timedelta

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Config
from app.database.repo import Repo
from app.keyboards.callbacks import CalCb, BookingCb
from app.keyboards.common import (
    calendar_kb,
    confirm_booking_kb,
    main_menu_kb,
    subscription_gate_kb,
    times_kb,
)
from app.services.datetime_utils import today as today_fn, format_day, parse_day
from app.services.formatting import fmt_booking_for_admin, fmt_booking_for_user, fmt_day_schedule
from app.services.scheduler import schedule_reminder_if_needed, remove_reminder
from app.services.subscription import is_subscribed
from app.states import BookingStates


router = Router(name="booking")


async def _show_calendar(call: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    min_d = today_fn()
    max_d = min_d + timedelta(days=30)
    data = await state.get_data()
    year = int(data.get("cal_y") or min_d.year)
    month = int(data.get("cal_m") or min_d.month)

    available = set(
        await repo.list_open_days_with_free_slots(
            start_day=format_day(min_d),
            end_day=format_day(max_d),
        )
    )
    try:
        await call.message.edit_text(
            "<b>Выберите дату</b>\n\n"
            "🟢 — есть свободные слоты\n"
            "⚪️ — нет свободных слотов / вне диапазона",
            reply_markup=calendar_kb(year, month, available_days=available, min_d=min_d, max_d=max_d),
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        # Игнорируем ситуацию, когда Telegram запрещает редактировать сообщение
        # без фактических изменений содержимого/клавиатуры.
        if "message is not modified" not in str(e):
            raise


@router.callback_query(F.data == "menu:book")
async def menu_book(call: CallbackQuery, state: FSMContext, bot: Bot, config: Config, repo: Repo) -> None:
    await state.clear()

    # Проверка подписки (доступ к записи запрещаем до подтверждения)
    if not await is_subscribed(bot, config.channel_id, call.from_user.id):
        await call.message.answer(
            "Для записи необходимо подписаться на канал",
            reply_markup=subscription_gate_kb(config.channel_link),
        )
        await call.answer()
        return

    if await repo.get_active_booking_by_user(call.from_user.id):
        await call.message.answer(
            "<b>У вас уже есть активная запись.</b>\n\n"
            "Сначала отмените её, чтобы записаться снова.",
            parse_mode="HTML",
        )
        await call.answer()
        return

    min_d = today_fn()
    await state.set_state(BookingStates.choosing_day)
    await state.update_data(cal_y=min_d.year, cal_m=min_d.month)
    await _show_calendar(call, state, repo)
    await call.answer()


@router.callback_query(F.data == "menu:reschedule")
async def menu_reschedule(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    config: Config,
    repo: Repo,
) -> None:
    await state.clear()
    b = await repo.get_active_booking_by_user(call.from_user.id)
    if not b:
        await call.message.answer("У вас нет активной записи, которую можно перенести.")
        await call.answer()
        return

    # Информация о правиле переноса и предупреждение про 24 часа
    from datetime import datetime, timedelta
    from app.services.datetime_utils import parse_dt

    try:
        dt_booking = parse_dt(b.day, b.time)
        now = datetime.now()
        diff = dt_booking - now
        base_text = (
            "ℹ️ Обратите внимание: по правилам мастера перенос записи возможен не позднее чем за 24 часа.\n"
            "При переносе позже предоплата может не возвращаться.\n\n"
        )
        if diff < timedelta(hours=24):
            text = (
                "⚠️ До вашей записи осталось меньше 24 часов.\n"
                "По правилам мастера предоплата может не возвращаться при переносе или отмене.\n\n"
            ) + base_text
        else:
            text = base_text
        await call.message.answer(text, parse_mode="HTML")
    except Exception:
        pass

    await state.set_state(BookingStates.choosing_day)
    await state.update_data(mode="reschedule", move_booking_id=b.id)
    await _show_calendar(call, state, repo)
    await call.answer()


@router.callback_query(F.data == "sub:check")
async def subscription_check(call: CallbackQuery, bot: Bot, config: Config, state: FSMContext) -> None:
    if not await is_subscribed(bot, config.channel_id, call.from_user.id):
        await call.answer("Подписка не найдена. Попробуйте ещё раз.", show_alert=True)
        return
    await call.answer("Подписка подтверждена!", show_alert=True)
    # Показываем меню — пользователь сможет нажать "Записаться"
    await state.clear()
    is_admin = call.from_user.id == config.admin_id
    await call.message.edit_text(
        "<b>Доступ открыт.</b>\n\nНажмите «Записаться», чтобы выбрать дату и время.",
        reply_markup=main_menu_kb(is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(CalCb.filter())
async def calendar_actions(call: CallbackQuery, callback_data: CalCb, state: FSMContext, repo: Repo) -> None:
    cur_state = await state.get_state()
    if cur_state != BookingStates.choosing_day.state:
        await call.answer()
        return

    min_d = today_fn()
    max_d = min_d + timedelta(days=30)

    if callback_data.action == "ignore":
        await call.answer()
        return

    if callback_data.action in {"nav_prev", "nav_next"}:
        y, m = callback_data.y, callback_data.m
        if callback_data.action == "nav_prev":
            if m == 1:
                y, m = y - 1, 12
            else:
                m -= 1
        else:
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1

        # Ограничим диапазоном календаря (текущий..следующий месяц максимум)
        min_first = date(min_d.year, min_d.month, 1)
        max_first = date(max_d.year, max_d.month, 1)
        new_first = date(y, m, 1)
        if new_first < min_first:
            y, m = min_first.year, min_first.month
        if new_first > max_first:
            y, m = max_first.year, max_first.month

        await state.update_data(cal_y=y, cal_m=m)
        await _show_calendar(call, state, repo)
        await call.answer()
        return

    if callback_data.action == "select":
        try:
            d = date(callback_data.y, callback_data.m, callback_data.d)
        except ValueError:
            await call.answer()
            return

        if not (min_d <= d <= max_d):
            await call.answer("Дата вне диапазона", show_alert=True)
            return

        day_str = format_day(d)
        times = await repo.list_free_times(day_str)
        if not times:
            await call.answer("На эту дату нет свободных слотов", show_alert=True)
            return

        await state.update_data(day=day_str)
        await state.set_state(BookingStates.choosing_time)
        await call.message.edit_text(
            f"<b>Дата:</b> {day_str}\n\n<b>Выберите время</b>",
            reply_markup=times_kb(day_str, times),
            parse_mode="HTML",
        )
        await call.answer()


@router.callback_query(F.data.startswith("book:back_cal:"))
async def back_to_calendar(call: CallbackQuery, state: FSMContext, repo: Repo) -> None:
    cur_state = await state.get_state()
    if cur_state not in {BookingStates.choosing_time.state, BookingStates.entering_name.state, BookingStates.entering_phone.state, BookingStates.confirming.state}:
        await call.answer()
        return

    day_str = call.data.split("book:back_cal:", 1)[1]
    try:
        d = parse_day(day_str)
    except Exception:
        d = today_fn()

    await state.set_state(BookingStates.choosing_day)
    await state.update_data(cal_y=d.year, cal_m=d.month)
    await _show_calendar(call, state, repo)
    await call.answer()


@router.callback_query(BookingCb.filter(F.action == "time"))
async def choose_time(
    call: CallbackQuery,
    callback_data: BookingCb,
    state: FSMContext,
    repo: Repo,
    bot: Bot,
    config: Config,
    scheduler: AsyncIOScheduler,
) -> None:
    cur_state = await state.get_state()
    if cur_state != BookingStates.choosing_time.state:
        await call.answer()
        return

    data = await state.get_data()
    mode = data.get("mode") or "new"

    # Декодируем время из callback_data (":" нельзя хранить напрямую)
    slot_time = callback_data.time.replace("-", ":")

    # Проверим доступность слота
    times = await repo.list_free_times(callback_data.day)
    if slot_time not in times:
        await call.answer("Слот уже заняли. Выберите другое время.", show_alert=True)
        return

    if mode == "reschedule":
        booking_id = data.get("move_booking_id")
        if not booking_id:
            await call.message.answer("ID записи не найден. Начните заново.", parse_mode="HTML")
            await state.clear()
            await call.answer()
            return
        try:
            await repo.move_booking(booking_id, callback_data.day, slot_time)
        except ValueError as e:
            await call.message.answer(
                f"Не удалось перенести запись: {e}", parse_mode="HTML"
            )
            await state.clear()
            await call.answer()
            return

        b = await repo.get_booking(booking_id)
        if not b:
            await call.message.answer("Запись не найдена после переноса.", parse_mode="HTML")
            await state.clear()
            await call.answer()
            return

        # Обновляем напоминание
        await remove_reminder(scheduler, repo, booking_id)
        try:
            await schedule_reminder_if_needed(scheduler, repo, bot, b)
        except Exception:
            pass

        # Уведомляем клиента
        try:
            await bot.send_message(
                chat_id=b.user_id,
                text=(
                    "<b>Ваша запись перенесена.</b>\n\n"
                    f"📅 <b>Новая дата:</b> {b.day}\n"
                    f"⏰ <b>Новое время:</b> {b.time}\n"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        # Уведомляем админа
        try:
            from app.services.formatting import fmt_booking_for_admin

            text_admin = fmt_booking_for_admin(
                booking_id=booking_id,
                user_id=b.user_id,
                username=call.from_user.username if call.from_user else None,
                day=b.day,
                time=b.time,
                name=b.name,
                phone=b.phone,
                title="Запись перенесена клиентом",
            )
            await bot.send_message(chat_id=config.admin_id, text=text_admin, parse_mode="HTML")
        except Exception:
            pass

        await call.message.edit_text(
            f"🔁 Ваша запись перенесена на <b>{b.day} {b.time}</b>.",
            parse_mode="HTML",
        )
        await state.clear()
        await call.answer()
        return

    # Обычный сценарий новой записи
    # Повторная защита от мультизаписей
    if await repo.get_active_booking_by_user(call.from_user.id):
        await call.message.answer(
            "<b>У вас уже есть активная запись.</b>\nСначала отмените её.",
            parse_mode="HTML",
        )
        await state.clear()
        await call.answer()
        return

    await state.update_data(day=callback_data.day, time=slot_time)
    await state.set_state(BookingStates.entering_name)
    await call.message.edit_text(
        f"<b>Дата:</b> {callback_data.day}\n<b>Время:</b> {slot_time}\n\n"
        "Введите <b>имя</b>:",
        parse_mode="HTML",
    )
    await call.answer()


@router.message(BookingStates.entering_name)
async def enter_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Введите имя (минимум 2 символа).")
        return
    await state.update_data(name=name)
    await state.set_state(BookingStates.entering_phone)
    await message.answer("Введите <b>номер телефона</b>:", parse_mode="HTML")


@router.message(BookingStates.entering_phone)
async def enter_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 5:
        await message.answer("Введите корректный номер телефона.")
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingStates.confirming)
    data = await state.get_data()
    await message.answer(
        "<b>Проверьте данные</b>\n\n"
        f"📅 <b>Дата:</b> {data['day']}\n"
        f"⏰ <b>Время:</b> {data['time']}\n"
        f"🙍 <b>Имя:</b> {data['name']}\n"
        f"📞 <b>Телефон:</b> {data['phone']}\n\n"
        "Подтверждаем запись?",
        reply_markup=confirm_booking_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "book:abort")
async def booking_abort(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.clear()
    is_admin = call.from_user.id == config.admin_id
    await call.message.edit_text("Запись отменена.", reply_markup=main_menu_kb(is_admin=is_admin))
    await call.answer()


@router.callback_query(F.data == "book:confirm")
async def booking_confirm(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    config: Config,
    repo: Repo,
    scheduler: AsyncIOScheduler,
) -> None:
    data = await state.get_data()
    day = data.get("day")
    time = data.get("time")
    name = data.get("name")
    phone = data.get("phone")
    if not all([day, time, name, phone]):
        await call.answer("Данные не найдены. Начните заново.", show_alert=True)
        await state.clear()
        return

    try:
        booking_id = await repo.create_booking(call.from_user.id, day, time, name, phone)
    except Exception as e:
        await call.message.answer(
            "<b>Не удалось создать запись.</b>\n"
            "Возможно, слот уже занят или у вас уже есть запись.",
            parse_mode="HTML",
        )
        await state.clear()
        await call.answer()
        return

    booking = await repo.get_booking(booking_id)
    if booking:
        await schedule_reminder_if_needed(scheduler, repo, bot, booking)

    # пользователю
    await call.message.edit_text(
        "<b>Запись подтверждена!</b>\n\n" + fmt_booking_for_user(day, time),
        parse_mode="HTML",
    )

    # админу
    try:
        await bot.send_message(
            chat_id=config.admin_id,
            text=fmt_booking_for_admin(booking_id, call.from_user.id, call.from_user.username, day, time, name, phone),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass

    # в канал расписания — текущий день целиком
    try:
        slots = await repo.list_all_slots_with_status(day)
        await bot.send_message(
            chat_id=config.schedule_channel_id,
            text=fmt_day_schedule(day, slots),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass

    await state.clear()
    await call.answer()


@router.callback_query(F.data == "menu:my")
async def my_booking(call: CallbackQuery, repo: Repo) -> None:
    b = await repo.get_active_booking_by_user(call.from_user.id)
    if not b:
        await call.message.answer("У вас нет активной записи.")
        await call.answer()
        return
    await call.message.answer(fmt_booking_for_user(b.day, b.time), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu:cancel")
async def cancel_my_booking(call: CallbackQuery, repo: Repo, scheduler: AsyncIOScheduler, bot: Bot, config: Config) -> None:
    b = await repo.get_active_booking_by_user(call.from_user.id)
    if not b:
        await call.message.answer("У вас нет активной записи.")
        await call.answer()
        return

    await repo.cancel_booking_by_id(b.id)
    await remove_reminder(scheduler, repo, b.id)
    await call.message.answer("✅ Запись отменена. Слот снова доступен для записи.")

    # Уведомим администратора
    try:
        text = fmt_booking_for_admin(
            booking_id=b.id,
            user_id=b.user_id,
            username=call.from_user.username if call.from_user else None,
            day=b.day,
            time=b.time,
            name=b.name,
            phone=b.phone,
            title="Запись отменена клиентом",
        )
        await bot.send_message(chat_id=config.admin_id, text=text, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await call.answer()

