#!/usr/bin/env python3
"""Test Spotify credentials and album recommendation functionality."""

import asyncio
import sys
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workers.content_parser import (
    _spotify_validate_credentials,
    _spotify_get_access_token,
    _spotify_search_album,
    get_album_of_day,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_spotify_validation():
    """Test if Spotify credentials are valid."""
    logger.info("=" * 60)
    logger.info("TEST 1: Validate Spotify Credentials")
    logger.info("=" * 60)

    is_valid = await _spotify_validate_credentials()

    if is_valid:
        logger.info("✓ Spotify credentials are VALID")
        return True
    else:
        logger.error("✗ Spotify credentials are INVALID or MISSING")
        logger.info("Please set in Doppler:")
        logger.info("  doppler secrets set SPOTIFY_CLIENT_ID <your-client-id>")
        logger.info("  doppler secrets set SPOTIFY_CLIENT_SECRET <your-client-secret>")
        return False


async def test_spotify_search():
    """Test album search on Spotify."""
    logger.info("=" * 60)
    logger.info("TEST 2: Search Album on Spotify")
    logger.info("=" * 60)

    token = await _spotify_get_access_token()
    if not token:
        logger.error("✗ Could not get Spotify token")
        return False

    # Test search for a well-known album
    test_album = "Abbey Road"
    test_artist = "The Beatles"

    logger.info(f"Searching for: '{test_album}' by {test_artist}")

    url = await _spotify_search_album(test_album, test_artist, token)

    if url:
        logger.info(f"✓ Found on Spotify: {url}")
        return True
    else:
        logger.error(f"✗ Album not found on Spotify")
        return False


async def test_album_of_day():
    """Test album of the day recommendation."""
    logger.info("=" * 60)
    logger.info("TEST 3: Get Album of the Day")
    logger.info("=" * 60)

    album = await get_album_of_day()

    if album:
        logger.info(f"✓ Album of the day: {album.get('title')} by {album.get('creator')}")
        logger.info(f"  URL: {album.get('url')}")
        logger.info(f"  Review: {album.get('review')}")
        return True
    else:
        logger.error("✗ Could not get album of the day")
        return False


async def main():
    """Run all Spotify tests."""
    logger.info("\n🎵 SPOTIFY FUNCTIONALITY TEST SUITE\n")

    results = {
        "Validation": await test_spotify_validation(),
        "Search": await test_spotify_search(),
        "Album of Day": await test_album_of_day(),
    }

    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {name}")

    all_passed = all(results.values())

    if all_passed:
        logger.info("\n✓ All Spotify tests PASSED!")
        return 0
    else:
        logger.error("\n✗ Some tests FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
