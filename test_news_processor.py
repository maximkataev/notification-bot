#!/usr/bin/env python3
"""Test news processor with ChatGPT integration."""
import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')


async def main():
    """Test news processor."""
    logger.info("\n" + "="*60)
    logger.info("TEST: News Processor with ChatGPT")
    logger.info("="*60)

    try:
        # Get recent news
        from src.workers.news_fetcher import get_recent_news
        logger.info("\n1️⃣  Fetching news from RSS...")
        news_items = await get_recent_news(hours=12)
        logger.info(f"✓ Fetched {len(news_items)} news items")

        if not news_items:
            logger.error("No news items available")
            return 1

        # Show first 5 news items
        logger.info("\nFirst 5 news items:")
        for i, item in enumerate(news_items[:5]):
            logger.info(f"  [{i}] {item['title'][:60]}...")

        # Process with ChatGPT
        logger.info("\n2️⃣  Sending to ChatGPT for selection...")
        from src.ai.news_processor import select_and_summarize_news_with_gpt

        selected = await select_and_summarize_news_with_gpt(news_items, user_id=123)

        if selected is None:
            logger.error("ChatGPT returned None")
            return 1

        logger.info(f"\n✓ ChatGPT selected {len(selected)} news items:")
        for item in selected:
            idx = item['index']
            category = item['category']
            summary = item['summary']
            description = item.get('description_ru', '')

            original = news_items[idx]
            source = original['source']
            url = original['url']

            logger.info(f"\n  📰 [{category}] {source}")
            logger.info(f"     Title (idx={idx}): {original['title'][:60]}...")
            logger.info(f"     Summary: {summary}")
            if description:
                logger.info(f"     Description (RU): {description[:80]}...")
            logger.info(f"     URL: {url}")

        logger.info("\n" + "="*60)
        logger.info("✓ TEST PASSED: News processor working!")
        logger.info("="*60)
        return 0

    except Exception as e:
        logger.error(f"✗ TEST FAILED: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
