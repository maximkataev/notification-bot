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


# Marker ChatGPT must return when it cannot/won't summarize an item
REJECT_MARKER = "❌"

# Refusal phrases that may leak if the model ignores the ❌ marker.
# Must be SPECIFIC — bare "не могу"/"не может"/"cannot" appear in legitimate news
# (e.g. "ЕС не может договориться о санкциях") and must NOT trigger a drop.
_REFUSAL_MARKERS = [
    "я не могу", "не могу оценить", "не могу описать", "не могу составить",
    "не могу подобрать", "невозможно оценить", "не удалось оценить",
    "as an ai", "i cannot", "i can't", "i'm unable", "i am unable",
    "cannot summarize", "can't summarize", "unable to summarize",
]


def _is_rejected_description(desc: str) -> bool:
    """True if a description signals a ChatGPT rejection / failed summary.

    Such items must be dropped from the digest rather than shown to the user.
    """
    if not desc or not desc.strip():
        return True
    if REJECT_MARKER in desc:
        return True
    d = desc.strip().lower()
    return any(marker in d for marker in _REFUSAL_MARKERS)


async def select_good_news_with_summaries(
    goodness_news: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """
    For secondary users without tasks: select up to 6 good news items
    and generate ChatGPT summaries for each. No duplicates.

    Returns:
        [
            {"index": 0, "category": "goodness", "description_ru": "..."},
            ...
        ]
        or None if ChatGPT call fails
    """
    import os
    from src.utils.doppler import get_secret

    if not goodness_news:
        logger.warning("No good news items to process")
        return None

    try:
        # Build indexed news list, removing duplicates by URL
        # Keep original indices so we can match them back in scheduler
        indexed_news = []
        seen_urls = set()

        for orig_pos, item in enumerate(goodness_news):
            url = item.get("url", "")
            # Skip if duplicate URL
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            description = item.get("description", "")
            description = _clean_html(description)[:500]

            indexed_news.append({
                "index": orig_pos,  # Keep original position in goodness_news
                "title": item.get("title", ""),
                "description": description,
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            })

            # Limit to 15 items for ChatGPT to choose from
            if len(indexed_news) >= 15:
                break

        if not indexed_news:
            logger.warning("No unique good news items after deduplication")
            return None

        logger.info(f"Processing {len(indexed_news)} unique good news items (deduplicated)")

        # Build prompt for ChatGPT.
        # This path serves the "good-news-only" user (Маша): NO politics, economics,
        # finance, markets, war or sports — ONLY warm, uplifting, heartwarming stories
        # (animals, zoos, wildlife, rescues, kindness, generosity, human-interest,
        # nature, helpful science). Quality over quantity: returning 2-3 genuinely
        # uplifting items is far better than padding to 6 with hard news.
        system_prompt = """You are an editor of a "good news only" digest for a kind, animal-loving reader.
You select ONLY genuinely warm, uplifting, heartwarming stories: animals, zoos, wildlife,
rescues, acts of kindness and generosity, touching human-interest stories, nature, and
science/medicine breakthroughs that help people or animals.
You STRICTLY REJECT anything about politics, government, elections, economics, finance,
markets, oil/energy, business, war, conflict, crime, disasters, diseases, deaths, and ALL
sports. When in doubt, reject.
Quality over quantity: pick FEWER items rather than including anything that is not clearly uplifting.
For each chosen item write a summary in Russian (50-70 words). Return ONLY a valid JSON array."""

        user_prompt = f"""ВЫБЕРИ ДО 6 ПО-НАСТОЯЩЕМУ ДОБРЫХ, ТЁПЛЫХ И ВДОХНОВЛЯЮЩИХ НОВОСТЕЙ из списка (можно МЕНЬШЕ — лучше 2-3 отличных, чем 6 с натяжкой).

РАЗРЕШЕНО (только такое): животные, зоопарки, дикая природа, спасение животных и людей,
доброта, забота, щедрость, волонтёрство, трогательные человеческие истории, природа,
достижения и открытия в науке/медицине, которые помогают людям или животным.

СТРОГО ЗАПРЕЩЕНО (никогда не включай, даже если новость нейтральная или «не негативная»):
политика, власть, выборы, экономика, финансы, рынки, нефть, энергетика, бизнес, санкции,
войны, конфликты, геополитика, преступления, катастрофы, болезни, смерти и ЛЮБОЙ спорт.
Если новость про политику/экономику/спорт — она ЗАПРЕЩЕНА, даже если выглядит позитивной.

NEWS:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
- Выбери ДО 6 новостей (можно меньше, если по-настоящему добрых мало)
- description_ru: ОДНО ПОЛНОЕ описание (50-70 слов на русском)
  * Начинается с НОВОЙ информации (не пересказ title)
  * Включает детали, факты, контекст
  * Заканчивается точкой, грамотный русский
- ⚠️ Если новость НЕ подходит (политика/экономика/спорт/негатив) или ты не можешь составить
  описание — верни в "description_ru" РОВНО символ ❌ (не пиши «я не могу оценить эту новость»).
  Скрипт сам уберёт такие новости из дайджеста.
- Только JSON-массив, без другого текста

ПРИМЕР ВЫВОДА:
[
  {{"index": 0, "category": "goodness", "description_ru": "Волонтеры спасли 500 бездомных собак и открыли новый приют. Проект получил грант, все животные здоровы и получат заботу."}},
  {{"index": 2, "category": "goodness", "description_ru": "В зоопарке родился редкий детёныш панды — первый за десять лет. Сотрудники круглосуточно выхаживают малыша, посетители смогут увидеть его весной."}}
]
"""

        # Get API key
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
                    "max_completion_tokens": 800,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        try:
            # Extract JSON if wrapped in markdown
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()

            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            # Try extracting first [ ... ] block
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if match:
                try:
                    selected_news = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON: {gpt_response[:100]}")
                    return None
            else:
                logger.error(f"No JSON array found in response: {gpt_response[:100]}")
                return None

        # Validate indices and build result
        valid_news = []
        seen_indices = set()

        for item in selected_news:
            if not isinstance(item, dict):
                continue

            idx = item.get("index", -1)

            # Skip duplicates
            if idx in seen_indices:
                logger.debug(f"Skipping duplicate index {idx}")
                continue

            # Validate index
            if not (0 <= idx < len(indexed_news)):
                logger.warning(f"Invalid index {idx} (max {len(indexed_news)-1}), skipping")
                continue

            # Drop items ChatGPT refused/couldn't summarize (returns ❌ or a refusal phrase)
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped good news (GPT reject marker ❌ / refusal): index {idx}")
                continue

            seen_indices.add(idx)
            valid_news.append(item)

        if not valid_news:
            logger.warning("No valid news items selected")
            return None

        logger.info(f"✓ ChatGPT selected {len(valid_news)} good news items")
        for item in valid_news:
            desc = item.get("description_ru", "")[:50]
            logger.info(f"  [{item['index']}] {desc}...")

        return valid_news

    except Exception as e:
        logger.error(f"Failed to process good news with ChatGPT: {type(e).__name__}: {e}")
        return None


async def select_crypto_news_with_summaries(
    crypto_news: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """
    Select ONE most relevant cryptocurrency news item and summarize it in Russian.

    Focus: BTC, ETH, SOL, SUI, UNI and other major cryptocurrencies / DeFi / market moves.

    Returns:
        [{"index": 0, "category": "crypto", "description_ru": "..."}]
        or None if ChatGPT call fails, finds nothing suitable, or returns ❌.
    """
    import os
    from src.utils.doppler import get_secret

    if not crypto_news:
        logger.warning("No crypto news items to process")
        return None

    try:
        # Build indexed news list, removing duplicates by URL.
        # Keep original indices so the scheduler can match them back.
        indexed_news = []
        seen_urls = set()

        for orig_pos, item in enumerate(crypto_news):
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            description = _clean_html(item.get("description", ""))[:500]
            indexed_news.append({
                "index": orig_pos,  # Keep original position in crypto_news
                "title": item.get("title", ""),
                "description": description,
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            })

            if len(indexed_news) >= 15:
                break

        if not indexed_news:
            logger.warning("No unique crypto news items after deduplication")
            return None

        logger.info(f"Processing {len(indexed_news)} unique crypto news items (deduplicated)")

        system_prompt = """You are a crypto market editor who selects ONE most important and interesting cryptocurrency news story.
Priority topics: Bitcoin (BTC), Ethereum (ETH), Solana (SOL), Sui (SUI), Uniswap (UNI) and other major cryptocurrencies, DeFi, ETFs, regulation, significant market moves.
Write a summary in Russian (40-60 words) that captures the essence.
Return ONLY a valid JSON array with a single item."""

        user_prompt = f"""ВЫБЕРИ РОВНО 1 САМУЮ ВАЖНУЮ И ИНТЕРЕСНУЮ КРИПТО-НОВОСТЬ из списка.
Приоритет: BTC, ETH, SOL, SUI, UNI и другие крупные криптовалюты, DeFi, ETF, регулирование, крупные движения рынка.

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
- Выбери ТОЛЬКО 1 новость (самую значимую для крипто-рынка)
- description_ru: ОДНО ПОЛНОЕ описание (40-60 слов на русском)
  * Начинается с главной идеи (не пересказ title)
  * Включает детали, цифры, факты, контекст
  * Заканчивается точкой, грамотный русский
- ⚠️ Если НИ ОДНА новость не подходит (нет реальной крипто-темы, мусор, не можешь оценить) —
  верни в "description_ru" РОВНО символ ❌. Скрипт сам уберёт новость из дайджеста.
- Только JSON-массив, без другого текста

ПРИМЕР ВЫВОДА:
[
  {{"index": 0, "category": "crypto", "description_ru": "Bitcoin превысил 100 тысяч долларов на фоне притока институциональных инвестиций в спотовые ETF. Аналитики связывают рост с ожиданием смягчения политики ФРС и снижением предложения после халвинга."}}
]
"""

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
                    "max_completion_tokens": 400,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        try:
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()

            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if match:
                try:
                    selected_news = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse crypto JSON: {gpt_response[:100]}")
                    return None
            else:
                logger.error(f"No JSON array in crypto response: {gpt_response[:100]}")
                return None

        # Validate and pick the first valid, non-rejected item
        for item in selected_news:
            if not isinstance(item, dict):
                continue
            # idx is the ORIGINAL position in crypto_news (kept through dedup), so
            # validate against crypto_news length, not the deduplicated list length.
            idx = item.get("index", -1)
            if not (0 <= idx < len(crypto_news)):
                logger.warning(f"Invalid crypto index {idx} (max {len(crypto_news)-1}), skipping")
                continue
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped crypto news (GPT reject marker ❌ / refusal): index {idx}")
                continue

            item["category"] = "crypto"
            logger.info(f"✓ ChatGPT selected crypto news: index {idx}")
            return [item]

        logger.info("No suitable crypto news selected (skipping section)")
        return None

    except Exception as e:
        logger.error(f"Failed to process crypto news with ChatGPT: {type(e).__name__}: {e}")
        return None


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
2️⃣ #3: Спорт (из пула "sports") — приоритет ФУТБОЛ, затем хоккей/теннис, или fallback на культуру
3️⃣ #4-5: Культура, технологии (по одной из каждого пула)
4️⃣ #6: ДОБРЫЕ НОВОСТИ (ТОЛЬКО позитив: животные, волонтёрство, достижения, чудеса)

КРИТИЧЕСКИЕ ПРАВИЛА:
- Выбираю ТОЛЬКО из указанного пула для каждой позиции ("available_in")
- ровно 6 новостей, ровно 2 политики, БАН на 3+ политики
- Спорт (позиция #3): приоритет ФУТБОЛ (любые лиги), затем хоккей/теннис
- Позиция #6 (goodness): ТОЛЬКО позитив, БАН на болезни/смерти/войны/трагедии
- Исключения: читаю "ИСКЛЮЧАЮ:" в профиле и ПОЛНОСТЬЮ их игнорирую

FORMAT - ВАЖНО:
- description_ru: одно ПОЛНОЕ, грамотное описание (40-60 слов)
  * Начинается с главной идеи (не дублирует title)
  * Включает конкретные детали (цифры, факты, контекст)
  * Заканчивается полной точкой
  * Без разрывов, без объединения фрагментов
- Текст должен читаться естественно и грамотно
- ⚠️ ЕСЛИ ты НЕ можешь составить нормальное описание новости, или хочешь ОТКЛОНИТЬ новость
  (например, она не подходит по теме, негативная для позиции goodness, или ты не можешь её оценить) —
  верни в поле "description_ru" РОВНО один символ: ❌
  НИКОГДА не пиши фразы вроде "я не могу оценить эту новость" — вместо этого ставь ❌.
  Скрипт сам уберёт такие новости из дайджеста.

Профиль пользователя:
{user_profile_section}
"""

        # Build user prompt with indexed news
        user_prompt = f"""ВЫБЕРИ И ОПИШИ РОВНО 6 НОВОСТЕЙ ПО СХЕМЕ:

Позиция 1 & 2: "available_in": "politics" (2 разные новости)
Позиция 3: "available_in": "sports" — ПРИОРИТЕТ ФУТБОЛ (футбол > хоккей > теннис > другое)
  Если нет футбола — выбери другой спорт. Если спорта совсем нет — fallback на культуру.
Позиция 4: "available_in": "culture"
Позиция 5: "available_in": "technology"
Позиция 6: "available_in": "goodness" — ТОЛЬКО ПОЗИТИВ! (животные, достижения, спасение, волонтёрство)
  БАН: болезни, смерти, трагедии, войны — это будут отклонены!

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ПРАВИЛА:
✅ Точно 6 новостей, ровно 2 политики
✅ Спорт: ФУТБОЛ первым, потом хоккей/теннис/другое (проверь title на "football", "футбол", "soccer")
✅ Последняя (позиция 6) должна быть 100% позитивная или вообще не включай
✅ description_ru: ОДНО ПОЛНОЕ ОПИСАНИЕ (40-60 слов), грамотный русский
   - начинается с НОВОЙ информации (не пересказ title)
   - включает детали, цифры, факты, контекст
   - заканчивается точкой
   - БЕЗ объединения фрагментов, БЕЗ разрывов
✅ Если НЕ можешь описать новость или хочешь её ОТКЛОНИТЬ — поставь в "description_ru" РОВНО: ❌
   (не пиши "я не могу оценить...", только символ ❌ — скрипт удалит новость из дайджеста)
✅ Только JSON, без текста

ПРИМЕР ХОРОШЕГО description_ru:
- ❌ "Импорт сои сокращается. Спрос падает из-за свиней. Конкуренция растет." (разрывы!)
- ✅ "Импорт сои сокращается на 20% из-за сокращения поголовья свиней. Это усилит конкуренцию между американскими и другими экспортёрами на китайском рынке." (полное, грамотное)

[
  {{"index": 0, "category": "politics", "description_ru": "Администрация США ввела новые санкции на нефтяной сектор, затрагивающие более 10 крупных компаний. Шаг был предпринят в ответ на нарушения международного права и экономического эмбарго."}},
  {{"index": 3, "category": "politics", "description_ru": "ЕС и Грузия подписали долгосрочное торговое соглашение, предусматривающее инвестиции в размере 200 млн долларов в развитие портовой инфраструктуры страны на протяжении пяти лет."}},
  {{"index": 7, "category": "sports", "description_ru": "«Барселона» победила «Реал Мадрид» со счётом 2:1 в полуфинале Лиги чемпионов. Команда из Каталонии впервые с 2018 года выходит в финал главного европейского турнира по футболу."}},
  {{"index": 12, "category": "culture", "description_ru": "В лондонском музее открылась выставка русского авангарда с 150 работами из 1920-х годов. Экспозиция будет доступна публике в течение шести месяцев и ожидается повышенный интерес критиков."}},
  {{"index": 15, "category": "technology", "description_ru": "Google представил новый AI алгоритм для обработки видеоконтента, который работает в 10 раз быстрее конкурентов. Инструмент уже доступен бесплатно на платформе Google Cloud."}},
  {{"index": 18, "category": "goodness", "description_ru": "Волонтёрская организация спасла 500 бездомных собак и открыла новый приют с современными условиями. Проект получил грант в размере 50 тысяч долларов, все животные прошли обследование и здоровы."}}
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

            # Drop items ChatGPT refused/couldn't summarize (returns ❌ or a refusal phrase)
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped news (GPT reject marker ❌ / refusal): index {idx}")
                continue

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
            desc = item.get("description_ru", "")[:50]
            logger.info(f"  [{item['index']}] {item['category']}: {desc}...")

        return valid_news

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ChatGPT JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to process news with ChatGPT: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
