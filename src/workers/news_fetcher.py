"""Fetch and parse news from RSS feeds - organized by 5 category pools."""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from html import unescape
import feedparser
import httpx

logger = logging.getLogger(__name__)


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# POOL 1: Politics & Economics
POLITICS_ECONOMY_FEEDS = [
    "https://feeds.bloomberg.com/markets/news.rss",  # Bloomberg Markets
    "https://www.politico.eu/feed/",  # Politico Europe
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
]

# POOL 2: Sports (football, hockey, tennis, track - NO F1, basketball, baseball)
SPORTS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/rss.xml",  # BBC Sport
    "https://www.espn.com/espn/rss/news",  # ESPN
    "https://www.eurosport.com/rss/eurosport_rss_news.xml",  # Eurosport
    "https://www.goal.com/feeds/news",  # Goal.com (football)
    "https://feeds.sky.com/feed/sports/football",  # Sky Sports Football
    "https://www.marca.com/rss/futbol/",  # Marca (Spanish football)
    "https://www.as.com/rss/futbol/",  # AS.com (Spanish sports)
    "https://feeds.theguardian.com/theguardian/sport/football/rss",  # Guardian Football
]

# POOL 3: Technology & AI
TECHNOLOGY_FEEDS = [
    "https://techcrunch.com/feed/",  # TechCrunch
    "https://feeds.arstechnica.com/arstechnica/index",  # Ars Technica
    "https://news.ycombinator.com/rss",  # Hacker News
    "https://www.theverge.com/rss/index.xml",  # The Verge
    "https://feeds.bloomberg.com/technology/news.rss",  # Bloomberg Technology
]

# POOL 4: Culture & Science
CULTURE_SCIENCE_FEEDS = [
    "https://www.theguardian.com/international/rss",  # The Guardian
    "https://feeds.npr.org/1001/rss.xml",  # NPR News (culture, society)
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News (also has culture)
]

# POOL 5: Good News (positive, inspiring stories — animals, kindness, rescues).
# Dedicated good-news / animal feeds so the pool is full of genuinely uplifting
# content instead of general hard-news where political/economic stories dominate
# (this pool feeds the "good-news-only" user, who must NOT get politics/economy/sports).
GOOD_NEWS_FEEDS = [
    "https://www.goodnewsnetwork.org/feed/",  # Good News Network (positive only)
    "https://www.positive.news/feed/",  # Positive News (positive only)
    "https://www.theguardian.com/world/animals/rss",  # Guardian Animals
    "https://www.theguardian.com/world/series/the-upside/rss",  # Guardian "The Upside"
]

# POOL 6: Crypto (BTC, ETH, SOL, SUI, UNI and other major cryptocurrencies)
CRYPTO_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",  # CoinDesk
    "https://cointelegraph.com/rss",  # Cointelegraph
    "https://decrypt.co/feed",  # Decrypt
    "https://bitcoinmagazine.com/.rss/full/",  # Bitcoin Magazine
]


async def _fetch_from_feeds(
    feed_urls: List[str], hours: int, category: str, limit_per_feed: int = 15
) -> List[Dict[str, Any]]:
    """Generic fetch function for any pool of feeds."""
    logger.info(f"Fetching {category} news from {len(feed_urls)} feeds (last {hours}h)")
    all_items = []
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    successful = 0
    failed = 0

    for feed_url in feed_urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(feed_url)

                # Skip 4xx errors (not found, etc) without retry
                if 400 <= response.status_code < 500:
                    logger.debug(f"{feed_url}: {response.status_code} Not Found")
                    failed += 1
                    continue

                response.raise_for_status()

            feed = feedparser.parse(response.text)
            source_name = feed.feed.get("title", feed_url.split("/")[2])

            items_added = 0
            for entry in feed.entries[:limit_per_feed]:
                pub_time = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_time = datetime(*entry.updated_parsed[:6])

                if pub_time and pub_time < cutoff_time:
                    continue

                url = entry.get("link", "").strip()
                if not url or not url.startswith(("http://", "https://")):
                    continue

                description = entry.get("summary", "")
                description = _clean_html(description)[:800]

                item = {
                    "title": entry.get("title", ""),
                    "description": description,
                    "source": source_name,
                    "url": url,
                    "published": pub_time.isoformat() if pub_time else None,
                    "category": category,  # Tag with category
                }

                if item["title"]:
                    all_items.append(item)
                    items_added += 1

            logger.debug(f"  ✓ {source_name}: {items_added} items")
            successful += 1

        except Exception as e:
            failed += 1
            logger.debug(f"  ✗ {feed_url}: {type(e).__name__}")
            continue

    logger.info(
        f"✓ {category}: {len(all_items)} items ({successful}/{len(feed_urls)} feeds)"
    )
    return all_items


async def get_politics_economy_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch politics & economics news."""
    return await _fetch_from_feeds(POLITICS_ECONOMY_FEEDS, hours, "politics")


async def get_sports_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch sports news (football, hockey, tennis, track - NO F1, basketball, baseball)."""
    items = await _fetch_from_feeds(SPORTS_FEEDS, hours, "sports", limit_per_feed=20)

    # Filter out banned sports
    filtered = []
    for item in items:
        combined = f"{item['title']} {item['description']}".lower()
        if not any(
            ban in combined
            for ban in [
                "formula 1",
                "f1",
                "nascar",
                "motogp",
                "indycar",
                "basketball",
                "nba",
                "baseball",
                "mlb",
                "esports",
            ]
        ):
            filtered.append(item)

    return filtered


async def get_technology_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch technology & AI news."""
    return await _fetch_from_feeds(TECHNOLOGY_FEEDS, hours, "technology")


async def get_culture_science_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch culture, science, and innovation news."""
    return await _fetch_from_feeds(CULTURE_SCIENCE_FEEDS, hours, "culture")


async def get_good_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch positive, inspiring news stories."""
    items = await _fetch_from_feeds(GOOD_NEWS_FEEDS, hours, "goodness")

    # Filter out negative content for good news section
    filtered = []
    negative_keywords = [
        "dead",
        "death",
        "died",
        "war",
        "conflict",
        "tragedy",
        "disaster",
        "accident",
        "crash",
        "killed",
        "missing",
        "crime",
        "murder",
        "attack",
    ]

    for item in items:
        combined = f"{item['title']} {item['description']}".lower()
        if not any(neg in combined for neg in negative_keywords):
            filtered.append(item)

    return filtered


async def get_crypto_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch cryptocurrency news (BTC, ETH, SOL, SUI, UNI and other major coins)."""
    return await _fetch_from_feeds(CRYPTO_FEEDS, hours, "crypto")
