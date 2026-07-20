#!/usr/bin/env python3
"""Test football results with RSS feed sport news."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workers.football_matches import get_yesterday_results, get_formatted_results

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_yesterday_results():
    """Test getting yesterday's results with match news from RSS feeds."""
    logger.info("=" * 80)
    logger.info("🏟️  TESTING FOOTBALL RESULTS WITH RSS SPORT NEWS")
    logger.info("=" * 80)

    # Get yesterday's results
    logger.info("\n📋 Fetching yesterday's results from kulichki.net...")
    results = await get_yesterday_results()

    if not results:
        logger.warning("❌ No results found for yesterday")
        return

    logger.info(f"\n✅ Found {len(results)} result(s):")
    for i, result in enumerate(results, 1):
        logger.info(f"\n  {i}. {result['home']} vs {result['away']}")
        logger.info(f"     Score: {result['score']}")
        logger.info(f"     League: {result.get('league', 'Unknown')}")

    # Test RSS feed search for each result
    logger.info("\n" + "=" * 80)
    logger.info("🔍 TESTING RSS FEED SEARCH FOR MATCH NEWS")
    logger.info("=" * 80)

    from src.workers.football_matches import _find_match_news_from_rss
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for result in results:
        home = result['home']
        away = result['away']

        logger.info(f"\n📰 Searching news for: {home} vs {away} on {yesterday}")

        news = await _find_match_news_from_rss(home, away, yesterday)

        if news:
            logger.info(f"✅ Found news ({len(news)} chars):")
            logger.info(f"   {news[:200]}...")
        else:
            logger.warning(f"⚠️  No news found")

    # Format results with AI commentary
    logger.info("\n" + "=" * 80)
    logger.info("🤖 FORMATTING RESULTS WITH AI COMMENTARY")
    logger.info("=" * 80)

    formatted = await get_formatted_results(results)
    if formatted:
        logger.info("\n📝 Formatted Results:\n")
        print(formatted)
    else:
        logger.warning("Failed to format results")


async def test_rss_search():
    """Test RSS feed search for match news (club matches)."""
    logger.info("\n" + "=" * 80)
    logger.info("🔍 TESTING RSS FEED SEARCH FOR MATCH NEWS")
    logger.info("=" * 80)

    from src.workers.football_matches import _find_match_news_from_rss

    # Test club matches
    club_test_cases = [
        ("Борнмут", "Манчестер Сити", "2026-05-19"),
        ("Барселона", "Атлетико", "2026-05-19"),
    ]

    logger.info("\n🏟️  Club Matches:")
    for home, away, date in club_test_cases:
        logger.info(f"\n🔎 Testing: {home} vs {away} on {date}")
        news = await _find_match_news_from_rss(home, away, date)
        if news:
            logger.info(f"✅ Found: {news[:150]}...")
        else:
            logger.info(f"⚠️  No news found (expected if match didn't happen)")


if __name__ == "__main__":
    logger.info("Starting football results test...")

    asyncio.run(test_yesterday_results())
    asyncio.run(test_rss_search())

    logger.info("\n" + "=" * 80)
    logger.info("✅ TEST COMPLETED")
    logger.info("=" * 80)
