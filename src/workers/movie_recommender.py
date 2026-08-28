"""Evening movie / series recommendation via ChatGPT.

Recommended for evening viewing on Tuesday, Friday, Saturday, Sunday.
Covers recent releases (1-3 years old) or lighthearted, atmospheric, high-quality movies/series.

History: shown movies/series are recorded in SQLite (shown_content) for 90 days.
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

CONTENT_TYPE = "movie_item"
_movie_lock = asyncio.Lock()

# Allowed weekdays for movies (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)
# User requirement: пт (4), сб (5), вс (6), вт (1).
MOVIE_WEEKDAYS = {1, 4, 5, 6}

MOVIE_FORMATS = [
    "лёгкая остроумная комедия или драмеди с отличным юмором",
    "захватывающий детектив или камерный триллер с неожиданной развязкой",
    "стильный атмосферный мини-сериал (4-8 серий)",
    "уютное душевное кино для отдыха (feel-good movie)",
    "яркая свежая новинка кино последних 1-3 лет с высоким рейтингом",
    "красивая умная фантастика или приключенческий фильм",
    "европейское или авторское кино с приятным визуалом и сюжетом",
]


def is_movie_day(weekday: int) -> bool:
    """Check if movie recommendation should run today (Tue, Fri, Sat, Sun)."""
    return weekday in MOVIE_WEEKDAYS


async def get_movie_recommendation() -> Optional[Dict[str, Any]]:
    """Recommend one movie or series for evening viewing, avoiding recent repeats.

    Returns:
        {
            "title": str,           # Русское название
            "original_title": str,  # Оригинальное название
            "year": str,            # Год
            "kind": str,            # "фильм" | "сериал" | "мини-сериал"
            "genre": str,           # Жанр
            "description": str,     # 1-2 живых предложения с синопсисом и почему стоит посмотреть
        }
        or None if generation fails.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    async with _movie_lock:
        # Same day cache
        cached = await get_item_shown_on(GLOBAL_USER_ID, CONTENT_TYPE, today)
        if cached:
            logger.info(f"Movie recommendation (cached for {today}): {cached.get('title')}")
            return cached

        # Exclude movies shown in the last 90 days
        recent_movies = await get_shown_keys(GLOBAL_USER_ID, CONTENT_TYPE)

        try:
            format_kind = random.choice(MOVIE_FORMATS)

            avoid_block = ""
            if recent_movies:
                joined = "\n".join(f"- {m}" for m in recent_movies)
                avoid_block = (
                    "\n\nНЕ предлагай эти фильмы/сериалы (они уже были за последние 90 дней):\n"
                    + joined
                )

            prompt = f"""Посоветуй ОДИН отличный фильм, сериал или мини-сериал для вечернего просмотра на сегодня ({today}).
Категория на сегодня: {format_kind}.

Критерии выбора:
- Реальное существующее кино с высоким рейтингом (IMDb/Кинопоиск 7.2+).
- Приветствуются как яркие новинки последних 1-3 лет, так и проверенные атмосферные или лёгкие картины.
- БЕЗ депрессивной чернухи и бессмысленной жестокости — кино должно оставлять приятное или захватывающее впечатление на вечер.
- Укажи русское название, оригинальное название, год, формат (фильм/сериал/мини-сериал) и жанр.
- Напиши краткое ёмкое описание (1-2 предложения): завязка сюжета и чем кино цепляет.{avoid_block}

Верни СТРОГО JSON-объект без markdown и без пояснений:
{{
  "title": "название на русском",
  "original_title": "оригинальное название",
  "year": "год (например: 2024)",
  "kind": "фильм" или "сериал" или "мини-сериал",
  "genre": "жанр (например: детективная комедия)",
  "description": "описание на русском, 1-2 предложения"
}}"""

            response = await get_client().chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=250,
                temperature=0.8,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a tasteful film curator. Recommend genuinely good, engaging movies and series. Reply with valid JSON only.",
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
            original_title = (data.get("original_title") or "").strip()
            year = str(data.get("year") or "").strip()
            kind = (data.get("kind") or "фильм").strip()
            genre = (data.get("genre") or "").strip()
            description = (data.get("description") or "").strip()

            if not title or not description:
                logger.warning("Movie recommendation: missing title or description")
                return None

            result = {
                "title": title,
                "original_title": original_title,
                "year": year,
                "kind": kind,
                "genre": genre,
                "description": description,
            }

            key = f"{title} ({year})" if year else title
            await record_shown_item(
                GLOBAL_USER_ID,
                CONTENT_TYPE,
                key,
                title=title,
                payload=result,
                shown_date=today,
            )

            logger.info(f"✓ Movie recommendation: {title} ({year})")
            return result

        except Exception as e:
            logger.warning(f"Failed to get movie recommendation: {type(e).__name__}: {e}")
            return None
