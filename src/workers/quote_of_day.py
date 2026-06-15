"""Generate the wisdom/quote of the day via ChatGPT.

The quote is produced by gpt-5.4-mini (a real, famous quote requested from the
model) — it is NOT picked from a hardcoded list or a quotes API.

RULE: NO HARDCODED FALLBACKS
If the model call fails, return None (no quote section in digest).
Better to skip the block than show fake data.
"""

import logging
import random
from typing import Optional, Dict, Any

from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Themes rotated to keep the daily quote varied (passed to the model, not quotes themselves)
QUOTE_THEMES = [
    "мудрость и философия жизни",
    "успех и достижение целей",
    "мотивация и продуктивность",
    "творчество и инновации",
    "лидерство",
    "стойкость и преодоление трудностей",
    "обучение и саморазвитие",
    "технологии и будущее",
]


async def get_quote_of_day() -> Optional[Dict[str, Any]]:
    """
    Generate an inspirational quote of the day using ChatGPT.

    The model is asked to return a real, well-known quote from a real author
    on a rotating theme. Output is parsed into text + author.

    Returns:
        Dict with "text" and "author", or None if the model call fails.
        NO HARDCODED FALLBACK: better to skip the block than show fake data.
    """
    theme = random.choice(QUOTE_THEMES)

    prompt = f"""Дай одну по-настоящему вдохновляющую и ободряющую цитату дня на тему "{theme}".

ГЛАВНОЕ ТРЕБОВАНИЕ — ТОЛЬКО РЕАЛЬНАЯ ЦИТАТА:
- Цитата должна быть подлинной и реально существующей, дословно принадлежать конкретному настоящему известному автору (философ, учёный, предприниматель, писатель и т.п.).
- КАТЕГОРИЧЕСКИ НЕЛЬЗЯ выдумывать цитату, перефразировать её или приписывать вымышленному/неверному автору.
- Если ты не уверен на 100%, что цитата подлинная и атрибуция верна — НЕ выдавай её, выбери другую, в которой уверен.

КАКОЙ ДОЛЖНА БЫТЬ ЦИТАТА (тон):
- Заряжающей энергией и оптимизмом, чтобы человек прочитал её утром и почувствовал прилив сил и желание действовать.
- Тёплой и ободряющей, дающей надежду и веру в себя, а не сухой или назидательной.
- Глубокой и содержательной — настоящая мудрость, а не банальный лозунг.

Остальные требования:
- Цитата на русском языке (если оригинал на другом языке — дай корректный перевод).
- Текст цитаты — 1-2 предложения, не длиннее 200 символов.
- Не повторяй банальные заезженные цитаты, выбери что-то свежее и содержательное.

Формат ответа строго такой (две строки, без лишнего текста):
ЦИТАТА: <текст цитаты без кавычек>
АВТОР: <имя автора>"""

    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            messages=[
                {
                    "role": "system",
                    "content": "You provide real, accurately-attributed quotes from famous authors in Russian. Never invent quotes or authors.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content.strip()

        text = None
        author = None
        for line in content.splitlines():
            line = line.strip()
            if line.upper().startswith("ЦИТАТА:"):
                text = line.split(":", 1)[1].strip().strip('"«»')
            elif line.upper().startswith("АВТОР:"):
                author = line.split(":", 1)[1].strip().strip('"«»')

        if text and len(text) > 10:
            author = author or "Неизвестный автор"
            logger.info(f"✓ Quote generated (theme: {theme}): {text[:50]}...")
            return {"text": text, "author": author}

        logger.warning(f"Quote parse failed, unexpected format: {content[:120]}")
        return None

    except Exception as e:
        logger.warning(f"Quote generation failed ({type(e).__name__}): {str(e)[:120]}")
        return None
