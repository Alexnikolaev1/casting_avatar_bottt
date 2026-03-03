"""
Модуль работы с базой данных PostgreSQL.
Использует asyncpg для асинхронных запросов.
"""

import asyncpg
import secrets
import logging
from typing import Optional
from bot.config import config

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            config.DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────────
# Инициализация схемы
# ─────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    telegram_id         BIGINT UNIQUE NOT NULL,
    username            TEXT,
    first_name          TEXT,
    last_name           TEXT,
    referral_code       TEXT UNIQUE NOT NULL,
    referred_by         BIGINT,
    free_generations    INTEGER NOT NULL DEFAULT 2,
    total_spent         INTEGER NOT NULL DEFAULT 0,   -- в копейках
    is_banned           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generations (
    id                  SERIAL PRIMARY KEY,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_id),
    style_id            TEXT NOT NULL,
    source_photo_url    TEXT NOT NULL,
    result_photo_url    TEXT,
    operation_id        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    -- pending | processing | completed | failed
    error_message       TEXT,
    is_pack             BOOLEAN NOT NULL DEFAULT FALSE,
    pack_id             INTEGER,   -- ссылка на родительскую генерацию (для пакетов)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS payments (
    id                  SERIAL PRIMARY KEY,
    payment_id          TEXT UNIQUE NOT NULL,
    user_id             BIGINT NOT NULL REFERENCES users(telegram_id),
    generation_ids      INTEGER[] NOT NULL DEFAULT '{}',
    amount              INTEGER NOT NULL,   -- в копейках
    status              TEXT NOT NULL DEFAULT 'pending',
    -- pending | succeeded | canceled | refunded
    style_id            TEXT,
    is_pack             BOOLEAN NOT NULL DEFAULT FALSE,
    idempotence_key     TEXT UNIQUE NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_generations_user_id ON generations(user_id);
CREATE INDEX IF NOT EXISTS idx_generations_status ON generations(status);
CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
"""


async def init_db():
    """Создаёт таблицы если их нет."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Database initialized")


# ─────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────

async def get_or_create_user(
    telegram_id: int,
    username: str = None,
    first_name: str = None,
    last_name: str = None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1", telegram_id
        )
        if not user:
            ref_code = secrets.token_urlsafe(8)
            user = await conn.fetchrow(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, referral_code, free_generations)
                VALUES ($1, $2, $3, $4, $5, 2)
                RETURNING *
                """,
                telegram_id, username, first_name, last_name, ref_code,
            )
        else:
            # Обновляем last_seen и данные пользователя
            user = await conn.fetchrow(
                """
                UPDATE users
                SET last_seen = NOW(),
                    username = COALESCE($2, username),
                    first_name = COALESCE($3, first_name),
                    last_name = COALESCE($4, last_name)
                WHERE telegram_id = $1
                RETURNING *
                """,
                telegram_id, username, first_name, last_name,
            )
        return dict(user)


async def get_user(telegram_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return dict(row) if row else None


async def get_user_by_ref_code(ref_code: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE referral_code = $1", ref_code
        )
        return dict(row) if row else None


async def add_free_generation(telegram_id: int, count: int = 1):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET free_generations = free_generations + $2 WHERE telegram_id = $1",
            telegram_id, count,
        )


async def use_free_generation(telegram_id: int) -> bool:
    """Списывает одну бесплатную генерацию. Возвращает True если успешно."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            UPDATE users
            SET free_generations = free_generations - 1
            WHERE telegram_id = $1 AND free_generations > 0
            RETURNING free_generations
            """,
            telegram_id,
        )
        return result is not None


async def set_referred_by(telegram_id: int, referrer_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users SET referred_by = $2
            WHERE telegram_id = $1 AND referred_by IS NULL
            """,
            telegram_id, referrer_id,
        )


async def add_total_spent(telegram_id: int, amount: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET total_spent = total_spent + $2 WHERE telegram_id = $1",
            telegram_id, amount,
        )


async def is_user_banned(telegram_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_banned FROM users WHERE telegram_id = $1", telegram_id
        )
        return row['is_banned'] if row else False


async def ban_user(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned = TRUE WHERE telegram_id = $1", telegram_id
        )


# ─────────────────────────────────────────────
# Generations
# ─────────────────────────────────────────────

async def create_generation(
    user_id: int,
    style_id: str,
    photo_url: str,
    is_pack: bool = False,
    pack_id: int = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO generations (user_id, style_id, source_photo_url, is_pack, pack_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id, style_id, photo_url, is_pack, pack_id,
        )
        return row['id']


async def get_generation(generation_id: int) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM generations WHERE id = $1", generation_id
        )
        return dict(row) if row else None


async def update_generation(
    generation_id: int,
    status: str,
    operation_id: str = None,
    result_url: str = None,
    error_message: str = None,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE generations
            SET status = $2,
                operation_id = COALESCE($3, operation_id),
                result_photo_url = COALESCE($4, result_photo_url),
                error_message = COALESCE($5, error_message),
                completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN NOW() ELSE completed_at END
            WHERE id = $1
            """,
            generation_id, status, operation_id, result_url, error_message,
        )


async def get_user_generations(user_id: int, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM generations
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [dict(r) for r in rows]


async def get_pending_generations(limit: int = 5) -> list[dict]:
    """Для воркера — достаёт задачи в очереди."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM generations
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# Payments
# ─────────────────────────────────────────────

async def create_payment(
    payment_id: str,
    user_id: int,
    generation_ids: list[int],
    amount: int,
    style_id: str,
    is_pack: bool,
    idempotence_key: str,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO payments
                (payment_id, user_id, generation_ids, amount, style_id, is_pack, idempotence_key)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            payment_id, user_id, generation_ids, amount, style_id, is_pack, idempotence_key,
        )
        return row['id']


async def get_payment(payment_id: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_id = $1", payment_id
        )
        return dict(row) if row else None


async def update_payment_status(payment_id: str, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payments SET status = $2, updated_at = NOW() WHERE payment_id = $1",
            payment_id, status,
        )


# ─────────────────────────────────────────────
# Статистика для администраторов
# ─────────────────────────────────────────────

async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_generations = await conn.fetchval("SELECT COUNT(*) FROM generations")
        completed = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE status = 'completed'"
        )
        total_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'succeeded'"
        )
        today_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '24 hours'"
        )
        today_payments = await conn.fetchval(
            "SELECT COUNT(*) FROM payments WHERE status = 'succeeded' "
            "AND updated_at > NOW() - INTERVAL '24 hours'"
        )
        return {
            "total_users": total_users,
            "today_users": today_users,
            "total_generations": total_generations,
            "completed_generations": completed,
            "total_revenue_rub": (total_revenue or 0) / 100,
            "today_payments": today_payments,
        }
