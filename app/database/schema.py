from __future__ import annotations

import aiosqlite


async def init_db(conn: aiosqlite.Connection) -> None:
    # Пользователи (для удобства, не обязательно)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_name   TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    # Рабочие дни (день может быть открыт/закрыт полностью)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_days (
            day         TEXT PRIMARY KEY, -- YYYY-MM-DD
            is_open     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    # Слоты на конкретный день
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS slots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day         TEXT NOT NULL, -- YYYY-MM-DD
            time        TEXT NOT NULL, -- HH:MM
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(day, time),
            FOREIGN KEY(day) REFERENCES work_days(day) ON DELETE CASCADE
        );
        """
    )

    # Записи клиентов
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            day         TEXT NOT NULL,
            time        TEXT NOT NULL,
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active', -- active/cancelled
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            cancelled_at TEXT
            -- уникальность для "активных" обеспечиваем частичным индексом ниже
        );
        """
    )

    # Один слот может иметь только одну активную запись (отменённые записи не мешают)
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_slot
        ON bookings(day, time)
        WHERE status='active';
        """
    )

    # Напоминания (job_id хранится, чтобы уметь снимать и восстанавливать)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            booking_id  INTEGER PRIMARY KEY,
            job_id      TEXT NOT NULL,
            run_at      TEXT NOT NULL, -- ISO datetime
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        );
        """
    )

    await conn.commit()

