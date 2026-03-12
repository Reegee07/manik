from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.config import Config
from app.database.repo import Repo
from app.keyboards.common import bottom_menu_kb, main_menu_kb, portfolio_kb


router = Router(name="start_menu")


WELCOME_TEXT = (
    "<b>Привет!</b>\n\n"
    "Здесь можно записаться на маникюр: выберите дату и время, оставьте имя и номер телефона.\n"
    "Все действия выполняются через кнопки.\n\n"
    "Для связи с мастером: <b>@xwqeee</b> 💖✨"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, config: Config, repo: Repo) -> None:
    await state.clear()
    u = message.from_user
    if u:
        await repo.upsert_user(u.id, u.username, u.first_name, u.last_name)
    is_admin = bool(u and u.id == config.admin_id)
    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu_kb(is_admin=is_admin),
        parse_mode="HTML",
    )
    await message.answer(
        "Кнопки быстрого доступа снизу 👇",
        reply_markup=bottom_menu_kb(is_admin=is_admin),
    )


@router.message(F.text == "🏠 Меню")
async def bottom_menu_home(message: Message, state: FSMContext, config: Config, repo: Repo) -> None:
    await state.clear()
    u = message.from_user
    if u:
        await repo.upsert_user(u.id, u.username, u.first_name, u.last_name)
    is_admin = bool(u and u.id == config.admin_id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")


@router.message(F.text == "🧾 Моя запись")
async def bottom_menu_my_booking(message: Message, repo: Repo) -> None:
    u = message.from_user
    if not u:
        return
    b = await repo.get_active_booking_by_user(u.id)
    if not b:
        await message.answer("У вас нет активной записи.")
        return
    from app.services.formatting import fmt_booking_for_user

    await message.answer(fmt_booking_for_user(b.day, b.time), parse_mode="HTML")


@router.message(F.text == "⚙️ Админ-меню")
async def bottom_menu_admin(message: Message, state: FSMContext, config: Config) -> None:
    u = message.from_user
    if not u or u.id != config.admin_id:
        return
    await state.clear()
    from app.keyboards.common import admin_menu_kb

    await message.answer("<b>Админ-панель</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu:home")
async def menu_home(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.clear()
    u = call.from_user
    is_admin = bool(u and u.id == config.admin_id)
    await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu:prices")
async def menu_prices(call: CallbackQuery) -> None:
    # Без FSM по требованию
    text = "<b>Прайсы</b>\n\nФренч — <b>1000₽</b>\nКвадрат — <b>500₽</b>"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu:portfolio")
async def menu_portfolio(call: CallbackQuery) -> None:
    await call.message.answer("<b>Портфолио</b>\nНажмите кнопку ниже:", reply_markup=portfolio_kb(), parse_mode="HTML")
    await call.answer()

