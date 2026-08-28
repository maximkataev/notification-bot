"""Art piece / Masterpiece of the day with background story.

Recommended for art enthusiasts (Юля in Vienna).
Covers classic and modern paintings, sculptures, architecture, stained glass,
and masterpieces in world museums (Belvedere, Kunsthistorisches Museum, Albertina, Louvre, etc.).

History: shown artworks are recorded in SQLite (shown_content) for 90 days.
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

CONTENT_TYPE = "art_item"
_art_lock = asyncio.Lock()

ART_PERIODS = [
    "австрийский модерн и венский сецессион (Густав Климт, Эгон Шиле, Коломан Мозер)",
    "импрессионизм и постимпрессионизм (Моне, Дега, Ренуар, Ван Гог, Сезанн)",
    "Северное Возрождение и фламандская живопись (Брейгель, Босх, ван Эйк, Вермеер)",
    "Итальянский Ренессанс и барокко (Леонардо, Караваджо, Боттичелли, Бернини)",
    "японская ксилография и искусство укиё-э (Хокусай, Хиросигэ, Утамаро)",
    "авангард, конструктивизм и экспрессионизм (Кандинский, Малевич, Франц Марк)",
    "сюрреализм и магический реализм (Магритт, Дали, Джорджо де Кирико)",
    "шедевр архитектуры или монументального искусства (соборы, витражи, уникальные здания)",
    "скульптура (Роден, Канова, Микеланджело, Генри Мур)",
    "культовое произведение искусства из музеев Вены (Бельведер, Музей истории искусств, Альбертина)",
]


async def get_art_of_day() -> Optional[Dict[str, Any]]:
    """Recommend one masterpiece of art with an engaging backstory.

    Returns:
        {
            "title": str,        # Название произведения
            "artist": str,       # Автор / архитектор
            "year": str,         # Год или период создания (например "1907-1908")
            "location": str,     # Музей / город / локация
            "description": str,  # 2-3 живых предложения с интересной деталью / историей создания
        }
        or None if generation fails.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    async with _art_lock:
        # Same day cache
        cached = await get_item_shown_on(GLOBAL_USER_ID, CONTENT_TYPE, today)
        if cached:
            logger.info(f"Art of day (cached for {today}): {cached.get('title')}")
            return cached

        # Exclude artworks sent in the last 90 days
        recent_artworks = await get_shown_keys(GLOBAL_USER_ID, CONTENT_TYPE)

        try:
            direction = random.choice(ART_PERIODS)

            avoid_block = ""
            if recent_artworks:
                joined = "\n".join(f"- {a}" for a in recent_artworks)
                avoid_block = (
                    "\n\nНЕ предлагай эти произведения (они уже были за последние 90 дней):\n"
                    + joined
                )

            prompt = f"""Посоветуй ОДИН шедевр мирового искусства (живопись, скульптура или архитектура) на сегодня ({today}).
Направление/эпоха на сегодня: {direction}.

Требования:
- Реальное, подлинное и известное произведение искусства.
- Укажи точное название, автора/мастера, примерный год/период и где сейчас хранится (музей, город).
- Напиши живое, увлекательное описание на русском (2-3 предложения): в чём изюминка работы, неочевидная скрытая деталь, любопытный факт о создании или судьбе шедевра (без скучных штампов).{avoid_block}

Верни СТРОГО JSON-объект без markdown и без другого текста:
{{
  "title": "название произведения на русском",
  "artist": "автор / архитектор",
  "year": "год или период (например: 1908)",
  "location": "музей и город (например: Галерея Бельведер, Вена)",
  "description": "увлекательное описание с деталью или историей создания на русском (2-3 предложения)"
}}"""

            response = await get_client().chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=250,
                temperature=0.8,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a knowledgeable, engaging art historian. Recommend real art masterpieces with captivating details. Reply with valid JSON only.",
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
            artist = (data.get("artist") or "").strip()
            year = (data.get("year") or "").strip()
            location = (data.get("location") or "").strip()
            description = (data.get("description") or "").strip()

            if not title or not artist or not description:
                logger.warning("Art of day: missing required fields")
                return None

            result = {
                "title": title,
                "artist": artist,
                "year": year,
                "location": location,
                "description": description,
            }

            key = f"{artist} — {title}"
            await record_shown_item(
                GLOBAL_USER_ID,
                CONTENT_TYPE,
                key,
                creator=artist,
                title=title,
                payload=result,
                shown_date=today,
            )

            logger.info(f"✓ Art of day: «{title}» by {artist} ({location})")
            return result

        except Exception as e:
            logger.warning(f"Failed to get art of day: {type(e).__name__}: {e}")
            return None
