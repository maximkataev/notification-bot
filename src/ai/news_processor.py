"""Process news through ChatGPT: select and summarize WITHOUT hallucination."""

import asyncio
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


# Shared retelling rules for every summarizer below.
# The summary must be a SEMANTIC SQUEEZE of the story itself — what happened, how it
# works, which numbers were named. When the source text is thin the model drifts into
# "why this matters for you" commentary ("для разработчиков важно, как именно…"), which
# reads like filler and carries no information, so it is banned outright. Facts may come
# ONLY from the supplied title/description: a shorter summary beats an invented one.
_SUMMARY_RULES = """- description_ru: ОДНО ПОЛНОЕ описание (40-70 слов на русском)
  * ЭТО СМЫСЛОВАЯ ВЫЖИМКА САМОЙ НОВОСТИ: что произошло, как это устроено и работает,
    какие названы цифры, имена, детали, причина и последствия — по сути события
  * ЗАПРЕЩЕНЫ рассуждения о значимости и любая вода: «для разработчиков важно…»,
    «это влияет на…», «вопрос в том, как…», «предстоит выяснить», «важно понимать»,
    оценки, прогнозы, риторические вопросы. Вместо такой фразы дай ЕЩЁ ОДИН ФАКТ из новости
  * Факты бери ТОЛЬКО из title/description. Ничего не додумывай: если деталей мало —
    напиши короче (25-30 слов), но не добирай объём домыслами и общими словами
  * Текст = ЗАКОНЧЕННАЯ ЦЕЛЬНАЯ история, а не обрывок вывода или пересказ title
  * Заканчивается точкой, грамотный русский"""

# Style demo shown alongside _SUMMARY_RULES: the same story told wrong (second sentence
# is commentary) and right (second sentence is the mechanism).
_SUMMARY_EXAMPLES = """ЭТАЛОН ПЕРЕСКАЗА:
- ❌ «Anthropic раскрыла детали новой системы водяных знаков для Claude. Для разработчиков важно, как именно метки будут работать с кодом и можно ли будет их скрыть.» — вторая фраза это рассуждение о важности, а не факт из новости
- ✅ «Anthropic раскрыла детали системы водяных знаков для Claude: при генерации модель по секретному ключу слегка смещает выбор слов, и детектор компании находит этот статистический след в тексте. По словам Anthropic, метка переживает мелкую правку и пропадает только после глубокого переписывания.» — та же новость, но вместо рассуждений дана суть механизма
- ✅ «Starbucks Korea закрывает более 2 000 кофеен на один день, чтобы провести для сотрудников обязательный урок по современной истории страны. Решение обойдётся компании примерно в 2,1 млрд вон выручки. Причина — сотрудник сеульской кофейни оскорбил посетителя, сравнив его с северокорейцем.»
- ❌ «Импорт сои сокращается. Спрос падает из-за свиней. Конкуренция растёт.» — разрывы, набор обрывков"""


async def _rewrite_from_article(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    title: str,
    source: str,
    article_text: str,
) -> Optional[str]:
    """Re-summarize one story from its full article text. None keeps the old text."""
    system_prompt = (
        "Ты редактор новостного дайджеста. По полному тексту статьи пишешь ОДНО описание "
        "новости на русском — смысловую выжимку сути. Возвращаешь ТОЛЬКО текст описания: "
        "без JSON, без кавычек, без заголовков и пояснений."
    )
    user_prompt = f"""ЗАГОЛОВОК: {title}
ИСТОЧНИК: {source}

ТЕКСТ СТАТЬИ:
{article_text}

ЗАДАЧА: напиши описание этой новости для утреннего дайджеста.
{_SUMMARY_RULES}
  * ОБЯЗАТЕЛЬНО раскрой СУТЬ: как именно это работает или устроено, что конкретно
    сделано, ключевые цифры и детали — то, чего НЕТ в заголовке. Читатель не пойдёт
    по ссылке, описание должно объяснить механизм само по себе
  * Используй ТОЛЬКО факты из текста статьи выше

{_SUMMARY_EXAMPLES}

Верни только текст описания."""

    try:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-5.4-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
                "max_completion_tokens": 400,
            },
        )
        if response.status_code != 200:
            logger.warning(f"Article rewrite API error: {response.status_code}")
            return None

        text = response.json()["choices"][0]["message"]["content"].strip()
        text = text.strip('"“”«» \n')
        # A model that ignored "plain text" may answer with JSON — do not show that.
        if text.startswith(("{", "[")):
            return None
        if _is_rejected_description(text) or len(text) < 80:
            return None
        return text

    except Exception as e:
        logger.warning(f"Article rewrite failed: {type(e).__name__}: {e}")
        return None


async def _enrich_with_article_facts(
    valid_news: List[Dict[str, Any]],
    item_by_index: Dict[int, Dict[str, Any]],
) -> None:
    """Second pass: rewrite each summary from the FULL article text, in place.

    The first pass only ever sees the RSS lede, so summaries restate the headline and
    pad with "why this matters" filler. Here the article body is fetched and the story
    is re-told from it, which is where the actual mechanism and numbers live.

    Best-effort: any story whose page cannot be read (paywall, 403, JS shell) or whose
    rewrite fails keeps its original description. Never raises.
    """
    import os
    from src.utils.doppler import get_secret
    from src.workers.article_fetcher import fetch_article_texts

    try:
        urls = [
            item_by_index[item["index"]].get("url", "")
            for item in valid_news
            if item.get("index") in item_by_index
        ]
        texts = await fetch_article_texts(urls)
        if not texts:
            return

        api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")

        async with httpx.AsyncClient(timeout=40.0) as client:
            targets = []
            for item in valid_news:
                original = item_by_index.get(item.get("index"))
                if not original:
                    continue
                article_text = texts.get(original.get("url", ""))
                if not article_text:
                    continue
                targets.append((item, original, article_text))

            if not targets:
                return

            rewrites = await asyncio.gather(
                *(
                    _rewrite_from_article(
                        client,
                        api_key,
                        title=original.get("title", ""),
                        source=original.get("source", ""),
                        article_text=article_text,
                    )
                    for _, original, article_text in targets
                ),
                return_exceptions=True,
            )

        deepened = 0
        for (item, _, _), rewritten in zip(targets, rewrites):
            if isinstance(rewritten, str) and rewritten:
                item["description_ru"] = rewritten
                deepened += 1

        logger.info(
            f"✓ Deepened {deepened}/{len(valid_news)} summaries from article text"
        )

    except Exception as e:
        logger.warning(f"Article enrichment skipped: {type(e).__name__}: {e}")


async def select_themed_news_with_summaries(
    business_news: List[Dict[str, Any]],
    art_news: List[Dict[str, Any]],
    fashion_news: List[Dict[str, Any]],
    good_news: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Themed news for Юля: business / art / fashion / good news only.

    The four pools are concatenated in this exact order (business + art + fashion +
    good) and each item gets a GLOBAL index into that combined list, so the caller
    must rebuild the combined list the same way to resolve source/url.

    Returns:
        [{"index": <global>, "category": "business|art|fashion|goodness",
          "description_ru": "..."}, ...]
        or None if the ChatGPT call fails / nothing suitable.
    """
    import os
    from src.utils.doppler import get_secret

    pools = [
        ("business", business_news),
        ("art", art_news),
        ("fashion", fashion_news),
        ("goodness", good_news),
    ]
    if not any(news for _, news in pools):
        logger.warning("No themed news items to process")
        return None

    try:
        # Build a single indexed list with global indices + a category tag.
        indexed_news = []
        item_by_index = {}  # global index -> original item (for the article pass)
        idx = 0
        for category_name, news_list in pools:
            for item in news_list:
                description = _clean_html(item.get("description", ""))[:800]
                indexed_news.append({
                    "index": idx,
                    "title": item.get("title", ""),
                    "description": description,
                    "source": item.get("source", ""),
                    "available_in": category_name,
                })
                item_by_index[idx] = item
                idx += 1

        logger.info(f"Themed news pool: {len(indexed_news)} items "
                    f"(business {len(business_news)}, art {len(art_news)}, "
                    f"fashion {len(fashion_news)}, good {len(good_news)})")

        system_prompt = """You are an editor of a personal digest for a reader who only wants:
business & economy, art & culture, fashion, and genuinely good/uplifting news.
You STRICTLY REJECT politics, war, conflict, crime, sports, and technology/gadgets.
Pick ONLY from the pool indicated by each item's "available_in" tag.
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description. Return ONLY a valid JSON array."""

        user_prompt = f"""ВЫБЕРИ ДО 6 НОВОСТЕЙ по темам пользователя: бизнес, искусство, мода, добрые новости.

РАСПРЕДЕЛЕНИЕ (старайся охватить все 4 темы, можно меньше если в пуле пусто):
- 2 новости бизнес/экономика (из пула "business")
- 1 новость искусство/культура (из пула "art")
- 2 новости мода (из пула "fashion")
- 1 ДОБРАЯ новость (из пула "goodness": животные, доброта, спасения, вдохновляющее)

СТРОГО ЗАПРЕЩЕНО: политика, война, конфликты, преступления, спорт, технологии/гаджеты.

NEWS:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
- Выбирай ТОЛЬКО из пула, указанного в "available_in" для нужной темы
{_SUMMARY_RULES}
- ⚠️ Если новость не подходит по теме или ты не можешь составить описание —
  верни в "description_ru" РОВНО символ ❌ (скрипт уберёт её из дайджеста)
- Только JSON-массив, без другого текста

{_SUMMARY_EXAMPLES}

ПРИМЕР ВЫВОДА:
[
  {{"index": 0, "category": "business", "description_ru": "Европейские фондовые рынки обновили исторический максимум после соглашения о снижении пошлин. Инвесторы ждут смягчения политики ЦБ, акции технологического и банковского секторов выросли на 2%."}},
  {{"index": 5, "category": "art", "description_ru": "В Лондоне открылась ретроспектива фотографа Дона Маккаллина с работами о войне и человеческой стойкости. Выставка собрала более 200 снимков и продлится полгода."}},
  {{"index": 9, "category": "fashion", "description_ru": "Дом моды представил коллекцию resort 2027, вдохновлённую японским минимализмом. Дизайнеры сделали ставку на природные ткани и спокойную палитру, показ прошёл в Токио."}},
  {{"index": 14, "category": "goodness", "description_ru": "Волонтёры спасли 500 бездомных собак и открыли новый приют с современными условиями. Проект получил грант, все животные здоровы и получат заботу."}}
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
                    "max_completion_tokens": 900,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        try:
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()
            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if not match:
                logger.error(f"No JSON array in themed response: {gpt_response[:100]}")
                return None
            try:
                selected_news = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse themed JSON: {gpt_response[:100]}")
                return None

        valid_news = []
        seen_indices = set()
        for item in selected_news:
            if not isinstance(item, dict):
                continue
            i = item.get("index", -1)
            if not (0 <= i < len(indexed_news)) or i in seen_indices:
                continue
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped themed news (reject marker ❌): index {i}")
                continue
            seen_indices.add(i)
            valid_news.append(item)

        if not valid_news:
            logger.warning("No valid themed news items selected")
            return None

        logger.info(f"✓ ChatGPT selected {len(valid_news)} themed news items")
        await _enrich_with_article_facts(valid_news, item_by_index)
        return valid_news

    except Exception as e:
        logger.error(f"Failed to process themed news with ChatGPT: {type(e).__name__}: {e}")
        return None


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
            description = _clean_html(description)[:800]

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
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description. Return ONLY a valid JSON array."""

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
{_SUMMARY_RULES}
- ⚠️ Если новость НЕ подходит (политика/экономика/спорт/негатив) или ты не можешь составить
  описание — верни в "description_ru" РОВНО символ ❌ (не пиши «я не могу оценить эту новость»).
  Скрипт сам уберёт такие новости из дайджеста.
- Только JSON-массив, без другого текста

{_SUMMARY_EXAMPLES}

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

        # Indices are original positions in goodness_news (kept through dedup).
        await _enrich_with_article_facts(valid_news, dict(enumerate(goodness_news)))
        return valid_news

    except Exception as e:
        logger.error(f"Failed to process good news with ChatGPT: {type(e).__name__}: {e}")
        return None


async def select_crypto_news_with_summaries(
    crypto_news: List[Dict[str, Any]],
    count: int = 2,
) -> Optional[List[Dict[str, Any]]]:
    """Select crypto news for an ACTIVE TRADER of BTC, ETH and SOL.

    The bar is tradability, not general interest: price moves with a stated cause,
    ETF/institutional flows, derivatives positioning, regulation and network events
    that touch those three coins. Explainers, altcoin hype and anonymous price
    predictions are rejected outright.

    Returns:
        [{"index": <pos in crypto_news>, "category": "crypto", "description_ru": "..."}]
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

            description = _clean_html(item.get("description", ""))[:800]
            entry = {
                "index": orig_pos,  # Keep original position in crypto_news
                "title": item.get("title", ""),
                "description": description,
                "source": item.get("source", ""),
                "url": item.get("url", ""),
            }
            # Coin tags come from TradingView's symbol feeds — a hard signal that the
            # story is about a position the trader actually holds.
            if item.get("coins"):
                entry["coins"] = item["coins"]
            indexed_news.append(entry)

            if len(indexed_news) >= 30:
                break

        if not indexed_news:
            logger.warning("No unique crypto news items after deduplication")
            return None

        logger.info(f"Processing {len(indexed_news)} unique crypto news items (deduplicated)")

        system_prompt = """You are a crypto editor for an ACTIVE TRADER who trades Bitcoin (BTC), Ethereum (ETH) and Solana (SOL).
You select stories that can move the price of those three coins or that the trader can act on.
You REJECT explainers and educational columns ("how blockchain works"), altcoin/memecoin/NFT hype,
airdrops, press releases, exchange promos and anonymous price predictions with no data behind them.
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description.
Return ONLY a valid JSON array."""

        user_prompt = f"""ВЫБЕРИ {count} КРИПТО-НОВОСТИ, ПОЛЕЗНЫЕ ДЛЯ АКТИВНОГО ТРЕЙДЕРА BTC, ETH и SOL.

ЧТО ЦЕННО (по убыванию):
1. Движения цены BTC/ETH/SOL с названной причиной: пробои уровней, ликвидации, объёмы, волатильность
2. Потоки денег: спотовые ETF (притоки/оттоки), покупки институционалов и компаний-казначейств,
   активность китов и майнеров, переводы на биржи и с бирж, эмиссия стейблкоинов
3. Деривативы и позиционирование: фандинг, открытый интерес, экспирации опционов, шорт/лонг-сквизы
4. Макро с прямым эффектом на риск-активы: ФРС и ставки, инфляция, доллар (DXY), ликвидность
5. Регулирование и инфраструктура: решения SEC/регуляторов по ETF, листинги, взломы и сбои бирж,
   апгрейды и сбои сетей Ethereum и Solana, доходность стейкинга

ЧТО ОТКЛОНЯТЬ ВСЕГДА:
- Обучалки и объяснялки («как работает блокчейн», «почему у блокчейна нет времени», гайды, ликбез)
- Хайп мелких альткоинов, мемкоины, NFT, GameFi, аирдропы, реклама и пресс-релизы бирж
- Прогнозы без данных («биткоин до $250 000 к декабрю»), гадания по графикам от анонимов
- Новости про монеты, которые никак не влияют на BTC, ETH и SOL

ПРИОРИТЕТ: у новостей с полем "coins" (BTC/ETH/SOL) приоритет — они про активы трейдера.
Новости должны быть РАЗНЫЕ: не две про одно и то же событие.

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
- Выбери до {count} новостей (лучше 1 отличная, чем 2 с натяжкой)
{_SUMMARY_RULES}
  * Обязательно сохрани ТОРГОВУЮ КОНКРЕТИКУ из статьи: уровни цен, объёмы, суммы потоков,
    проценты, даты и сроки — трейдеру нужны цифры, а не общие слова
- ⚠️ Если новость не подходит (ликбез, хайп, нет реальной торговой сути, не можешь оценить) —
  верни в "description_ru" РОВНО символ ❌. Скрипт сам уберёт новость из дайджеста.
- Только JSON-массив, без другого текста

{_SUMMARY_EXAMPLES}

ПРИМЕР ВЫВОДА:
[
  {{"index": 0, "category": "crypto", "description_ru": "Спотовые биткоин-ETF за неделю потеряли $1,2 млрд — крупнейший отток с марта, основная часть пришлась на FBTC и GBTC. BTC на этом фоне терял 6% и тестировал $92 000, объём ликвидаций длинных позиций за сутки составил $480 млн."}},
  {{"index": 4, "category": "crypto", "description_ru": "Разработчики Ethereum назначили апгрейд Hegotá на март и включили в него FOCIL. Изменение затрагивает порядок включения транзакций в блок; в тестовой сети запуск запланирован на январь."}}
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
                    "max_completion_tokens": 300 + 250 * count,
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

        # Only indices actually shown to the model are acceptable: the pool is capped,
        # so a larger in-range index would resolve to a story ChatGPT never saw.
        offered_indices = {entry["index"] for entry in indexed_news}

        selected = []
        seen_indices = set()
        for item in selected_news:
            if not isinstance(item, dict):
                continue
            idx = item.get("index", -1)
            if idx not in offered_indices or idx in seen_indices:
                logger.warning(f"Invalid/duplicate crypto index {idx}, skipping")
                continue
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped crypto news (GPT reject marker ❌ / refusal): index {idx}")
                continue

            seen_indices.add(idx)
            item["category"] = "crypto"
            selected.append(item)
            if len(selected) >= count:
                break

        if selected:
            logger.info(f"✓ ChatGPT selected {len(selected)} crypto news item(s)")
            await _enrich_with_article_facts(selected, dict(enumerate(crypto_news)))
            return selected

        logger.info("No suitable crypto news selected (skipping section)")
        return None

    except Exception as e:
        logger.error(f"Failed to process crypto news with ChatGPT: {type(e).__name__}: {e}")
        return None


async def select_stocks_news_with_summaries(
    stocks_news: List[Dict[str, Any]],
    count: int = 1,
) -> Optional[List[Dict[str, Any]]]:
    """Select US stock market news for someone who holds S&P 500 / Nasdaq funds.

    Returns:
        [{"index": <pos in stocks_news>, "category": "stocks", "description_ru": "..."}]
        or None when nothing suitable was found (the section is then skipped).
    """
    import os
    from src.utils.doppler import get_secret

    if not stocks_news:
        logger.warning("No stocks news items to process")
        return None

    try:
        indexed_news = []
        seen_urls = set()

        for orig_pos, item in enumerate(stocks_news):
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            entry = {
                "index": orig_pos,
                "title": item.get("title", ""),
                "description": _clean_html(item.get("description", ""))[:800],
                "source": item.get("source", ""),
                "published": item.get("published"),
            }
            if item.get("tickers"):
                entry["tickers"] = item["tickers"]
            indexed_news.append(entry)

            if len(indexed_news) >= 30:
                break

        if not indexed_news:
            logger.warning("No unique stocks news items after deduplication")
            return None

        logger.info(f"Processing {len(indexed_news)} unique stocks news items (deduplicated)")

        system_prompt = """You are a US equities editor for an investor who follows the S&P 500 and Nasdaq
and holds index funds (SPY/QQQ-style) alongside large-cap single names.
You select what moved or will move the US market: index sessions with a stated driver, Fed and macro data,
earnings from index heavyweights, fund flows, and notable single-stock moves inside the index.
You REJECT explainers and personal-finance advice ("how to build a portfolio", "the best diet"),
penny stocks, promotional analyst listicles with no data, crypto (covered elsewhere) and lifestyle stories.
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description.
Return ONLY a valid JSON array."""

        user_prompt = f"""ВЫБЕРИ {count} НОВОСТЬ ПРО РЫНОК АКЦИЙ США, полезную инвестору в S&P 500 и Nasdaq.

ЧТО ЦЕННО (по убыванию):
1. Итоги и движение индексов S&P 500, Nasdaq, Dow с названной ПРИЧИНОЙ (данные, ставки, отчёты)
2. ФРС и макро: ставки, инфляция, безработица, розничные продажи, доходности трежерис, доллар
3. Отчётности тяжеловесов индекса (Nvidia, Apple, Microsoft, Alphabet, Amazon и т.п.) и их эффект на индекс
4. Потоки в фонды и ETF, позиционирование крупных игроков, крупные сделки и байбэки
5. Резкие движения отдельных крупных бумаг из индекса с объяснением причины

ЧТО ОТКЛОНЯТЬ ВСЕГДА:
- Личные финансы и лайфстайл («как копить», «лучшая диета», ипотека, советы читателям)
- Подборки «аналитики любят эти 3 дивидендные акции» без данных и без причины
- Мелкие компании, пенни-стоки, промо и пресс-релизы
- Крипто (для неё отдельная секция дайджеста)

Свежесть важна: при прочих равных выбирай новость с самой поздней датой в поле "published".
У новостей с полем "tickers" (SPX/SPY/QQQ) приоритет — они привязаны к индексу напрямую.

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
- Выбери до {count} новостей (лучше ни одной, чем неподходящую)
{_SUMMARY_RULES}
  * Обязательно сохрани КОНКРЕТИКУ: уровни индексов, проценты, суммы, даты, цифры отчётов
- ⚠️ Если новость не подходит (лайфстайл, личные финансы, реклама, нет рыночной сути) —
  верни в "description_ru" РОВНО символ ❌. Скрипт сам уберёт новость из дайджеста.
- Только JSON-массив, без другого текста

{_SUMMARY_EXAMPLES}

ПРИМЕР ВЫВОДА:
[
  {{"index": 2, "category": "stocks", "description_ru": "S&P 500 закрылся на 0,4% выше и обновил максимум после данных по розничным продажам, которые выросли на 0,6% против ожидаемых 0,3%. Nasdaq прибавил 0,8% на фоне роста Nvidia на 3%; доходность десятилетних трежерис снизилась до 4,1%."}}
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
                    "max_completion_tokens": 300 + 250 * count,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        try:
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()
            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if not match:
                logger.error(f"No JSON array in stocks response: {gpt_response[:100]}")
                return None
            try:
                selected_news = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse stocks JSON: {gpt_response[:100]}")
                return None

        offered_indices = {entry["index"] for entry in indexed_news}

        selected = []
        seen_indices = set()
        for item in selected_news:
            if not isinstance(item, dict):
                continue
            idx = item.get("index", -1)
            if idx not in offered_indices or idx in seen_indices:
                logger.warning(f"Invalid/duplicate stocks index {idx}, skipping")
                continue
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped stocks news (reject marker ❌ / refusal): index {idx}")
                continue

            seen_indices.add(idx)
            item["category"] = "stocks"
            selected.append(item)
            if len(selected) >= count:
                break

        if selected:
            logger.info(f"✓ ChatGPT selected {len(selected)} stocks news item(s)")
            await _enrich_with_article_facts(selected, dict(enumerate(stocks_news)))
            return selected

        logger.info("No suitable stocks news selected (skipping section)")
        return None

    except Exception as e:
        logger.error(f"Failed to process stocks news with ChatGPT: {type(e).__name__}: {e}")
        return None


async def _select_local_news(
    news: List[Dict[str, Any]],
    *,
    region: str,
    region_rule: str,
    count: int,
    good_only: bool,
    category: str,
) -> Optional[List[Dict[str, Any]]]:
    """Select up to `count` local (city/country) news items and summarize in Russian.

    Shared implementation behind the Georgia / Tbilisi / Vienna sections. The pools
    are regional feeds that also carry neighbouring-country and hard-news items, so
    ChatGPT does the geographic filtering (`region_rule`) and, when `good_only`,
    the "is this actually uplifting" filtering too.

    Feeds may be in Georgian or German — summaries are always Russian.

    Returns:
        [{"index": <position in `news`>, "category": category, "description_ru": "..."}]
        or None when the call fails or nothing suitable was found (section is then
        skipped entirely — never padded).
    """
    import os
    from src.utils.doppler import get_secret

    if not news:
        logger.warning(f"No {category} news items to process")
        return None

    try:
        # Keep original positions so the scheduler can resolve source/url back.
        indexed_news = []
        seen_urls = set()

        for orig_pos, item in enumerate(news):
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            indexed_news.append({
                "index": orig_pos,
                "title": item.get("title", ""),
                "description": _clean_html(item.get("description", ""))[:800],
                "source": item.get("source", ""),
            })

            if len(indexed_news) >= 30:
                break

        if not indexed_news:
            logger.warning(f"No unique {category} news items after deduplication")
            return None

        logger.info(f"Processing {len(indexed_news)} unique {category} news items (deduplicated)")

        if good_only:
            # The bar is "pleasant to read over breakfast", NOT "extraordinary".
            # An earlier, harsher wording made the model reject entire pools that
            # clearly held festivals, openings and community stories, so the rule
            # is now: reject by TOPIC (the ban list), not by how remarkable the
            # story is. Everyday warm city life is exactly what this slot wants.
            system_prompt = f"""You are an editor picking pleasant, positive local news about {region}
for a reader who enjoys warm everyday city stories over morning coffee.
GOOD (all of this counts, it does NOT have to be extraordinary): culture, exhibitions, festivals,
concerts, city life, new places and openings, restorations, parks and nature, animals, people helping
people, volunteering, education and science achievements, touching human-interest stories, traditions,
anniversaries, urban improvements.
REJECT ONLY by topic: politics, government, elections, protests, courts, war, crime, police, accidents,
disasters, economy/markets, scandals, deaths, illness, and sports results.
If several stories qualify, pick the warmest and most interesting one.
Return an empty array ONLY if literally every item in the list is on the reject list.
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description. Sources may be in Georgian or German — always answer in Russian.
Return ONLY a valid JSON array."""
            task_line = (
                f"ВЫБЕРИ {count} ПРИЯТНУЮ, ДОБРУЮ НОВОСТЬ про {region}.\n\n"
                "ПОДХОДИТ (не обязана быть выдающейся — обычная тёплая городская новость это ровно то, "
                "что нужно): культура, выставки, фестивали, концерты, городская жизнь, новые места и "
                "открытия, реставрации, парки и природа, животные, люди помогают людям, волонтёрство, "
                "образование и наука, трогательные человеческие истории, традиции, юбилеи, "
                "благоустройство города.\n"
                "ОТКЛОНЯЙ ТОЛЬКО ПО ТЕМЕ: политика, власть, выборы, протесты, суды, война, преступления, "
                "полиция, аварии, катастрофы, экономика/рынки, скандалы, смерти, болезни, спорт.\n"
                "Если подходящих несколько — выбери самую тёплую и интересную.\n"
                "⚠️ Пустой массив [] возвращай ТОЛЬКО если ВСЕ новости из списка попадают в запрещённые темы."
            )
        else:
            system_prompt = f"""You are an editor picking the most important and interesting local news about {region}
for a reader who lives there: politics, economy, city life, infrastructure, society, culture, notable events.
Skip trivia, gossip, celebrity and pure sports results.
For each chosen item write a Russian summary (40-70 words) that is a factual GIST of the story itself — what happened, how it works, the named numbers and details. Never write why-it-matters commentary, and never invent facts that are not in the supplied title/description. Sources may be in Georgian or German — always answer in Russian.
Return ONLY a valid JSON array."""
            task_line = (
                f"ВЫБЕРИ {count} САМЫЕ ВАЖНЫЕ И ИНТЕРЕСНЫЕ НОВОСТИ про {region} "
                "(политика, экономика, город, инфраструктура, общество, культура, заметные события).\n"
                "Новости должны быть РАЗНЫЕ по теме — не две про одно и то же событие.\n"
                "Пропускай сплетни, знаменитостей и чистые спортивные результаты."
            )

        user_prompt = f"""{task_line}

ГЕОГРАФИЯ — ОБЯЗАТЕЛЬНО: {region_rule}

НОВОСТИ:
{json.dumps(indexed_news, ensure_ascii=False, indent=2)}

ТРЕБОВАНИЯ:
{_SUMMARY_RULES}
  * Пиши НА РУССКОМ, даже если источник на грузинском или немецком
- ⚠️ Если новость не подходит по географии/теме или ты не можешь составить описание —
  верни в "description_ru" РОВНО символ ❌ (скрипт уберёт её из дайджеста).
  НИКОГДА не пиши «я не могу оценить эту новость».
- Только JSON-массив, без другого текста

{_SUMMARY_EXAMPLES}

ПРИМЕР ВЫВОДА:
[
  {{"index": 3, "category": "{category}", "description_ru": "Мэрия начала реставрацию исторических балконов в районе Сололаки: за год приведут в порядок 40 фасадов. Работы финансирует город вместе с частным фондом, жильцам помогают восстановить резные детали по старым чертежам."}}
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
                    "max_completion_tokens": 300 + 250 * count,
                },
            )

        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        gpt_response = data["choices"][0]["message"]["content"].strip()

        try:
            if "```json" in gpt_response:
                gpt_response = gpt_response.split("```json")[1].split("```")[0].strip()
            elif "```" in gpt_response:
                gpt_response = gpt_response.split("```")[1].split("```")[0].strip()
            selected_news = json.loads(gpt_response)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", gpt_response, re.DOTALL)
            if not match:
                logger.error(f"No JSON array in {category} response: {gpt_response[:100]}")
                return None
            try:
                selected_news = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse {category} JSON: {gpt_response[:100]}")
                return None

        if not isinstance(selected_news, list):
            logger.error(f"{category} response is not a list: {gpt_response[:100]}")
            return None

        # Only indices actually shown to the model are acceptable: the pool is
        # capped at 30 items, so a larger in-range index would silently resolve to
        # a story ChatGPT never saw and pair it with the wrong source/url.
        offered_indices = {entry["index"] for entry in indexed_news}

        valid_news = []
        seen_indices = set()

        for item in selected_news:
            if not isinstance(item, dict):
                continue
            idx = item.get("index", -1)
            if idx not in offered_indices or idx in seen_indices:
                logger.warning(f"Invalid/duplicate {category} index {idx}, skipping")
                continue
            if _is_rejected_description(item.get("description_ru", "")):
                logger.info(f"  ⛔ Dropped {category} news (reject marker ❌ / refusal): index {idx}")
                continue
            seen_indices.add(idx)
            item["category"] = category
            valid_news.append(item)
            if len(valid_news) >= count:
                break

        if not valid_news:
            logger.info(f"No suitable {category} news selected (section skipped)")
            return None

        logger.info(f"✓ ChatGPT selected {len(valid_news)} {category} news items")
        await _enrich_with_article_facts(valid_news, dict(enumerate(news)))
        return valid_news

    except Exception as e:
        logger.error(f"Failed to process {category} news with ChatGPT: {type(e).__name__}: {e}")
        return None


# Geography rules reused by the regional selectors. The Caucasus feeds (OC Media,
# JAMnews) mix in Armenia/Azerbaijan/North Caucasus, so this filter carries weight.
_GEORGIA_RULE = (
    "новость должна быть ПРО ГРУЗИЮ (Тбилиси, Батуми, грузинская политика, экономика, "
    "общество, культура). Новости про Армению, Азербайджан, Чечню, Дагестан, Россию и "
    "другие страны — ОТКЛОНЯЙ, даже если они из того же источника."
)
_VIENNA_RULE = (
    "новость должна быть ПРО ВЕНУ или её районы (можно про Австрию, если событие "
    "напрямую касается Вены). Международные и общемировые новости — ОТКЛОНЯЙ."
)


async def select_georgia_news_with_summaries(
    georgia_news: List[Dict[str, Any]],
    count: int = 2,
) -> Optional[List[Dict[str, Any]]]:
    """Select `count` general Georgia/Tbilisi news items (Максим)."""
    return await _select_local_news(
        georgia_news,
        region="Грузию и Тбилиси",
        region_rule=_GEORGIA_RULE,
        count=count,
        good_only=False,
        category="georgia",
    )


async def select_georgia_good_news_with_summaries(
    georgia_news: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Select ONE good Georgia news item, Tbilisi preferred (Маша). None if there is none."""
    return await _select_local_news(
        georgia_news,
        region="Грузию, и особенно Тбилиси (новости про Тбилиси имеют приоритет)",
        region_rule=_GEORGIA_RULE,
        count=1,
        good_only=True,
        category="georgia_good",
    )


async def select_vienna_good_news_with_summaries(
    vienna_news: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Select ONE good Vienna news item (Юля). None if there is none."""
    return await _select_local_news(
        vienna_news,
        region="Вену",
        region_rule=_VIENNA_RULE,
        count=1,
        good_only=True,
        category="vienna_good",
    )


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
                description = _clean_html(description)[:800]

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
{_SUMMARY_RULES}
  * Без разрывов, без объединения фрагментов — текст читается естественно и грамотно

{_SUMMARY_EXAMPLES}

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
{_SUMMARY_RULES}
✅ Если НЕ можешь описать новость или хочешь её ОТКЛОНИТЬ — поставь в "description_ru" РОВНО: ❌
   (не пиши "я не могу оценить...", только символ ❌ — скрипт удалит новость из дайджеста)
✅ Только JSON, без текста

{_SUMMARY_EXAMPLES}

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

                # Normalize category back onto the item so downstream consumers
                # (this logger + scheduler) can rely on item["category"] existing
                # even when ChatGPT omits the field for some items.
                item["category"] = category
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
            logger.info(f"  [{item.get('index')}] {item.get('category', 'unknown')}: {desc}...")

        await _enrich_with_article_facts(
            valid_news, {i: original for i, (_, original) in idx_to_original.items()}
        )
        return valid_news

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ChatGPT JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to process news with ChatGPT: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
