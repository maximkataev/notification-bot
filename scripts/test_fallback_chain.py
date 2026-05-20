#!/usr/bin/env python3
"""Demonstrate how fallback chain works."""

import asyncio
import sys
import logging

# Setup detailed logging to see fallback decisions
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(name)-30s | %(message)s'
)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import get_aggregated_weather


async def test_fallbacks():
    """Test the complete fallback chain."""
    print("=" * 100)
    print("TESTING FALLBACK CHAIN")
    print("=" * 100)
    print()
    print("This will show you how the weather sources are tried in order:")
    print("1. BBC (primary) - if fails → try fallback 1")
    print("2. World-Weather.ru (fallback 1) - if fails → try fallback 2")
    print("3. wttr.in (fallback 2) - if fails → all exhausted")
    print()
    print("-" * 100)
    print()

    result = await get_aggregated_weather()

    print()
    print("-" * 100)
    print()

    if result:
        print("✓ SUCCESS! Got weather data:")
        print()
        for period in ["night", "morning", "day", "evening"]:
            if period in result:
                data = result[period]
                print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C, {data['condition']}")
    else:
        print("✗ FAILED - All weather sources exhausted, no data returned")

    print()
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(test_fallbacks())
