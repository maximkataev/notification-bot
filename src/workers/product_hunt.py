"""Fetch top product from Product Hunt."""

import logging
from typing import Optional, Dict, Any
import feedparser
import httpx
import re
from html import unescape

logger = logging.getLogger(__name__)

PRODUCT_HUNT_FEED = "https://www.producthunt.com/feed"


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Remove "Discussion | Link" patterns and similar
    text = re.sub(
        r"\s*(?:Discussion|Comments?|More|Read more|View)\s*\|\s*(?:Link|Discuss|View|Comment)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def get_top_product() -> Optional[Dict[str, Any]]:
    """
    Fetch the most interesting Product Hunt product using GPT evaluation.

    Returns:
        {
            "name": str,
            "url": str,
            "description": str
        }
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.debug(f"Fetching Product Hunt feed: {PRODUCT_HUNT_FEED}")
            response = await client.get(PRODUCT_HUNT_FEED)
            response.raise_for_status()

        feed = feedparser.parse(response.text)

        if not feed.entries:
            logger.warning("No entries found in Product Hunt feed")
            return None

        # Prepare top 10 products for evaluation
        candidates = []
        for i, entry in enumerate(feed.entries[:10]):
            title = entry.get("title", "Unknown")
            summary = entry.get("summary", "")
            description = _clean_html(summary)[:200]
            candidates.append(
                {
                    "index": i,
                    "title": title,
                    "description": description,
                    "url": entry.get("link", ""),
                }
            )

        if len(candidates) < 1:
            logger.warning("No valid candidates in Product Hunt feed")
            return None

        if len(candidates) == 1:
            entry = candidates[0]
            product = {
                "name": entry["title"],
                "url": entry["url"],
                "description": entry["description"],
            }
            logger.info(f"✓ Only one product available: {product['name']}")
            return product

        # Ask GPT to pick the most interesting one
        from openai import AsyncOpenAI
        import os

        def get_openai_client():
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                from src.utils.doppler import get_secret

                api_key = get_secret("OPENAI_API_KEY")
            return AsyncOpenAI(api_key=api_key)

        candidates_text = "\n".join(
            f"{i+1}. {c['title']}\n   {c['description']}"
            for i, c in enumerate(candidates)
        )

        prompt = f"""Из этих {len(candidates)} продуктов выбери САМЫЙ интересный и полезный.

Критерии:
- Инновационность и уникальность идеи
- Практическая полезность для специалиста
- Интересность (не скучные/обычные решения)

Продукты:
{candidates_text}

Ответь ТОЛЬКО номер (1-{len(candidates)}), без объяснений."""

        response = await get_openai_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        choice_text = response.choices[0].message.content.strip()
        try:
            choice_idx = int(choice_text) - 1
            if not (0 <= choice_idx < len(candidates)):
                choice_idx = 0
        except ValueError:
            logger.debug(
                f"Failed to parse GPT choice: {choice_text}, defaulting to first"
            )
            choice_idx = 0

        selected = candidates[choice_idx]
        product = {
            "name": selected["title"],
            "url": selected["url"],
            "description": selected["description"],
        }

        logger.info(
            f"✓ Interesting product (GPT selected #{choice_idx+1}): {product['name']}"
        )
        return product

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch Product Hunt: {type(e).__name__}: {e}")
        return None
