"""Process news through ChatGPT: select and summarize WITHOUT hallucination."""
import logging
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from html import unescape
import httpx

logger = logging.getLogger(__name__)


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
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
            match = re.search(r'ИСКЛЮЧ[АУ]:\s*(.+?)(?:\n|$)', exclude_text, re.IGNORECASE)
            if match:
                exclude_items = match.group(1)
                # Split by commas and parentheses
                items = re.split(r'[,()]+', exclude_items)
                for item in items:
                    cleaned = item.strip().lower()
                    if cleaned and len(cleaned) > 1:
                        exclusions.append(cleaned)

    logger.info(f"Extracted {len(exclusions)} exclusion keywords")
    return exclusions


def _has_excluded_content(text: str, exclusions: list) -> bool:
    """Check if text contains any excluded keywords."""
    text_lower = text.lower()
    for exclusion in exclusions:
        if exclusion in text_lower:
            return True
    return False


async def select_and_summarize_news_with_gpt(
    news_items: List[Dict[str, Any]], user_id: int
) -> Optional[List[Dict[str, Any]]]:
    """
    Send all news to ChatGPT for selection and summarization.
    ChatGPT returns indices of selected news + summaries.
    We match indices back to original news to preserve URLs.

    Returns:
        [
            {"index": 0, "category": "politics", "summary": "Трамп объявил..."},
            {"index": 3, "category": "politics", "summary": "НАТО критикует..."},
            {"index": 7, "category": "sports", "summary": "Барселона подписала..."},
            {"index": 12, "category": "culture", "summary": "Гориллы родили..."}
        ]

        or None if ChatGPT call fails
    """
    import os
    from src.utils.doppler import get_secret
    from src.db.database import get_news_prompt

    if not news_items:
        logger.warning("No news items to process")
        return None

    try:
        # Build indexed news list for ChatGPT
        indexed_news = []
        for idx, item in enumerate(news_items):
            description = item.get("description", "")
            # Clean HTML tags from RSS feed descriptions
            description = _clean_html(description)[:500]

            indexed_news.append({
                "index": idx,
                "title": item.get("title", ""),
                "description": description,  # Fuller description for better context
                "source": item.get("source", ""),
            })

        # Fetch user's custom news prompt if it exists
        custom_prompt = await get_news_prompt(user_id)
        if custom_prompt:
            logger.info(f"✓ Using custom news prompt for user {user_id}")
            logger.debug(f"  Custom prompt: {custom_prompt[:100]}...")
        else:
            logger.info(f"Using default news profile for user {user_id}")

        user_profile_section = custom_prompt if custom_prompt else (
            "Я выбираю новости, релевантные для бизнес- и системного аналитика, проживающего в Грузии. "
            "Он интересуется: AI и машинным обучением, облачными технологиями, инновациями в IT, "
            "аналитическими подходами, Big Data, DevOps, системным дизайном, новыми продуктами и стартапами. "
            "Также интересуется: футболом (особенно европейским и в частности испанским), экономикой, политикой "
            "(США, Россия, Грузия, ЕС, Китай, крупные страны), событиями в России и Грузии, позитивными "
            "новостями из мира культуры, науки и инноваций. Путешествует по странам, куда не нужна виза "
            "(Кавказ, Средняя Азия, Юго-Восточная Азия).\n"
            "Я НЕ выбираю и ИСКЛЮЧАЮ: новости про неревантные страны (Латинская Америка, Африка, Австралия), "
            "баскетбол, бейсбол, формулу-1, моду, кино, сериалы, документалки, знаменитостей и актёров, "
            "премьеры фильмов,娱乐新闻, развлечение, вымышленные новости, шоу-бизнес, музыкальные турниры, "
            "рейтинги фильмов, премии кино, новости о звёздах."
        )

        # Build system prompt with user interests
        system_prompt = f"""Я персональный помощник для отбора новостей.

⚠️ СНАЧАЛА ФИЛЬТР - ИСКЛЮЧЕНИЯ (УДАЛЯЙ ВСЕ):
Прочитай профиль пользователя ниже. Найди список исключений (после "ИСКЛЮЧАЮ:").
НИКОГДА не выбирай новости, которые содержат эти слова/темы. ПОЛНОСТЬЮ ИГНОРИРУЙ их при выборе.

Затем выбираю из оставшихся ровно 5 новостей:
- 2 новости о политике, экономике или финансах
- 1 новость о спорте (особенно футбол)
- 1 новость о культуре, науке, социальных событиях или добрых новостях (НЕ про кино, знаменитостей, актёров)
- 1 новость о IT, AI, технологиях или инновациях (для аналитика и IT-специалиста)

МОИ КРИТИЧЕСКИЕ ПРАВИЛА:
1. Я выбираю ТОЛЬКО из предоставленного списка
2. Я НЕ выдумываю новости
3. Я пишу одно краткое предложение (максимум 15 слов) для каждой
4. Я объясняю смысл новости и ее основную мысль: максимум 250 символов, не больше! Главное, чтобы было интересно и информативно
5. Я пишу обе части (summary + description) на русском
6. Я возвращаю ответ JSON массивом ровно 5 новостей
7. КРИТИЧНО: Я учитываю интересы пользователя И СТРОГО СЛЕДУЮ исключениям
8. Если нет подходящей новости в категории (из-за исключений), я выбираю ближайшую релевантную, но НИ В КОЕМ СЛУЧАЕ не из исключений
9. Я сохраняю смысл при сокращении описания до 250 символов
10. Четвертая категория (КУЛЬТУРА) - ИСКЛЮЧИТЕЛЬНО позитивные новости о науке, искусстве, инновациях, социальных успехах (НЕ кино, НЕ премьеры)

Профиль пользователя (то, чему я следую при отборе новостей):
{user_profile_section}
"""

        # Build user prompt with indexed news
        user_prompt = f"""Выбери новости из этого списка (используй индексы):

{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

⚠️ КРИТИЧЕСКИ ВАЖНО - ИСКЛЮЧИ ВСЕ новости про:
- Кино, сериалы, премьеры, актёров, знаменитостей
- Развлечение, шоу-бизнес, премии кино
- Любые новости про творческие проекты звёзд

🔴 КРИТИЧЕСКОЕ ПРАВИЛО: description_ru НЕ должна быть переписанной версией summary!
✅ summary = краткий заголовок/главная мысль (15 слов)
✅ description_ru = ДОПОЛНИТЕЛЬНАЯ информация: почему, как, контекст, детали, цифры, факты
❌ description_ru НЕ ПОВТОРЯЕТ summary другими словами

Пример ПЛОХО:
  summary: "Чемпионат мира 1994 сделал футбол популярным в США"
  description_ru: "До 1994 года футбол не был популярен в США, но турнир изменил ситуацию" ← ПЕРЕПИСАНО!

Пример ХОРОШО:
  summary: "Чемпионат мира 1994 сделал футбол популярным в США"
  description_ru: "Турнир получил телетрансляции на основных каналах и привлёк 3,5 млн зрителей на финал" ← ДОПОЛНЕНИЕ!

СТРОГИЕ ТРЕБОВАНИЯ ДЛЯ КАЖДОЙ НОВОСТИ:
1. summary: одно предложение на русском максимум 15 слов (ГЛАВНАЯ ИДЕЯ)
2. description_ru: НОВАЯ информация из текста (почему/как/детали/цифры/контекст) МАКСИМУМ 250 СИМВОЛОВ (не более!)

⚠️ ПРОВЕРКА: description_ru должна содержать ДРУГИЕ факты, чем summary, не пересказывать его!
Считай символы! Если перевод длиннее 250 символов - укороти его, но сохраняй смысл.

ОБЯЗАТЕЛЬНО ВЕРНУТЬ РОВНО 5 НОВОСТЕЙ (в этом порядке):
1. politics (политика/экономика)
2. politics (политика/экономика)
3. sports (спорт)
4. culture (ТОЛЬКО позитивные новости про науку, искусство, инновации, социальные события - НЕ кино, НЕ знаменитости)
5. tech (IT/AI/технологии)

Ответь JSON массивом (без markdown блока):
[
  {{"index": 0, "category": "politics", "summary": "главная мысль (макс 15 слов)", "description_ru": "дополнение: контекст/детали/цифры (макс 250 символов)"}},
  {{"index": 3, "category": "politics", "summary": "главная мысль (макс 15 слов)", "description_ru": "дополнение: контекст/детали/цифры (макс 250 символов)"}},
  {{"index": 7, "category": "sports", "summary": "главная мысль (макс 15 слов)", "description_ru": "дополнение: контекст/детали/цифры (макс 250 символов)"}},
  {{"index": 12, "category": "culture", "summary": "главная мысль (макс 15 слов)", "description_ru": "дополнение: контекст/детали/цифры (макс 250 символов)"}},
  {{"index": 15, "category": "tech", "summary": "главная мысль (макс 15 слов)", "description_ru": "дополнение: контекст/детали/цифры (макс 250 символов)"}}
]

Если нет подходящей новости в какой-то категории, выбери ближайшую релевантную.
Ответ ТОЛЬКО JSON, без комментариев и объяснений.
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
            match = re.search(r'\[.*\]', gpt_response, re.DOTALL)
            if match:
                try:
                    selected_news = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON even after extraction: {gpt_response[:100]}")
                    return None
            else:
                logger.error(f"No JSON array found in response: {gpt_response[:100]}")
                return None

        # Extract exclusions from user profile
        exclusions = _extract_exclusions(user_profile_section)

        # Validate indices are within range and filter out invalid ones
        valid_news = []
        for item in selected_news:
            if isinstance(item, dict) and 0 <= item.get("index", -1) < len(news_items):
                # Check if this news item violates exclusions
                original_news = news_items[item.get("index")]
                title = original_news.get("title", "")
                description = original_news.get("description", "")
                combined_text = f"{title} {description}"

                if exclusions and _has_excluded_content(combined_text, exclusions):
                    logger.warning(
                        f"  ⚠️  Rejected by exclusions: {title[:50]}..."
                    )
                    continue

                valid_news.append(item)
            else:
                idx = item.get("index") if isinstance(item, dict) else "unknown"
                logger.warning(f"Invalid index {idx} (max {len(news_items)-1}), skipping")

        if not valid_news:
            logger.warning("All news items were invalid or excluded, returning None")
            return None

        logger.info(f"✓ ChatGPT selected {len(valid_news)} valid news items (filtered from {len(selected_news)})")
        for item in valid_news:
            logger.info(f"  [{item['index']}] {item['category']}: {item['summary'][:50]}...")

        return valid_news

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ChatGPT JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to process news with ChatGPT: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
