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
