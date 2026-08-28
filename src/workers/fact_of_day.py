"""Light, fascinating and verified fact of the day.

Fetches real curated facts from verified sources:
1. Primary: Curated Facts database (uselessfacts.jsph.pl API) + precise Russian translation
2. Fallback: Wikipedia «Знаете ли вы?» (Main page editorial DYK section)

Strict rule: ONLY LIGHT, POSITIVE and CURIOUS facts.
STRICTLY BANNED: dark topics, deaths, wars, diseases, murders, dictators, tragedies.

History: shown facts are stored in SQLite (shown_content) for 90 days so nothing repeats.
Per project rules: NO HARDCODED FALLBACKS — if sources fail, return None.
"""

import asyncio
import json
import logging
import random
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
from bs4 import BeautifulSoup

from src.db.database import (
    GLOBAL_USER_ID,
    get_item_shown_on,
    get_shown_keys,
    record_shown_item,
)
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

CONTENT_TYPE = "fact_item"
_fact_lock = asyncio.Lock()

_USELESSFACTS_URL = "https://uselessfacts.jsph.pl/api/v2/facts/random"
_WIKI_RU_MAIN_PAGE_URL = (
    "https://ru.wikipedia.org/w/api.php?action=parse&page=%D0%97%D0%B0%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD%D0%B0%D1%8F_%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0&format=json&prop=text"
)
_USER_AGENT = "NotificationBot/1.0 (https://github.com/notification-bot)"
_REQUEST_TIMEOUT = 10.0


async def _translate_and_format_fact(raw_fact_en: str, recent_keys: List[str]) -> Optional[Dict[str, str]]:
    """Translate and format a real English fact into clean Russian with topic categorization."""
    avoid_block = ""
    if recent_keys:
        joined = "\n".join(f"- {f}" for f in recent_keys[-25:])
        avoid_block = (
            "\n\nНЕ используй факты на эти темы, если они уже были:\n" + joined
        )

    prompt = f"""Переведи и красиво оформи на русском языке проверенный реальный факт.

ОРИГИНАЛЬНЫЙ ФАКТ (на английском):
"{raw_fact_en}"

ТРЕБОВАНИЯ:
1. Сохрани 100% фактическую точность оригинального факта.
2. Тон: лёгкий, позитивный, любопытный и понятный (1-2 предложения, до 220 символов).
3. СТРОГИЙ БАН на мрак: если факт касается смертей, болезней, войн, жестокости, диктаторов, трагедий — верни СТРОГО: {{"reject": true}}
4. Придумай короткую тему (например: "О животных", "О космосе", "О природе", "О еде", "О языке", "О человеке").{avoid_block}

Верни СТРОГО JSON-объект без markdown:
{{
  "topic": "короткая тема (например: О животных)",
  "text": "текст факта на хорошем русском языке"
}}"""

    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "You are a scientific translator who formats verified facts accurately into Russian. Reply with valid JSON only.",
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
        if data.get("reject"):
            logger.info("Fact rejected by safety/tone filter")
            return None

        fact_text = (data.get("text") or "").strip()
        fact_topic = (data.get("topic") or "Интересный факт").strip()

        if not fact_text or len(fact_text) < 15:
            return None

        return {"topic": fact_topic, "text": fact_text, "raw_key": raw_fact_en}
    except Exception as e:
        logger.warning(f"Failed to translate fact: {type(e).__name__}: {e}")
        return None


async def _fetch_from_uselessfacts(recent_keys: List[str]) -> Optional[Dict[str, Any]]:
    """Fetch random verified fact from uselessfacts.jsph.pl API."""
    shown_set = {k.lower() for k in recent_keys}

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                res = await client.get(_USELESSFACTS_URL, headers={"User-Agent": _USER_AGENT})
                if res.status_code != 200:
                    continue
                data = res.json()
                raw_fact = (data.get("text") or "").strip()
                if not raw_fact:
                    continue

                if raw_fact.lower() in shown_set:
                    continue

                formatted = await _translate_and_format_fact(raw_fact, recent_keys)
                if formatted:
                    return formatted
        except Exception as e:
            logger.warning(f"Uselessfacts API attempt {attempt+1} failed: {type(e).__name__}: {e}")

    return None


async def _fetch_from_wikipedia(recent_keys: List[str]) -> Optional[Dict[str, Any]]:
    """Fetch fact from Russian Wikipedia 'Знаете ли вы?' section."""
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            res = await client.get(_WIKI_RU_MAIN_PAGE_URL, headers={"User-Agent": _USER_AGENT})
            if res.status_code != 200:
                return None
            data = res.json()
            html_text = data.get("parse", {}).get("text", {}).get("*", "")
            if not html_text:
                return None

        soup = BeautifulSoup(html_text, "html.parser")
        dyk_box = soup.find(id="main-dyk")
        if not dyk_box:
            return None

        candidates = []
        for li in dyk_box.find_all("li"):
            text = li.get_text().strip()
            # Filter out navigation links and short items
            if not text or len(text) < 20:
                continue
            if text in ("Предложения", "Архив", "Просмотр шаблона"):
                continue
            # Remove (на илл.) and similar footnotes
            cleaned = re.sub(r"\(на\s+илл\.\)|\(на\s+фото\)", "", text).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            candidates.append(cleaned)

        if not candidates:
            return None

        random.shuffle(candidates)

        avoid_block = ""
        if recent_keys:
            joined = "\n".join(f"- {f}" for f in recent_keys[-25:])
            avoid_block = (
                "\n\nНЕ выбирай факты, похожие на эти:\n" + joined
            )

        prompt = f"""Выбери ОДИН самый лёгкий, любопытный и позитивный факт из списка рубрики «Знаете ли вы?» русской Википедии:

СПИСОК ФАКТОВ:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
1. Выбери факт, который читается легко, увлекательно и без негатива.
2. СТРОГИЙ ЗАПРЕТ: войны, жертвы, нацизм, катастрофы, трагедии, насилие, болезни.
3. Добавь подходящую короткую тему ("О природе", "Об истории", "О науке", "О культуре" и т.п.).{avoid_block}

Верни СТРОГО JSON:
{{
  "topic": "короткая тема",
  "text": "текст выбранного факта"
}}"""

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "You select lighthearted, fascinating encyclopedia facts. Reply with valid JSON only.",
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
        fact_text = (data.get("text") or "").strip()
        fact_topic = (data.get("topic") or "Знаете ли вы").strip()

        if fact_text and len(fact_text) >= 15:
            return {"topic": fact_topic, "text": fact_text, "raw_key": fact_text}

    except Exception as e:
        logger.warning(f"Wikipedia DYK fetch failed: {type(e).__name__}: {e}")

    return None


async def get_fact_of_day() -> Optional[Dict[str, Any]]:
    """Get a real, verified, lighthearted fact of the day with fallback sources.

    Sources:
    1. Primary: Verified Curated Facts API (uselessfacts.jsph.pl)
    2. Fallback: Wikipedia «Знаете ли вы?»

    Returns:
        {
            "topic": str,  # "О животных" | "О космосе" | ...
            "text": str,   # 1-2 sentences with the verified fact
        }
        or None if all sources fail.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    async with _fact_lock:
        # Same day cache → all recipients get the same fact on a given date.
        cached = await get_item_shown_on(GLOBAL_USER_ID, CONTENT_TYPE, today)
        if cached:
            logger.info(f"Fact of day (cached for {today}): {cached.get('text', '')[:40]}...")
            return cached

        # Exclude facts shown in the last 90 days.
        recent_facts = await get_shown_keys(GLOBAL_USER_ID, CONTENT_TYPE)

        result = None

        # 1. Primary: Curated facts database
        logger.info("Fetching fact of day from Curated Facts API")
        result = await _fetch_from_uselessfacts(recent_facts)

        # 2. Fallback: Wikipedia "Знаете ли вы?"
        if not result:
            logger.info("Curated Facts API unavailable, falling back to Wikipedia 'Знаете ли вы?'")
            result = await _fetch_from_wikipedia(recent_facts)

        if not result:
            logger.warning("All fact sources failed or exhausted, returning None")
            return None

        # Record in SQLite history (anti-repeat for 90 days)
        raw_key = result.get("raw_key") or result["text"][:80]
        await record_shown_item(
            GLOBAL_USER_ID,
            CONTENT_TYPE,
            raw_key,
            title=result["topic"],
            payload=result,
            shown_date=today,
        )

        logger.info(f"✓ Fact of day ({result['topic']}): {result['text'][:50]}...")
        return result
