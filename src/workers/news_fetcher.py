"""Fetch and parse news from RSS feeds."""

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
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = unescape(text)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Free RSS news feeds (verified working sources)
RSS_FEEDS = [
    # Politics & Economics
    "https://feeds.bloomberg.com/markets/news.rss",  # Bloomberg Markets
    "https://www.politico.eu/feed/",  # Politico Europe
    # World News & Culture
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
    "https://www.theguardian.com/international/rss",  # The Guardian
    "https://feeds.npr.org/1001/rss.xml",  # NPR News (culture, society, good news)
    # Technology & AI (for tech-savvy analyst)
    "https://techcrunch.com/feed/",  # TechCrunch
    "https://feeds.arstechnica.com/arstechnica/index",  # Ars Technica
    "https://news.ycombinator.com/rss",  # Hacker News
    "https://www.theverge.com/rss/index.xml",  # The Verge (tech & gadgets)
    "https://feeds.bloomberg.com/technology/news.rss",  # Bloomberg Technology
    # Russia & CIS
    "https://meduza.io/rss/news",  # Meduza (Russian news)
]


async def get_recent_news(hours: int = 8) -> List[Dict[str, Any]]:
    """
    Fetch news from RSS feeds from the last N hours.

    Args:
        hours: How many hours back to look (default 8)

    Returns:
        List of news items with: title, description, source, url, published_time
    """
    logger.info(f"Starting news fetch from {len(RSS_FEEDS)} RSS feeds (last {hours}h)")
    all_items = []
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    successful_feeds = 0
    failed_feeds = 0

    for feed_url in RSS_FEEDS:
        try:
            logger.debug(f"Fetching: {feed_url}")
            # Fetch with timeout
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(feed_url)
                response.raise_for_status()
            logger.debug(f"✓ HTTP 200: {feed_url}")

            # Parse RSS
            feed = feedparser.parse(response.text)
            source_name = feed.feed.get("title", feed_url.split("/")[2])
            entries_count = len(feed.entries)
            logger.debug(f"  Parsed {entries_count} entries from {source_name}")

            items_added = 0
            for entry in feed.entries[:10]:  # Limit to 10 per feed
                # Parse publish time
                pub_time = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_time = datetime(*entry.updated_parsed[:6])

                # Skip if older than cutoff
                if pub_time and pub_time < cutoff_time:
                    logger.debug(f"  Skipping old entry: {pub_time}")
                    continue

                # Skip if no URL
                url = entry.get("link", "").strip()
                if not url:
                    logger.debug(f"  Skipping entry without URL")
                    continue

                # Skip if URL looks invalid
                if not url.startswith(("http://", "https://")):
                    logger.debug(f"  Skipping invalid URL: {url}")
                    continue

                description = entry.get("summary", "")
                # Clean HTML tags from RSS feed descriptions
                description = _clean_html(description)[:800]

                item = {
                    "title": entry.get("title", ""),
                    "description": description,  # First 800 chars for fuller context
                    "source": source_name,
                    "url": url,
                    "published": pub_time.isoformat() if pub_time else None,
                }

                if item["title"]:  # Only add if has title
                    all_items.append(item)
                    items_added += 1

            logger.info(f"✓ {source_name}: {items_added} items added")
            successful_feeds += 1

        except Exception as e:
            failed_feeds += 1
            logger.warning(
                f"✗ Failed to fetch from {feed_url}: {type(e).__name__}: {e}"
            )
            logger.debug(f"Full error:", exc_info=True)
            continue

    logger.info(
        f"✓ News fetch complete: {len(all_items)} items, "
        f"{successful_feeds}/{len(RSS_FEEDS)} feeds OK, {failed_feeds} failed"
    )

    # Track and warn about high failure rate
    failure_rate = failed_feeds / len(RSS_FEEDS) if RSS_FEEDS else 0
    if failure_rate > 0.5:
        logger.error(
            f"⚠️  HIGH FEED FAILURE RATE: {failed_feeds}/{len(RSS_FEEDS)} feeds failed ({failure_rate*100:.1f}%)"
        )
    if not all_items:
        logger.warning(
            "⚠️  No news items fetched from any feed - digest will have no news section"
        )

    return all_items
