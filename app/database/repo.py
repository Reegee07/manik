from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

import aiosqlite


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    day: str  # YYYY-MM-DD
    time: str  # HH:MM
    name: str
    phone: str
    status: str


@dataclass(frozen=True)
class BookingWithUser:
    id: int
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    day: str
    time: str
    name: str
    phone: str


class Repo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    # ---- Users
    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> None:
        await self.conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              username=excluded.username,
              first_name=excluded.first_name,
              last_name=excluded.last_name;
            """,
            (user_id, username, first_name, last_name),
        )
        await self.conn.commit()

    # ---- Work days
    async def open_day(self, day: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO work_days(day, is_open) VALUES(?, 1)
            ON CONFLICT(day) DO UPDATE SET is_open=1;
            """,
            (day,),
        )
        await self.conn.commit()

    async def close_day(self, day: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO work_days(day, is_open) VALUES(?, 0)
            ON CONFLICT(day) DO UPDATE SET is_open=0;
            """,
            (day,),
        )
        # деактивируем все слоты в этот день
        await self.conn.execute("UPDATE slots SET is_active=0 WHERE day=?;", (day,))
        # отменяем активные записи этого дня
        await self.conn.execute(
            "UPDATE bookings SET status='cancelled', cancelled_at=datetime('now') WHERE day=? AND status='active';",
            (day,),
        )
        await self.conn.commit()

    async def list_active_booking_ids_by_day(self, day: str) -> list[int]:
        cur = await self.conn.execute(
            "SELECT id FROM bookings WHERE day=? AND status='active';",
            (day,),
        )
        rows = await cur.fetchall()
        return [int(r["id"]) for r in rows]

    async def get_active_booking_id_by_slot(self, day: str, time: str) -> int | None:
        cur = await self.conn.execute(
            "SELECT id FROM bookings WHERE day=? AND time=? AND status='active' LIMIT 1;",
            (day, time),
        )
        row = await cur.fetchone()
        return int(row["id"]) if row else None

    async def is_day_open(self, day: str) -> bool:
        cur = await self.conn.execute("SELECT is_open FROM work_days WHERE day=?;", (day,))
        row = await cur.fetchone()
        return bool(row["is_open"]) if row else False

    async def list_open_days_with_free_slots(self, start_day: str, end_day: str) -> list[str]:
        """
        Возвращает дни, которые:
        - открыты
        - и имеют хотя бы один активный слот без активной записи
        """
        cur = await self.conn.execute(
            """
            SELECT wd.day
            FROM work_days wd
            WHERE wd.day BETWEEN ? AND ?
              AND wd.is_open=1
              AND EXISTS (
                SELECT 1
                FROM slots s
                LEFT JOIN bookings b
                  ON b.day=s.day AND b.time=s.time AND b.status='active'
                WHERE s.day=wd.day AND s.is_active=1 AND b.id IS NULL
              )
            ORDER BY wd.day;
            """,
            (start_day, end_day),
        )
        rows = await cur.fetchall()
        return [r["day"] for r in rows]

    async def list_open_days(self, start_day: str, end_day: str) -> list[str]:
        """
        Возвращает все открытые рабочие дни в диапазоне (независимо от слотов).
        """
        cur = await self.conn.execute(
            """
            SELECT day
            FROM work_days
            WHERE day BETWEEN ? AND ?
              AND is_open=1
            ORDER BY day;
            """,
            (start_day, end_day),
        )
        rows = await cur.fetchall()
        return [r["day"] for r in rows]

    # ---- Slots
    async def add_slot(self, day: str, time: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO work_days(day, is_open) VALUES(?, 1)
            ON CONFLICT(day) DO NOTHING;
            """,
            (day,),
        )
        await self.conn.execute(
            """
            INSERT INTO slots(day, time, is_active) VALUES(?, ?, 1)
            ON CONFLICT(day, time) DO UPDATE SET is_active=1;
            """,
            (day, time),
        )
        await self.conn.commit()

    async def remove_slot(self, day: str, time: str) -> None:
        await self.conn.execute(
            "UPDATE slots SET is_active=0 WHERE day=? AND time=?;",
            (day, time),
        )
        # если на этом слоте была активная запись — отменяем
        await self.conn.execute(
            """
            UPDATE bookings
            SET status='cancelled', cancelled_at=datetime('now')
            WHERE day=? AND time=? AND status='active';
            """,
            (day, time),
        )
        await self.conn.commit()

    async def list_free_times(self, day: str) -> list[str]:
        cur = await self.conn.execute(
            """
            SELECT s.time
            FROM slots s
            LEFT JOIN bookings b
              ON b.day=s.day AND b.time=s.time AND b.status='active'
            WHERE s.day=? AND s.is_active=1 AND b.id IS NULL
            ORDER BY s.time;
            """,
            (day,),
        )
        rows = await cur.fetchall()
        return [r["time"] for r in rows]

    async def list_all_slots_with_status(self, day: str) -> list[tuple[str, str]]:
        """
        Возвращает список (time, status): free/booked/inactive
        """
        cur = await self.conn.execute(
            """
            SELECT s.time,
                   CASE
                     WHEN s.is_active=0 THEN 'inactive'
                     WHEN EXISTS (
                       SELECT 1 FROM bookings b
                       WHERE b.day=s.day AND b.time=s.time AND b.status='active'
                     ) THEN 'booked'
                     ELSE 'free'
                   END AS st
            FROM slots s
            WHERE s.day=?
            ORDER BY s.time;
            """,
            (day,),
        )
        rows = await cur.fetchall()
        return [(r["time"], r["st"]) for r in rows]

    # ---- Bookings
    async def get_active_booking_by_user(self, user_id: int) -> Booking | None:
        cur = await self.conn.execute(
            """
            SELECT id, user_id, day, time, name, phone, status
            FROM bookings
            WHERE user_id=? AND status='active'
            ORDER BY id DESC
            LIMIT 1;
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return Booking(**dict(row))

    async def create_booking(self, user_id: int, day: str, time: str, name: str, phone: str) -> int:
        """
        Создает запись. Важно:
        - пользователь не должен иметь активных записей
        - слот должен быть свободен и активен
        """
        # Транзакция: блокируем запись на время проверки/вставки,
        # чтобы два клиента не заняли один и тот же слот одновременно.
        await self.conn.execute("BEGIN IMMEDIATE;")
        try:
            existing = await self.get_active_booking_by_user(user_id)
            if existing:
                raise ValueError("User already has an active booking")

            # проверка: день открыт
            if not await self.is_day_open(day):
                raise ValueError("Day is closed")

            # проверка: слот активен и свободен
            cur = await self.conn.execute(
                """
                SELECT s.id
                FROM slots s
                LEFT JOIN bookings b
                  ON b.day=s.day AND b.time=s.time AND b.status='active'
                WHERE s.day=? AND s.time=? AND s.is_active=1 AND b.id IS NULL
                LIMIT 1;
                """,
                (day, time),
            )
            row = await cur.fetchone()
            if not row:
                raise ValueError("Slot is not available")

            cur2 = await self.conn.execute(
                """
                INSERT INTO bookings(user_id, day, time, name, phone, status)
                VALUES(?, ?, ?, ?, ?, 'active');
                """,
                (user_id, day, time, name, phone),
            )
            await self.conn.commit()
            return int(cur2.lastrowid)
        except Exception:
            await self.conn.rollback()
            raise

    async def cancel_booking_by_id(self, booking_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE bookings
            SET status='cancelled', cancelled_at=datetime('now')
            WHERE id=? AND status='active';
            """,
            (booking_id,),
        )
        await self.conn.commit()

    async def cancel_booking_by_user(self, user_id: int) -> int | None:
        booking = await self.get_active_booking_by_user(user_id)
        if not booking:
            return None
        await self.cancel_booking_by_id(booking.id)
        return booking.id

    async def get_booking(self, booking_id: int) -> Booking | None:
        cur = await self.conn.execute(
            """
            SELECT id, user_id, day, time, name, phone, status
            FROM bookings
            WHERE id=?;
            """,
            (booking_id,),
        )
        row = await cur.fetchone()
        return Booking(**dict(row)) if row else None

    async def move_booking(self, booking_id: int, new_day: str, new_time: str) -> None:
        """
        Переносит активную запись на другой день/время.
        Проверяет, что день открыт и новый слот свободен и активен.
        """
        await self.conn.execute("BEGIN IMMEDIATE;")
        try:
            cur = await self.conn.execute(
                """
                SELECT id, user_id, day, time, name, phone, status
                FROM bookings
                WHERE id=?;
                """,
                (booking_id,),
            )
            row = await cur.fetchone()
            if not row:
                raise ValueError("Booking not found")
            if row["status"] != "active":
                raise ValueError("Booking is not active")

            # проверка: день открыт
            if not await self.is_day_open(new_day):
                raise ValueError("Day is closed")

            # проверка: новый слот активен и свободен
            cur2 = await self.conn.execute(
                """
                SELECT s.id
                FROM slots s
                LEFT JOIN bookings b
                  ON b.day=s.day AND b.time=s.time AND b.status='active'
                WHERE s.day=? AND s.time=? AND s.is_active=1 AND b.id IS NULL
                LIMIT 1;
                """,
                (new_day, new_time),
            )
            row2 = await cur2.fetchone()
            if not row2:
                raise ValueError("Slot is not available")

            await self.conn.execute(
                """
                UPDATE bookings
                SET day=?, time=?
                WHERE id=?;
                """,
                (new_day, new_time, booking_id),
            )
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise

    async def list_active_bookings_from_now(self) -> list[Booking]:
        """
        Возвращает активные записи, которые еще не прошли (для восстановления напоминаний).
        Сравнение делается по (day,time) >= now().
        """
        cur = await self.conn.execute(
            """
            SELECT id, user_id, day, time, name, phone, status
            FROM bookings
            WHERE status='active'
              AND datetime(day || ' ' || time) >= datetime('now')
            ORDER BY day, time;
            """
        )
        rows = await cur.fetchall()
        return [Booking(**dict(r)) for r in rows]

    async def list_active_bookings_between(self, start_day: str, end_day: str) -> list[BookingWithUser]:
        """
        Возвращает активные записи в диапазоне дней (включительно) с данными пользователя.
        """
        cur = await self.conn.execute(
            """
            SELECT b.id,
                   b.user_id,
                   u.username,
                   u.first_name,
                   u.last_name,
                   b.day,
                   b.time,
                   b.name,
                   b.phone
            FROM bookings b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.status='active'
              AND b.day BETWEEN ? AND ?
            ORDER BY b.day, b.time, b.id;
            """,
            (start_day, end_day),
        )
        rows = await cur.fetchall()
        return [BookingWithUser(**dict(r)) for r in rows]

    async def list_all_active_bookings(self, limit: int = 50) -> list[BookingWithUser]:
        """
        Возвращает все активные записи (до limit штук) с данными пользователя.
        """
        cur = await self.conn.execute(
            """
            SELECT b.id,
                   b.user_id,
                   u.username,
                   u.first_name,
                   u.last_name,
                   b.day,
                   b.time,
                   b.name,
                   b.phone
            FROM bookings b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.status='active'
            ORDER BY b.day, b.time, b.id
            LIMIT ?;
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return [BookingWithUser(**dict(r)) for r in rows]

    # ---- Reminders
    async def upsert_reminder(self, booking_id: int, job_id: str, run_at_iso: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO reminders(booking_id, job_id, run_at)
            VALUES(?, ?, ?)
            ON CONFLICT(booking_id) DO UPDATE SET job_id=excluded.job_id, run_at=excluded.run_at;
            """,
            (booking_id, job_id, run_at_iso),
        )
        await self.conn.commit()

    async def delete_reminder(self, booking_id: int) -> None:
        await self.conn.execute("DELETE FROM reminders WHERE booking_id=?;", (booking_id,))
        await self.conn.commit()

    async def get_reminder_job_id(self, booking_id: int) -> str | None:
        cur = await self.conn.execute("SELECT job_id FROM reminders WHERE booking_id=?;", (booking_id,))
        row = await cur.fetchone()
        return row["job_id"] if row else None

