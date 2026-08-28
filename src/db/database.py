"""SQLite database management."""

import aiosqlite
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, List
from src.db.models import UserProfile, ExchangeRate

logger = logging.getLogger(__name__)

DB_PATH = Path("data/tasks.db")

# How long a content unit (video, podcast, album, meme, place, idiom) stays in the
# anti-repeat window. Nothing is ever deleted from the table — the window is applied
# when reading, so already-sent history is never lost.
CONTENT_HISTORY_DAYS = 90

# Content that is shared by every recipient (idiom / place of the day: everyone gets
# the same one on a given date) is stored under this pseudo user id.
GLOBAL_USER_ID = 0


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

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shown_content (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                creator      TEXT NOT NULL,
                shown_at     TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_shown_content_lookup "
            "ON shown_content (user_id, content_type, id)"
        )

        # Migration: item-level columns so every content unit (not just a creator)
        # can be recorded — url/phrase/place key, its payload and the local date.
        cursor = await db.execute("PRAGMA table_info(shown_content)")
        existing_columns = {row[1] for row in await cursor.fetchall()}
        for column in ("item_key", "title", "url", "payload", "shown_date"):
            if column not in existing_columns:
                await db.execute(
                    f"ALTER TABLE shown_content ADD COLUMN {column} TEXT"
                )

        # Backfill rows written before the migration (already-shown podcasts and
        # albums) so they keep being excluded from recommendations.
        await db.execute(
            "UPDATE shown_content SET item_key = creator WHERE item_key IS NULL"
        )
        await db.execute(
            "UPDATE shown_content SET shown_date = date(shown_at) "
            "WHERE shown_date IS NULL AND shown_at IS NOT NULL"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_shown_content_window "
            "ON shown_content (user_id, content_type, shown_date)"
        )

        await db.commit()
        logger.info("Database initialized")

    await import_legacy_json_histories()


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


# Shown content history (anti-repeat across restarts/redeploys).
#
# Every content unit sent to a recipient is recorded here — videos, podcast
# episodes, albums, memes, places of the day, idioms — and excluded from new
# recommendations for CONTENT_HISTORY_DAYS days. Rows are never deleted: the
# retention window is applied when reading, so nothing already sent is lost.
def _history_cutoff(days: int) -> str:
    """Local date (YYYY-MM-DD) from which history entries still count."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


async def record_shown_item(
    user_id: int,
    content_type: str,
    key: str,
    *,
    creator: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    shown_date: Optional[str] = None,
):
    """Record one content unit as sent to `user_id`.

    Args:
        content_type: "video_item" | "podcast_item" | "podcast" (creator-level) |
            "album" | "meme_item" | "place_<city>" | "idiom_<lang>"
        key: stable identity of the unit (url, phrase, place name, "artist — album")
        payload: full item, kept so same-day recipients get the identical content
        shown_date: local date of sending (defaults to today)
    """
    if not key:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO shown_content
                (user_id, content_type, creator, item_key, title, url, payload, shown_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                content_type,
                creator or key,
                key,
                title,
                url,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                shown_date or datetime.now().strftime("%Y-%m-%d"),
            ),
        )
        await db.commit()


async def get_shown_keys(
    user_id: int, content_type: str, days: int = CONTENT_HISTORY_DAYS
) -> List[str]:
    """Return the keys of every unit of this type sent to the user in the window."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COALESCE(item_key, creator)
            FROM shown_content
            WHERE user_id = ? AND content_type = ?
              AND COALESCE(shown_date, date(shown_at), '') >= ?
            GROUP BY COALESCE(item_key, creator)
            ORDER BY MAX(id) ASC
            """,
            (user_id, content_type, _history_cutoff(days)),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows if row[0]]


async def get_shown_items(
    user_id: int, content_type: str, days: int = CONTENT_HISTORY_DAYS
) -> List[Dict[str, Any]]:
    """Return full history entries (oldest → newest) for this type in the window."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT COALESCE(item_key, creator), creator, title, url, payload,
                   COALESCE(shown_date, date(shown_at), '')
            FROM shown_content
            WHERE user_id = ? AND content_type = ?
              AND COALESCE(shown_date, date(shown_at), '') >= ?
            ORDER BY id
            """,
            (user_id, content_type, _history_cutoff(days)),
        )
        rows = await cursor.fetchall()

    items: List[Dict[str, Any]] = []
    for key, creator, title, url, payload, date in rows:
        parsed = None
        if payload:
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                parsed = None
        items.append(
            {
                "key": key,
                "creator": creator,
                "title": title,
                "url": url,
                "payload": parsed,
                "date": date,
            }
        )
    return items


async def get_item_shown_on(
    user_id: int, content_type: str, date: str
) -> Optional[Dict[str, Any]]:
    """Return the payload of the unit sent on `date` (same-day cache), if any."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT payload
            FROM shown_content
            WHERE user_id = ? AND content_type = ?
              AND COALESCE(shown_date, date(shown_at), '') = ?
              AND payload IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, content_type, date),
        )
        row = await cursor.fetchone()

    if not row:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


async def get_shown_creators(
    user_id: int, content_type: str = "podcast", days: int = CONTENT_HISTORY_DAYS
) -> List[str]:
    """Return creators shown to the user for this content type within the window."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT DISTINCT creator
            FROM shown_content
            WHERE user_id = ? AND content_type = ?
              AND COALESCE(shown_date, date(shown_at), '') >= ?
            """,
            (user_id, content_type, _history_cutoff(days)),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows if row[0]]


async def record_shown_content(
    user_id: int, creator: str, content_type: str = "podcast"
):
    """Record a shown creator so it is excluded from future recommendations."""
    await record_shown_item(user_id, content_type, creator, creator=creator)


# One-time import of the pre-SQLite JSON histories. The files stay on disk
# untouched; entries already present in the table are skipped, so importing is
# idempotent and nothing that was already sent is lost.
_LEGACY_JSON_HISTORIES = {
    "idiom_en": ("idiom_history.json", "phrase"),
    "idiom_es": ("idiom_history_es.json", "phrase"),
    "place_tbilisi": ("place_history.json", "name"),
    "place_vienna": ("place_history_vienna.json", "name"),
}


def _legacy_history_entries(filename: str) -> List[Dict[str, Any]]:
    """Read a legacy history file from the data dir (relative to cwd or to the repo)."""
    candidates = [
        DB_PATH.parent / filename,
        Path(__file__).resolve().parents[2] / "data" / filename,
    ]
    entries: List[Dict[str, Any]] = []
    seen_paths = set()
    for path in candidates:
        resolved = str(path.resolve()) if path.exists() else None
        if not resolved or resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                entries.extend(e for e in data if isinstance(e, dict))
        except Exception as e:
            logger.warning(
                f"Could not read legacy history {path}: {type(e).__name__}: {e}"
            )
    return entries


async def import_legacy_json_histories():
    """Import idiom/place history from data/*.json into shown_content."""
    for content_type, (filename, key_field) in _LEGACY_JSON_HISTORIES.items():
        entries = _legacy_history_entries(filename)
        if not entries:
            continue

        known = set(await get_shown_keys(GLOBAL_USER_ID, content_type, days=36500))
        imported = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = (entry.get(key_field) or "").strip()
            if not key or key in known:
                continue
            payload = {k: v for k, v in entry.items() if k != "date"}
            await record_shown_item(
                GLOBAL_USER_ID,
                content_type,
                key,
                title=key,
                payload=payload,
                shown_date=entry.get("date") or datetime.now().strftime("%Y-%m-%d"),
            )
            known.add(key)
            imported += 1

        if imported:
            logger.info(f"Imported {imported} legacy {content_type} entries from {filename}")


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
