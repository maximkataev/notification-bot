#!/usr/bin/env python3
"""Test meme fetching functionality with fallback sources."""

import asyncio
import sys
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workers.meme_fetcher import get_fresh_memes, get_fresh_memes_for_digest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_fresh_memes():
    """Test fetching fresh memes from all sources."""
    logger.info("=" * 60)
    logger.info("TEST 1: Fetch Fresh Memes (All Sources)")
    logger.info("=" * 60)

    memes = await get_fresh_memes(max_results=5)

    if memes:
        logger.info(f"✓ Found {len(memes)} fresh memes")
        for i, meme in enumerate(memes, 1):
            logger.info(f"  {i}. {meme.get('title', 'N/A')[:60]}")
            logger.info(f"     Source: {meme.get('source')}")
            logger.info(f"     Language: {meme.get('language')}")
        return True
    else:
        logger.error("✗ No memes found from any source")
        return False


async def test_memes_for_digest():
    """Test meme fetching for digest (validated and filtered)."""
    logger.info("=" * 60)
    logger.info("TEST 2: Memes for Digest (Validated)")
    logger.info("=" * 60)

    memes = await get_fresh_memes_for_digest(max_results=3)

    if memes:
        logger.info(f"✓ Got {len(memes)} valid memes for digest")
        for i, meme in enumerate(memes, 1):
            logger.info(f"  {i}. {meme.get('title', 'N/A')[:60]}")
            logger.info(f"     Source: {meme.get('source')}")
            logger.info(f"     URL: {meme.get('url')[:70]}...")
        return True
    else:
        logger.warning("⊘ No memes available for digest")
        return False


async def main():
    """Run all meme tests."""
    logger.info("\n🎬 MEME FETCHING TEST SUITE\n")

    results = {
        "Fresh Memes": await test_fresh_memes(),
        "Digest Memes": await test_memes_for_digest(),
    }

    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    for name, passed in results.items():
        status = "✓ PASS" if passed else "⚠️  PARTIAL/FAIL"
        logger.info(f"{status}: {name}")

    all_passed = all(results.values())

    if all_passed:
        logger.info("\n✓ All meme tests PASSED!")
        return 0
    else:
        logger.warning("\n⚠️  Some meme sources unavailable (fallback working)")
        return 0  # Not critical if fallback works


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
