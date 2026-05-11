"""Filter and select real news by keywords - NO AI generation, only real RSS data."""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default prompt (displayed when user hasn't set custom)
DEFAULT_NEWS_PROMPT = "Выбрать новости, релевантные для инвестора и трейдера"

# Keywords for main news (economics, trading, geopolitics affecting markets)
MAIN_NEWS_KEYWORDS = [
    "stock",
    "market",
    "currency",
    "exchange",
    "rate",
    "price",
    "rub",
    "gel",
    "usd",
    "eur",
    "crypto",
    "bitcoin",
    "ethereum",
    "sanctions",
    "tariff",
    "trade",
    "economy",
    "inflation",
    "interest rate",
    "bank",
    "federal reserve",
    "ecb",
    "central bank",
    "gdp",
    "earnings",
    "profit",
    "loss",
    "quarterly",
    "quarterly earnings",
    "oil",
    "gas",
    "energy",
    "commodity",
    "valuation",
    "ipo",
    "merger",
    "acquisition",
    "fed",
    "bernanke",
    "powell",
    "geopolitics",
    "iran",
    "russia",
    "war",
    "conflict",
    "middle east",
    "ukraine",
    "gaza",
    "strait of hormuz",
    "navigation",
    "russian",
    "moscow",
    "siberia",
    "gazprom",
    "rosneft",
    "sberbank",
    "yandex",
    "georgia",
    "tbilisi",
    "caucasus",
    "caspian",
    "defense",
    "military",
]

# Keywords for sports news
SPORTS_NEWS_KEYWORDS = [
    "barcelona",
    "psg",
    "football",
    "soccer",
    "goal",
    "match",
    "score",
    "win",
    "loss",
    "transfer",
    "player",
    "coach",
    "league",
    "premier league",
    "la liga",
    "serie a",
    "champions league",
    "europa league",
    "hockey",
    "ice hockey",
    "nfl",
    "nba",
]

# Keywords for good news (positive)
GOOD_NEWS_KEYWORDS = [
    "rescue",
    "saved",
    "discovery",
    "breakthrough",
    "cure",
    "vaccine",
    "medical",
    "travel",
    "visa",
    "border",
    "open",
    "festival",
    "award",
    "achievement",
    "help",
    "charity",
    "donate",
    "animals",
    "environment",
    "green",
    "recovery",
    "russia",
    "georgian",
    "russian",
    "ukraine",
    "cyprus",
]


def _match_keywords(text: str, keywords: List[str]) -> bool:
    """Check if text contains any keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def _extract_exclusion_keywords(custom_prompt: str) -> List[str]:
    """
    Parse custom prompt to extract exclusion keywords.
    Looks for patterns like:
    - "Я НЕ выбираю ... ИСКЛЮЧАЮ: item1, item2, item3"
    - Returns list of lowercase keywords to exclude
    """
    if not custom_prompt:
        return []

    # Find the exclusion section after "ИСКЛЮЧАЮ:" or "ИСКЛЮЧУ:"
    lower_prompt = custom_prompt.lower()
    exclude_start = lower_prompt.find("исключаю:")

    if exclude_start == -1:
        exclude_start = lower_prompt.find("исключу:")

    if exclude_start == -1:
        return []

    # Extract text after "ИСКЛЮЧАЮ:"
    exclude_text = custom_prompt[exclude_start + 9 :]  # len("исключаю:") = 9

    # Split by comma and parentheses, clean up
    import re

    items = re.split(r"[,()]+", exclude_text)

    keywords = []
    for item in items:
        cleaned = item.strip().lower()
        if cleaned and len(cleaned) > 2:  # Skip empty or very short items
            keywords.append(cleaned)

    logger.info(
        f"Extracted {len(keywords)} exclusion keywords from custom prompt: {keywords[:5]}..."
    )
    return keywords


async def select_and_summarize_news(
    news_items: List[Dict[str, Any]],
    custom_prompt: Optional[str] = None,
    exclude_urls: Optional[set] = None,
) -> Optional[List[Dict[str, str]]]:
    """
    Filter real news by relevance keywords. NO AI - only real data from RSS.
    Applies custom prompt exclusion keywords if provided.
    Returns 2 most relevant news items (excluding already selected ones).
    """
    if not news_items:
        logger.info("No news items to process")
        return None

    exclude_urls = exclude_urls or set()
    exclusion_keywords = (
        _extract_exclusion_keywords(custom_prompt) if custom_prompt else []
    )

    logger.info(
        f"Filtering {len(news_items)} news items for main news relevance (excluding {len(exclude_urls)} already selected)"
    )

    # Filter by main news keywords, excluding already selected
    matching_news = []
    for item in news_items:
        if item.get("url") in exclude_urls:
            continue

        title_and_desc = f"{item.get('title', '')} {item.get('description', '')}"
        text_lower = title_and_desc.lower()

        # Check exclusion keywords from custom prompt
        if exclusion_keywords and any(
            keyword in text_lower for keyword in exclusion_keywords
        ):
            logger.debug(
                f"  ✗ Excluded by custom prompt: {item.get('title', 'N/A')[:50]}..."
            )
            continue

        if _match_keywords(title_and_desc, MAIN_NEWS_KEYWORDS):
            matching_news.append(item)

    logger.info(f"Found {len(matching_news)} relevant main news items")

    # Return top 2 (take as-is from RSS, no AI rewriting)
    selected = matching_news[:2]

    if selected:
        for i, item in enumerate(selected, 1):
            logger.info(
                f"  [{i}] {item.get('title', 'N/A')[:60]}... ({item.get('source')})"
            )
        return selected

    return None


async def select_sports_news(
    news_items: List[Dict[str, Any]], exclude_urls: Optional[set] = None
) -> Optional[Dict[str, str]]:
    """Select 1 sports news item - real data only, no AI (excluding already selected)."""
    if not news_items:
        logger.info("No news items for sports selection")
        return None

    exclude_urls = exclude_urls or set()
    logger.info(
        f"Filtering {len(news_items)} news items for sports relevance (excluding {len(exclude_urls)} already selected)"
    )

    # Filter by sports keywords, excluding already selected
    for item in news_items:
        if item.get("url") in exclude_urls:
            continue
        title_and_desc = f"{item.get('title', '')} {item.get('description', '')}"
        if _match_keywords(title_and_desc, SPORTS_NEWS_KEYWORDS):
            logger.info(f"✓ Sports news selected: {item.get('title', 'N/A')[:60]}...")
            return item

    logger.warning("⚠️  No sports news found matching keywords")
    return None


async def select_good_news(
    news_items: List[Dict[str, Any]], exclude_urls: Optional[set] = None
) -> Optional[Dict[str, str]]:
    """Select 1 good/positive news item - real data only, no AI (excluding already selected)."""
    if not news_items:
        logger.info("No news items for good news selection")
        return None

    exclude_urls = exclude_urls or set()
    logger.info(
        f"Filtering {len(news_items)} news items for good news relevance (excluding {len(exclude_urls)} already selected)"
    )

    # Filter by good news keywords, excluding already selected
    for item in news_items:
        if item.get("url") in exclude_urls:
            continue
        title_and_desc = f"{item.get('title', '')} {item.get('description', '')}"
        if _match_keywords(title_and_desc, GOOD_NEWS_KEYWORDS):
            logger.info(f"✓ Good news selected: {item.get('title', 'N/A')[:60]}...")
            return item

    logger.warning("⚠️  No good news found matching keywords")
    return None
