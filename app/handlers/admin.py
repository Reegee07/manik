from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Config
from app.database.repo import Repo
from app.keyboards.callbacks import AdminCb, AdminCalCb, AdminTimeCb
from app.keyboards.common import admin_calendar_kb, admin_menu_kb, admin_time_suggestions_kb, main_menu_kb
from app.services.datetime_utils import today as today_fn, format_day
from app.services.datetime_utils import parse_day
from app.services.formatting import fmt_day_schedule, fmt_week_bookings
from app.services.scheduler import remove_reminder, schedule_reminder_if_needed
from app.states import AdminStates


router = Router(name="admin")


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id == config.admin_id


def _common_time_suggestions() -> list[str]:
    # Самые частые слоты (каждые 30 минут)
    times: list[str] = []
    for hour in range(9, 21):
        times.append(f"{hour:02d}:00")
        times.append(f"{hour:02d}:30")
    return times


@router.callback_query(F.data == "adm:manual_time")
async def admin_manual_time(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    if not _is_admin(call.from_user.id, config):
        await call.answer()
        return
    cur_state = await state.get_state()
    if cur_state != AdminStates.waiting_time.state:
        await call.answer()
        return
    await call.message.answer("Введите время в формате <code>HH:MM</code> (например, <code>12:30</code>):", parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu:admin")
async def menu_admin(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    if not _is_admin(call.from_user.id, config):
        await call.answer()
        return
    await state.clear()
    await call.message.edit_text("<b>Админ-панель</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(AdminCb.filter())
async def admin_actions(
    call: CallbackQuery,
    callback_data: AdminCb,
    state: FSMContext,
    config: Config,
    repo: Repo,
    scheduler: AsyncIOScheduler,
    bot: Bot,
) -> None:
    if not _is_admin(call.from_user.id, config):
        await call.answer()
        return

    action = callback_data.action
    await state.clear()
    await state.update_data(admin_action=action)

    if action in {"open_day", "close_day", "view_day", "add_slot", "del_slot"}:
        await state.set_state(AdminStates.waiting_day)
        min_d = today_fn() - timedelta(days=30)
        max_d = today_fn() + timedelta(days=365)
        open_days = set(await repo.list_open_days(format_day(min_d), format_day(max_d)))
        await state.update_data(adm_cal_y=today_fn().year, adm_cal_m=today_fn().month)
        await call.message.answer(
            "<b>Выберите дату</b> (можно и вручную <code>YYYY-MM-DD</code>):\n\n"
            "🟢 — день уже открыт\n"
            "⚪️ — день закрыт",
            parse_mode="HTML",
            reply_markup=admin_calendar_kb(today_fn().year, today_fn().month, min_d=min_d, max_d=max_d, open_days=open_days),
        )
        await call.answer()
        return

    if action == "cancel_booking":
        # Если в callback уже пришёл booking_id — сразу отменяем эту запись
        if callback_data.booking_id:
            booking_id = callback_data.booking_id
            b = await repo.get_booking(booking_id)
            if not b or b.status != "active":
                await call.message.answer("Активная запись с таким ID не найдена.", reply_markup=admin_menu_kb())
                await state.clear()
                await call.answer()
                return

            await repo.cancel_booking_by_id(booking_id)
            await remove_reminder(scheduler, repo, booking_id)
            try:
                await bot.send_message(
                    chat_id=b.user_id,
                    text=(
                        "<b>Ваша запись отменена мастером.</b>\n\n"
                        f"📅 <b>Дата:</b> {b.day}\n"
                        f"⏰ <b>Время:</b> {b.time}\n"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await call.message.answer(
                f"🗑 Запись <b>{booking_id}</b> отменена. Слот снова доступен.",
                parse_mode="HTML",
                reply_markup=admin_menu_kb(),
            )
            await state.clear()
            await call.answer()
            return

        # Иначе показываем список активных записей + ждём ввода ID вручную
        await state.set_state(AdminStates.waiting_booking_id)
        bookings = await repo.list_all_active_bookings(limit=50)
        if not bookings:
            await call.message.answer("Активных записей нет.", parse_mode="HTML", reply_markup=admin_menu_kb())
            await state.clear()
            await call.answer()
            return

        lines = ["<b>Активные записи (ID)</b>", ""]
        from app.services.formatting import h  # локальный импорт, чтобы не плодить зависимостей сверху

        for b in bookings:
            uname = (b.username or "").strip()
            uname_part = f" (@{h(uname)})" if uname else ""
            lines.append(
                f"🆔 <b>{b.id}</b> — {h(b.day)} {h(b.time)}\n"
                f"    {h(b.name)} ({h(b.phone)}) | <code>{b.user_id}</code>{uname_part}"
            )
        text = "\n".join(lines)

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from app.keyboards.callbacks import AdminCb as _AdminCbLocal

        kb = InlineKeyboardBuilder()
        for b in bookings:
            kb.button(
                text=f"ID {b.id} — {b.day} {b.time}",
                callback_data=_AdminCbLocal(action="cancel_booking", booking_id=b.id).pack(),
            )
        kb.adjust(1)
        kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))

        await call.message.answer(
            text + "\n\nИли введите <b>ID записи</b> вручную (число):",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        await call.answer()
        return

    if action == "view_week":
        # Текущая неделя (пн..вс)
        today = today_fn()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        start_day = format_day(monday)
        end_day = format_day(sunday)
        bookings = await repo.list_active_bookings_between(start_day, end_day)
        await call.message.answer(fmt_week_bookings(start_day, end_day, bookings), parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        await call.answer()
        return

    if action == "work_days":
        # Показываем открытые рабочие дни только на ближайшие 2 недели
        today = today_fn()
        start = today
        end = today + timedelta(days=14)
        start_day = format_day(start)
        end_day = format_day(end)
        days = await repo.list_open_days(start_day, end_day)
        if not days:
            text = (
                "<b>Рабочие дни</b>\n"
                f"{start_day} — {end_day}\n\n"
                "<i>Открытых дней нет.</i>"
            )
        else:
            joined = "\n".join(f"• {d}" for d in days)
            text = (
                "<b>Рабочие дни</b>\n"
                f"{start_day} — {end_day}\n\n"
                f"{joined}"
            )
        await call.message.answer(text, parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        await call.answer()
        return

    if action == "move_booking":
        # Если уже выбран booking_id (по кнопке) — сразу переходим к выбору новой даты
        if callback_data.booking_id:
            booking_id = callback_data.booking_id
            b = await repo.get_booking(booking_id)
            if not b or b.status != "active":
                await call.message.answer("Активная запись с таким ID не найдена.", reply_markup=admin_menu_kb())
                await state.clear()
                await call.answer()
                return

            await state.update_data(admin_action="move_booking", move_booking_id=booking_id)
            await state.set_state(AdminStates.waiting_day)
            min_d = today_fn() - timedelta(days=30)
            max_d = today_fn() + timedelta(days=365)
            open_days = set(await repo.list_open_days(format_day(min_d), format_day(max_d)))
            await call.message.answer(
                f"<b>Перенос записи ID {booking_id}</b>\n"
                f"Текущая дата: <b>{b.day}</b>, время: <b>{b.time}</b>\n\n"
                "Выберите <b>новую дату</b> (можно и вручную <code>YYYY-MM-DD</code>):\n"
                "🟢 — день уже открыт\n"
                "⚪️ — день закрыт",
                parse_mode="HTML",
                reply_markup=admin_calendar_kb(
                    today_fn().year,
                    today_fn().month,
                    min_d=min_d,
                    max_d=max_d,
                    open_days=open_days,
                ),
            )
            await call.answer()
            return

        # Иначе показываем список активных записей для выбора
        await state.set_state(AdminStates.waiting_booking_id)
        await state.update_data(admin_action="move_booking")
        bookings = await repo.list_all_active_bookings(limit=50)
        if not bookings:
            await call.message.answer("Активных записей нет.", parse_mode="HTML", reply_markup=admin_menu_kb())
            await state.clear()
            await call.answer()
            return

        lines = ["<b>Выберите запись для переноса</b>", ""]
        from app.services.formatting import h  # локальный импорт

        for b in bookings:
            uname = (b.username or "").strip()
            uname_part = f" (@{h(uname)})" if uname else ""
            lines.append(
                f"🆔 <b>{b.id}</b> — {h(b.day)} {h(b.time)}\n"
                f"    {h(b.name)} ({h(b.phone)}) | <code>{b.user_id}</code>{uname_part}"
            )
        text = "\n".join(lines)

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from app.keyboards.callbacks import AdminCb as _AdminCbLocal

        kb = InlineKeyboardBuilder()
        for b in bookings:
            kb.button(
                text=f"ID {b.id} — {b.day} {b.time}",
                callback_data=_AdminCbLocal(action="move_booking", booking_id=b.id).pack(),
            )
        kb.adjust(1)
        kb.row(InlineKeyboardButton(text="🏠 В меню", callback_data="menu:home"))

        await call.message.answer(
            text + "\n\nИли введите <b>ID записи</b> вручную (число):",
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )
        await call.answer()
        return

    await call.answer()


@router.message(AdminStates.waiting_day)
async def admin_enter_day(
    message: Message,
    state: FSMContext,
    bot: Bot,
    repo: Repo,
    scheduler: AsyncIOScheduler,
) -> None:
    day_str = (message.text or "").strip()
    try:
        d = parse_day(day_str)
        day_str = d.strftime("%Y-%m-%d")
    except Exception:
        await message.answer("Неверная дата. Пример: <code>2026-03-12</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    action = data.get("admin_action")

    if action == "open_day":
        await repo.open_day(day_str)
        await message.answer(f"✅ День <b>{day_str}</b> открыт.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action == "close_day":
        # Снимаем напоминания по активным записям этого дня
        booking_ids = await repo.list_active_booking_ids_by_day(day_str)
        await repo.close_day(day_str)
        for bid in booking_ids:
            await remove_reminder(scheduler, repo, bid)
            b = await repo.get_booking(bid)
            if b:
                try:
                    await bot.send_message(
                        chat_id=b.user_id,
                        text=(
                            "<b>Ваша запись отменена мастером.</b>\n\n"
                            f"📅 <b>Дата:</b> {b.day}\n"
                            f"⏰ <b>Время:</b> {b.time}\n"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        await message.answer(
            f"🚫 День <b>{day_str}</b> закрыт. Активные записи отменены: <b>{len(booking_ids)}</b>.",
            parse_mode="HTML",
            reply_markup=admin_menu_kb(),
        )
        await state.clear()
        return

    if action == "view_day":
        slots = await repo.list_all_slots_with_status(day_str)
        await message.answer(fmt_day_schedule(day_str, slots), parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action in {"add_slot", "del_slot"}:
        await state.update_data(day=day_str)
        await state.set_state(AdminStates.waiting_time)
        await message.answer(
            "Введите время в формате <code>HH:MM</code> (например, <code>12:30</code>)\n"
            "или выберите из предложенных:",
            parse_mode="HTML",
            reply_markup=admin_time_suggestions_kb(_common_time_suggestions()),
        )
        return

    if action == "move_booking":
        # Для переноса показываем только реально свободные слоты
        free_times = await repo.list_free_times(day_str)
        if not free_times:
            await message.answer(
                "На эту дату нет свободных слотов для переноса. Выберите другой день.",
                parse_mode="HTML",
                reply_markup=admin_menu_kb(),
            )
            await state.clear()
            return

        await state.update_data(day=day_str)
        await state.set_state(AdminStates.waiting_time)
        await message.answer(
            f"Новая дата: <b>{day_str}</b>\n\n"
            "Выберите доступное время для переноса:",
            parse_mode="HTML",
            reply_markup=admin_time_suggestions_kb(free_times),
        )
        return

    await message.answer("Неизвестное действие.", reply_markup=admin_menu_kb())
    await state.clear()


@router.message(AdminStates.waiting_time)
async def admin_enter_time(message: Message, state: FSMContext, bot: Bot, repo: Repo, scheduler: AsyncIOScheduler) -> None:
    time_str = (message.text or "").strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except Exception:
        await message.answer("Неверное время. Пример: <code>10:00</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    action = data.get("admin_action")
    day = data.get("day")
    if not day:
        await message.answer("Дата не найдена. Начните заново.", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action == "add_slot":
        await repo.add_slot(day, time_str)
        await message.answer(f"✅ Слот <b>{day} {time_str}</b> добавлен/включён.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action == "del_slot":
        booking_id = await repo.get_active_booking_id_by_slot(day, time_str)
        await repo.remove_slot(day, time_str)
        if booking_id:
            await remove_reminder(scheduler, repo, booking_id)
            b = await repo.get_booking(booking_id)
            if b:
                try:
                    await bot.send_message(
                        chat_id=b.user_id,
                        text=(
                            "<b>Ваша запись отменена мастером.</b>\n\n"
                            f"📅 <b>Дата:</b> {b.day}\n"
                            f"⏰ <b>Время:</b> {b.time}\n"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        await message.answer(f"➖ Слот <b>{day} {time_str}</b> выключен.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action == "move_booking":
        booking_id = data.get("move_booking_id")
        if not booking_id:
            await message.answer("ID записи не найден. Начните заново.", reply_markup=admin_menu_kb())
            await state.clear()
            return
        try:
            await repo.move_booking(booking_id, day, time_str)
        except ValueError as e:
            await message.answer(
                f"Не удалось перенести запись: {e}", reply_markup=admin_menu_kb()
            )
            await state.clear()
            return

        b = await repo.get_booking(booking_id)
        if not b:
            await message.answer("Запись не найдена после переноса.", reply_markup=admin_menu_kb())
            await state.clear()
            return

        # Обновляем напоминание
        await remove_reminder(scheduler, repo, booking_id)
        try:
            await schedule_reminder_if_needed(scheduler, repo, bot, b)
        except Exception:
            # если не получилось — просто продолжаем, запись уже перенесена
            pass

        # Уведомляем клиента
        try:
            await bot.send_message(
                chat_id=b.user_id,
                text=(
                    "<b>Ваша запись перенесена администратором.</b>\n\n"
                    f"📅 <b>Новая дата:</b> {b.day}\n"
                    f"⏰ <b>Новое время:</b> {b.time}\n"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await message.answer(
            f"🔁 Запись <b>{booking_id}</b> перенесена на <b>{b.day} {b.time}</b>.",
            parse_mode="HTML",
            reply_markup=admin_menu_kb(),
        )
        await state.clear()
        return

    await message.answer("Неизвестное действие.", reply_markup=admin_menu_kb())
    await state.clear()


@router.message(AdminStates.waiting_booking_id)
async def admin_cancel_by_id(message: Message, state: FSMContext, bot: Bot, repo: Repo, scheduler: AsyncIOScheduler) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Введите число (ID записи).")
        return
    booking_id = int(raw)
    b = await repo.get_booking(booking_id)
    if not b or b.status != "active":
        await message.answer("Активная запись с таким ID не найдена.", reply_markup=admin_menu_kb())
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("admin_action")

    if action == "cancel_booking":
        await repo.cancel_booking_by_id(booking_id)
        await remove_reminder(scheduler, repo, booking_id)
        try:
            await bot.send_message(
                chat_id=b.user_id,
                text=(
                    "<b>Ваша запись отменена мастером.</b>\n\n"
                    f"📅 <b>Дата:</b> {b.day}\n"
                    f"⏰ <b>Время:</b> {b.time}\n"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await message.answer(f"🗑 Запись <b>{booking_id}</b> отменена. Слот снова доступен.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        return

    if action == "move_booking":
        # Сохраняем выбранный ID и переходим к выбору новой даты
        await state.update_data(move_booking_id=booking_id, admin_action="move_booking")
        await state.set_state(AdminStates.waiting_day)
        min_d = today_fn() - timedelta(days=30)
        max_d = today_fn() + timedelta(days=365)
        open_days = set(await repo.list_open_days(format_day(min_d), format_day(max_d)))
        await message.answer(
            f"<b>Перенос записи ID {booking_id}</b>\n"
            f"Текущая дата: <b>{b.day}</b>, время: <b>{b.time}</b>\n\n"
            "Выберите <b>новую дату</b> (можно и вручную <code>YYYY-MM-DD</code>):\n"
            "🟢 — день уже открыт\n"
            "⚪️ — день закрыт",
            parse_mode="HTML",
            reply_markup=admin_calendar_kb(
                today_fn().year,
                today_fn().month,
                min_d=min_d,
                max_d=max_d,
                open_days=open_days,
            ),
        )
        return

    await message.answer("Неизвестное действие.", reply_markup=admin_menu_kb())
    await state.clear()




@router.message(F.text == "/admin")
async def admin_cmd(message: Message, state: FSMContext, config: Config) -> None:
    if not _is_admin(message.from_user.id, config):
        return
    await state.clear()
    await message.answer("<b>Админ-панель</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.callback_query(AdminCalCb.filter())
async def admin_calendar_actions(call: CallbackQuery, callback_data: AdminCalCb, state: FSMContext, bot: Bot, repo: Repo, scheduler: AsyncIOScheduler, config: Config) -> None:
    if not _is_admin(call.from_user.id, config):
        await call.answer()
        return

    cur_state = await state.get_state()
    if cur_state != AdminStates.waiting_day.state:
        await call.answer()
        return

    min_d = today_fn() - timedelta(days=30)
    max_d = today_fn() + timedelta(days=365)

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

        # Ограничим диапазоном календаря
        min_first = date(min_d.year, min_d.month, 1)
        max_first = date(max_d.year, max_d.month, 1)
        new_first = date(y, m, 1)
        if new_first < min_first:
            y, m = min_first.year, min_first.month
        if new_first > max_first:
            y, m = max_first.year, max_first.month

        await state.update_data(adm_cal_y=y, adm_cal_m=m)
        open_days = set(await repo.list_open_days(format_day(min_d), format_day(max_d)))
        try:
            await call.message.edit_reply_markup(
                reply_markup=admin_calendar_kb(y, m, min_d=min_d, max_d=max_d, open_days=open_days)
            )
        except Exception:
            # fallback: если нельзя отредактировать — отправим новое
            await call.message.answer(reply_markup=admin_calendar_kb(y, m, min_d=min_d, max_d=max_d))
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

        # Просто запускаем ту же логику, что и при ручном вводе даты
        await call.answer()
        # Попросим админа ввести время/получить результат через обычный обработчик:
        # проще — напрямую выполнить часть логики, дублируя минимально.
        day_str = format_day(d)
        data = await state.get_data()
        action = data.get("admin_action")

        if action == "open_day":
            await repo.open_day(day_str)
            await call.message.answer(f"✅ День <b>{day_str}</b> открыт.", parse_mode="HTML", reply_markup=admin_menu_kb())
            await state.clear()
            return

        if action == "close_day":
            booking_ids = await repo.list_active_booking_ids_by_day(day_str)
            await repo.close_day(day_str)
            for bid in booking_ids:
                await remove_reminder(scheduler, repo, bid)
                b = await repo.get_booking(bid)
                if b:
                    try:
                        await bot.send_message(
                            chat_id=b.user_id,
                            text=(
                                "<b>Ваша запись отменена мастером.</b>\n\n"
                                f"📅 <b>Дата:</b> {b.day}\n"
                                f"⏰ <b>Время:</b> {b.time}\n"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            await call.message.answer(
                f"🚫 День <b>{day_str}</b> закрыт. Активные записи отменены: <b>{len(booking_ids)}</b>.",
                parse_mode="HTML",
                reply_markup=admin_menu_kb(),
            )
            await state.clear()
            return

        if action == "view_day":
            slots = await repo.list_all_slots_with_status(day_str)
            await call.message.answer(fmt_day_schedule(day_str, slots), parse_mode="HTML", reply_markup=admin_menu_kb())
            await state.clear()
            return

        if action in {"add_slot", "del_slot"}:
            await state.update_data(day=day_str)
            await state.set_state(AdminStates.waiting_time)
            await call.message.answer(
                f"Дата выбрана: <b>{day_str}</b>\n\n"
                "Введите время в формате <code>HH:MM</code> или выберите из предложенных:",
                parse_mode="HTML",
                reply_markup=admin_time_suggestions_kb(_common_time_suggestions()),
            )
            return

        if action == "move_booking":
            # Для переноса показываем только реально свободные слоты
            free_times = await repo.list_free_times(day_str)
            if not free_times:
                await call.message.answer(
                    "На эту дату нет свободных слотов для переноса. Выберите другой день.",
                    parse_mode="HTML",
                    reply_markup=admin_menu_kb(),
                )
                await state.clear()
                await call.answer()
                return

            await state.update_data(day=day_str)
            await state.set_state(AdminStates.waiting_time)
            await call.message.answer(
                f"Новая дата: <b>{day_str}</b>\n\n"
                "Выберите доступное время для переноса:",
                parse_mode="HTML",
                reply_markup=admin_time_suggestions_kb(free_times),
            )
            return


@router.callback_query(AdminTimeCb.filter())
async def admin_time_pick(call: CallbackQuery, callback_data: AdminTimeCb, state: FSMContext, bot: Bot, repo: Repo, scheduler: AsyncIOScheduler, config: Config) -> None:
    if not _is_admin(call.from_user.id, config):
        await call.answer()
        return

    cur_state = await state.get_state()
    if cur_state != AdminStates.waiting_time.state:
        await call.answer()
        return

    time_str = callback_data.time.replace("-", ":")
    try:
        datetime.strptime(time_str, "%H:%M")
    except Exception:
        await call.answer("Неверное время", show_alert=True)
        return

    data = await state.get_data()
    action = data.get("admin_action")
    day = data.get("day")
    if not day:
        await call.message.answer("Дата не найдена. Начните заново.", reply_markup=admin_menu_kb())
        await state.clear()
        await call.answer()
        return

    if action == "add_slot":
        await repo.add_slot(day, time_str)
        await call.message.answer(f"✅ Слот <b>{day} {time_str}</b> добавлен/включён.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        await call.answer()
        return

    if action == "del_slot":
        booking_id = await repo.get_active_booking_id_by_slot(day, time_str)
        await repo.remove_slot(day, time_str)
        if booking_id:
            await remove_reminder(scheduler, repo, booking_id)
            b = await repo.get_booking(booking_id)
            if b:
                try:
                    await bot.send_message(
                        chat_id=b.user_id,
                        text=(
                            "<b>Ваша запись отменена мастером.</b>\n\n"
                            f"📅 <b>Дата:</b> {b.day}\n"
                            f"⏰ <b>Время:</b> {b.time}\n"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        await call.message.answer(f"➖ Слот <b>{day} {time_str}</b> выключен.", parse_mode="HTML", reply_markup=admin_menu_kb())
        await state.clear()
        await call.answer()
        return

    if action == "move_booking":
        booking_id = data.get("move_booking_id")
        if not booking_id:
            await call.message.answer("ID записи не найден. Начните заново.", reply_markup=admin_menu_kb())
            await state.clear()
            await call.answer()
            return
        try:
            await repo.move_booking(booking_id, day, time_str)
        except ValueError as e:
            await call.message.answer(
                f"Не удалось перенести запись: {e}", reply_markup=admin_menu_kb()
            )
            await state.clear()
            await call.answer()
            return

        b = await repo.get_booking(booking_id)
        if not b:
            await call.message.answer("Запись не найдена после переноса.", reply_markup=admin_menu_kb())
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
                    "<b>Ваша запись перенесена администратором.</b>\n\n"
                    f"📅 <b>Новая дата:</b> {b.day}\n"
                    f"⏰ <b>Новое время:</b> {b.time}\n"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await call.message.answer(
            f"🔁 Запись <b>{booking_id}</b> перенесена на <b>{b.day} {b.time}</b>.",
            parse_mode="HTML",
            reply_markup=admin_menu_kb(),
        )
        await state.clear()
        await call.answer()
        return

    await call.answer()

