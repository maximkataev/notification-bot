"""Book of the week recommendation via ChatGPT.

Recommended once a week (Wednesday) for all users.
Covers fascinating non-fiction (art, psychology, thinking, architecture, science)
and high-quality fiction (modern prose, page-turners, timeless classics).

History: shown books are recorded in SQLite (shown_content) for 90 days.
Per project rules: NO HARDCODED FALLBACKS — if generation fails, return None.
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Optional, Dict, Any

from src.db.database import (
    GLOBAL_USER_ID,
    get_item_shown_on,
    get_shown_keys,
    record_shown_item,
)
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

CONTENT_TYPE = "book_item"
_book_lock = asyncio.Lock()

# Run on Wednesday (2)
BOOK_WEEKDAY = 2

BOOK_THEMES = [
    "увлекательный нон-фикшн об искусстве, визуальной культуре или архитектуре",
    "книга о мышлении, психологии восприятия, креативности или биохакинге",
    "захватывающий современный роман или интеллектуальный детектив",
    "книга об истории цивилизаций, неожиданных открытиях или антропологии",
    "книга об урбанистике, путешествиях и исследовании городов",
    "классический или культовый роман, который читается на одном дыхании",
    "книга о науке, будущем, технологиях и устройстве Вселенной",
]


def is_book_day(weekday: int) -> bool:
    """Check if book recommendation should run today (Wednesday)."""
    return weekday == BOOK_WEEKDAY


async def get_book_of_week() -> Optional[Dict[str, Any]]:
    """Recommend one great book for the week, avoiding recent repeats.

    Returns:
        {
            "title": str,        # Название книги
            "author": str,       # Автор
            "genre": str,        # Жанр / направление
            "description": str,  # 2 живых предложения: суть книги и почему стоит прочесть
        }
        or None if generation fails.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    async with _book_lock:
        # Same day cache
        cached = await get_item_shown_on(GLOBAL_USER_ID, CONTENT_TYPE, today)
        if cached:
            logger.info(f"Book recommendation (cached for {today}): {cached.get('title')}")
            return cached

        # Exclude books shown in the last 90 days
        recent_books = await get_shown_keys(GLOBAL_USER_ID, CONTENT_TYPE)

        try:
            theme = random.choice(BOOK_THEMES)

            avoid_block = ""
            if recent_books:
                joined = "\n".join(f"- {b}" for b in recent_books)
                avoid_block = (
                    "\n\nНЕ предлагай эти книги (они уже были за последние 90 дней):\n"
                    + joined
                )

            prompt = f"""Посоветуй ОДНУ действительно выдающуюся и увлекательную книгу на тему: "{theme}".

Критерии:
- Реальная, признанная и переведённая на русский язык книга.
- Настоящая литература с глубоким смыслом или ярким стилем, без дешёвого инфобизнеса и поверхностного селф-хелпа.
- Напиши точное название на русском, имя автора, жанр/тему.
- Дай короткое ёмкое описание (2 предложения): главная идея книги и почему она захватывает читателя.{avoid_block}

Верни СТРОГО JSON-объект без markdown и без лишнего текста:
{{
  "title": "название книги на русском",
  "author": "автор",
  "genre": "жанр / направление",
  "description": "описание на русском, 2 предложения"
}}"""

            response = await get_client().chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=220,
                temperature=0.8,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an erudite literary critic and book curator. Recommend exceptional books with captivating descriptions. Reply with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )

            raw = response.choices[0].message.content.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            data = json.loads(raw)
            title = (data.get("title") or "").strip()
            author = (data.get("author") or "").strip()
            genre = (data.get("genre") or "").strip()
            description = (data.get("description") or "").strip()

            if not title or not author or not description:
                logger.warning("Book recommendation: missing required fields")
                return None

            result = {
                "title": title,
                "author": author,
                "genre": genre,
                "description": description,
            }

            key = f"{author} — {title}"
            await record_shown_item(
                GLOBAL_USER_ID,
                CONTENT_TYPE,
                key,
                creator=author,
                title=title,
                payload=result,
                shown_date=today,
            )

            logger.info(f"✓ Book recommendation: «{title}» by {author}")
            return result

        except Exception as e:
            logger.warning(f"Failed to get book recommendation: {type(e).__name__}: {e}")
            return None
