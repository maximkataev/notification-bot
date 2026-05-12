"""Process news through ChatGPT: select and summarize WITHOUT hallucination."""

import logging
import json
import re
from typing import List, Dict, Any, Optional
from html import unescape
import httpx

logger = logging.getLogger(__name__)


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_exclusions(profile_text: str) -> list:
    """Extract exclusion keywords from user profile text."""
    exclusions = []
    if "ИСКЛЮЧАЮ:" in profile_text or "ИСКЛЮЧУ:" in profile_text:
        # Find the exclusion section
        start_idx = profile_text.find("ИСКЛЮЧАЮ:")
        if start_idx == -1:
            start_idx = profile_text.find("ИСКЛЮЧУ:")

        if start_idx != -1:
            exclude_text = profile_text[start_idx:]
            # Extract comma-separated values until end of line or sentence
            import re

            # Match everything after ИСКЛЮЧАЮ: until end of text or line break
            match = re.search(
                r"ИСКЛЮЧ[АУ]:\s*(.+?)(?:\n|$)", exclude_text, re.IGNORECASE
            )
            if match:
                exclude_items = match.group(1)
                # Split by commas and parentheses
                items = re.split(r"[,()]+", exclude_items)
                for item in items:
                    cleaned = item.strip().lower()
                    if cleaned and len(cleaned) > 1:
                        exclusions.append(cleaned)

    logger.info(f"Extracted {len(exclusions)} exclusion keywords")
    return exclusions


def _has_excluded_content(text: str, exclusions: list) -> bool:
    """Check if text contains any excluded keywords (with morphological flexibility)."""
    text_lower = text.lower()
    for exclusion in exclusions:
        # Exact match first
        if exclusion in text_lower:
            return True

        # For compound words with hyphens (e.g., "формула-1"), check the root word
        # This handles Russian morphology: "формула-1" matches both "формула" and "формулу"
        if "-" in exclusion:
            root = exclusion.split("-")[
                0
            ]  # Get word before hyphen: "формула-1" → "формула"
            # Check root + common Russian endings
            for variant in [root, root + "у", root + "ы", root + "е"]:
                if variant in text_lower:
                    return True

    return False


async def select_and_summarize_news_with_gpt(
    politics_news: List[Dict[str, Any]],
    sports_news: List[Dict[str, Any]],
    technology_news: List[Dict[str, Any]],
    culture_news: List[Dict[str, Any]],
    goodness_news: List[Dict[str, Any]],
    user_id: int,
) -> Optional[List[Dict[str, Any]]]:
    """
    Send categorized news to ChatGPT for selection and summarization.
    Each category has its own pool, GPT selects from each.

    Returns:
        [
            {"index": 0, "category": "politics", "summary": "Трамп объявил..."},
            {"index": 3, "category": "politics", "summary": "НАТО критикует..."},
            {"index": 7, "category": "sports", "summary": "Барселона подписала..."},
            {"index": 12, "category": "culture", "summary": "Гориллы родили..."},
            {"index": 15, "category": "technology", "summary": "Google запустил..."},
            {"index": 20, "category": "goodness", "summary": "Спасли 100 собак..."}
        ]

        or None if ChatGPT call fails
    """
    import os
    from src.utils.doppler import get_secret
    from src.db.database import get_news_prompt

    all_news = (
        politics_news + sports_news + technology_news + culture_news + goodness_news
    )
    if not all_news:
        logger.warning("No news items to process")
        return None

    try:
        # Build indexed news list for ChatGPT with category tags
        indexed_news = []
        idx_to_original = {}  # Map index -> (pool_name, original_item)
        idx = 0

        for category_name, news_list in [
            ("politics", politics_news),
            ("sports", sports_news),
            ("technology", technology_news),
            ("culture", culture_news),
            ("goodness", goodness_news),
        ]:
            for item in news_list:
                description = item.get("description", "")
                description = _clean_html(description)[:500]

                indexed_news.append(
                    {
                        "index": idx,
                        "title": item.get("title", ""),
                        "description": description,
                        "source": item.get("source", ""),
                        "available_in": category_name,  # Mark which pool it's from
                    }
                )
                idx_to_original[idx] = (
                    category_name,
                    item,
                )  # Save original for validation
                idx += 1

        # Fetch user's custom news prompt if it exists
        custom_prompt = await get_news_prompt(user_id)
        if custom_prompt:
            logger.info(f"✓ Using custom news prompt for user {user_id}")
            logger.debug(f"  Custom prompt: {custom_prompt[:100]}...")
        else:
            logger.info(f"Using default news profile for user {user_id}")

        user_profile_section = (
            custom_prompt
            if custom_prompt
            else (
                "Я выбираю новости, релевантные для бизнес- и системного аналитика, проживающего в Грузии. "
                "Он интересуется: AI и машинным обучением, облачными технологиями, инновациями в IT, "
                "аналитическими подходами, Big Data, DevOps, системным дизайном, новыми продуктами и стартапами. "
                "Также интересуется: футболом (особенно европейским и в частности испанским), экономикой, политикой "
                "(США, Россия, Грузия, ЕС, Китай, крупные страны), событиями в России и Грузии, позитивными "
                "новостями из мира культуры, науки и инноваций. Путешествует по странам, куда не нужна виза "
                "(Кавказ, Средняя Азия, Юго-Восточная Азия).\n"
                "Я НЕ выбираю и ИСКЛЮЧАЮ: новости про неревантные страны (Латинская Америка, Африка, Австралия), "
                "баскетбол, бейсбол, формула-1, гонки, racing, машины, моду, кино, сериалы, документалки, знаменитостей и актёров, "
                "премьеры фильмов, развлечение, вымышленные новости, шоу-бизнес, музыкальные турниры, "
                "рейтинги фильмов, премии кино, новости о звёздах."
            )
        )

        # Build system prompt with user interests
        system_prompt = f"""Я выбираю ровно 6 новостей из 5 специализированных пулов источников.

РАСПРЕДЕЛЕНИЕ ПО ПОЗИЦИЯМ:
1️⃣ #1-2: Политика (из пула "politics") — 2 разные новости
2️⃣ #3: Спорт (из пула "sports") — или fallback на культуру, НО НЕ политику
3️⃣ #4-6: Культура, технологии, добрые новости (по одной из каждого пула)

КРИТИЧЕСКИЕ ПРАВИЛА:
- Выбираю ТОЛЬКО из указанного пула для каждой позиции ("available_in")
- ровно 6 новостей, ровно 2 политики, БАН на 3+ политики
- Спорт: только из пула "sports" (футбол, хоккей, теннис, легкая атлетика)
- Добрые новости: ТОЛЬКО позитив, БАН на смерти/войны/трагедии
- Исключения: читаю "ИСКЛЮЧАЮ:" в профиле и ПОЛНОСТЬЮ их игнорирую

FORMAT:
- summary: одна фраза, максимум 15 слов
- description_ru: новая информация (детали, цифры, контекст), максимум 250 символов
- description НЕ дублирует summary

Профиль пользователя:
{user_profile_section}
"""

        # Build user prompt with indexed news
        user_prompt = f"""ВЫБЕРИ РОВНО 6 НОВОСТЕЙ ПО СХЕМЕ:

Позиция 1 & 2: "available_in": "politics" (2 разные новости)
Позиция 3: "available_in": "sports" (или культура, если спорта нет, но НЕ политика!)
Позиция 4: "available_in": "culture"
Позиция 5: "available_in": "technology"
Позиция 6: "available_in": "goodness" (ТОЛЬКО позитив: животные, волонтёрство, благотворительность)

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ПРАВИЛА:
✅ Точно 6 новостей, ровно 2 политики
❌ БАН: 3+ политики, политика вместо спорта, трагедии/смерти в позиции 6
✅ summary: макс 15 слов (главная идея)
✅ description_ru: макс 250 символов (новая информация, НЕ пересказ)
✅ Только JSON, без текста

ПРИМЕР:
[
  {{"index": 0, "category": "politics", "summary": "Санкции США против нефтяного сектора", "description_ru": "Затрагивают 10+ компаний. Введены в ответ на нарушения международного права."}},
  {{"index": 3, "category": "politics", "summary": "ЕС и Грузия подписали торговое соглашение", "description_ru": "Инвестиции $200 млн в портовую инфраструктуру на 5 лет."}},
  {{"index": 7, "category": "sports", "summary": "Barcelona победила Madrid в полуфинале", "description_ru": "Финальный счет 2:1. Barcelona выходит в финал Лиги чемпионов."}},
  {{"index": 12, "category": "culture", "summary": "Новая выставка русского авангарда в Лондоне", "description_ru": "150 работ из 1920-х годов. Экспозиция будет открыта 6 месяцев."}},
  {{"index": 15, "category": "tech", "summary": "Google запустил новый AI для обработки видео", "description_ru": "Обрабатывает видео в 10x быстрее конкурентов. Бесплатно на Google Cloud."}},
  {{"index": 18, "category": "goodness", "summary": "Волонтёры спасли 500 бездомных собак", "description_ru": "Открыт новый приют. Получен грант $50 тыс. Все животные здоровы."}}
]
"""

        # Get API key (not async)
        api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-5.4-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.5,
                    "max_completion_tokens": 1000,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        # Parse JSON response with robust extraction
        import re

        try:
            # Try extracting JSON if wrapped in markdown
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()

            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            # Try extracting first [ ... ] block if not valid JSON
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if match:
                try:
                    selected_news = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.error(
                        f"Failed to parse JSON even after extraction: {gpt_response[:100]}"
                    )
                    return None
            else:
                logger.error(f"No JSON array found in response: {gpt_response[:100]}")
                return None

        # Extract exclusions from user profile
        exclusions = _extract_exclusions(user_profile_section)

        # Validate indices are within range, check pool assignment, filter exclusions
        valid_news = []
        category_counts = {
            "politics": 0,
            "sports": 0,
            "technology": 0,
            "culture": 0,
            "goodness": 0,
        }

        for item in selected_news:
            if not isinstance(item, dict) or not (
                0 <= item.get("index", -1) < len(indexed_news)
            ):
                idx = item.get("index") if isinstance(item, dict) else "unknown"
                logger.warning(
                    f"Invalid index {idx} (max {len(indexed_news)-1}), skipping"
                )
                continue

            idx = item.get("index")
            category = item.get("category", "unknown")

            # Get original news item from saved mapping
            if idx in idx_to_original:
                _, original_news = idx_to_original[idx]
                title = original_news.get("title", "")
                description = original_news.get("description", "")
                combined_text = f"{title} {description}"

                if exclusions and _has_excluded_content(combined_text, exclusions):
                    logger.warning(f"  ⚠️  Rejected by exclusions: {title[:50]}...")
                    continue

                valid_news.append(item)
                category_counts[category] = category_counts.get(category, 0) + 1
            else:
                logger.warning(f"Index {idx} not found in mapping, skipping")

        if not valid_news:
            logger.warning("All news items were invalid or excluded, returning None")
            return None

        logger.info(
            f"✓ ChatGPT selected {len(valid_news)} valid news items (filtered from {len(selected_news)})"
        )
        for item in valid_news:
            logger.info(
                f"  [{item['index']}] {item['category']}: {item['summary'][:50]}..."
            )

        return valid_news

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ChatGPT JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to process news with ChatGPT: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
