"""SQLite database management."""
import aiosqlite
import logging
from pathlib import Path
from typing import Optional, List
from src.db.models import UserProfile, ExchangeRate

logger = logging.getLogger(__name__)

DB_PATH = Path("data/tasks.db")


async def init_db():
    """Initialize database and run migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id     INTEGER PRIMARY KEY,
                wake_time   TEXT DEFAULT '09:00',
                sleep_time  TEXT DEFAULT '23:00',
                preferences TEXT,
                timezone    TEXT DEFAULT 'Asia/Tbilisi',
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_rules (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                rule      TEXT NOT NULL,
                category  TEXT,
                active    INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_config (
                user_id       INTEGER PRIMARY KEY,
                custom_prompt TEXT,
                updated_at    TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await db.commit()
        logger.info("Database initialized")

# User Profile operations
async def get_user_profile(user_id: int) -> UserProfile:
    """Get user profile, create if not exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, wake_time, sleep_time, preferences, timezone, updated_at
            FROM user_profile
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

        if row:
            return UserProfile(
                user_id=row[0],
                wake_time=row[1],
                sleep_time=row[2],
                preferences=row[3] or "",
                timezone=row[4],
                updated_at=row[5],
            )

        # Create default profile
        profile = UserProfile(user_id=user_id)
        await save_user_profile(profile)
        return profile


async def save_user_profile(profile: UserProfile):
    """Save or update user profile."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO user_profile
            (user_id, wake_time, sleep_time, preferences, timezone, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            profile.to_tuple(),
        )
        await db.commit()


# AI Rules management
async def add_ai_rule(user_id: int, rule: str, category: Optional[str] = None) -> int:
    """Add a custom rule for AI."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO ai_rules (user_id, rule, category, active)
            VALUES (?, ?, ?, 1)
            """,
            (user_id, rule, category),
        )
        await db.commit()
        return cursor.lastrowid


async def get_ai_rules(user_id: int) -> List[tuple]:
    """Get all active rules for user. Returns (id, rule, category)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, rule, category
            FROM ai_rules
            WHERE user_id = ? AND active = 1
            ORDER BY created_at
            """,
            (user_id,),
        )
        return await cursor.fetchall()


async def delete_ai_rule(rule_id: int, user_id: int) -> bool:
    """Delete a rule (soft delete)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE ai_rules
            SET active = 0
            WHERE id = ? AND user_id = ?
            """,
            (rule_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def reset_ai_rules(user_id: int):
    """Delete all rules for user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE ai_rules
            SET active = 0
            WHERE user_id = ?
            """,
            (user_id,),
        )
        await db.commit()


async def get_news_prompt(user_id: int) -> Optional[str]:
    """Get custom news prompt for user, or None if using default."""
    logger.debug(f"Loading news prompt for user {user_id}")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT custom_prompt FROM news_config WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row and row[0]:
            logger.debug(f"✓ Custom news prompt found for user {user_id}")
            return row[0]
        else:
            logger.debug(f"Using default news prompt for user {user_id}")
            return None


async def set_news_prompt(user_id: int, prompt: str):
    """Set custom news prompt for user."""
    logger.info(f"Updating news prompt for user {user_id}: {prompt[:50]}...")
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if exists
        cursor = await db.execute(
            "SELECT user_id FROM news_config WHERE user_id = ?",
            (user_id,),
        )
        exists = await cursor.fetchone()

        if exists:
            logger.debug(f"Updating existing news_config for user {user_id}")
            await db.execute(
                """
                UPDATE news_config
                SET custom_prompt = ?, updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (prompt, user_id),
            )
        else:
            logger.debug(f"Creating new news_config for user {user_id}")
            await db.execute(
                """
                INSERT INTO news_config (user_id, custom_prompt)
                VALUES (?, ?)
                """,
                (user_id, prompt),
            )

        await db.commit()
        logger.info(f"✓ News prompt updated for user {user_id}")


async def reset_news_prompt(user_id: int):
    """Reset news prompt to default (delete custom)."""
    logger.info(f"Resetting news prompt for user {user_id} to default")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE news_config
            SET custom_prompt = NULL, updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (user_id,),
        )
        await db.commit()
        logger.info(f"✓ News prompt reset for user {user_id}")

