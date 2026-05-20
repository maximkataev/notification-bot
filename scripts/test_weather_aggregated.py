#!/usr/bin/env python3
"""Test the aggregated weather function with new priority order."""

import asyncio
import sys
import logging

# Setup logging to see debug output
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')

# Add project root to path
sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import get_aggregated_weather


async def test_aggregated():
    """Test aggregated weather function."""
    print("=" * 80)
    print("TESTING AGGREGATED WEATHER (new priority order)")
    print("=" * 80)
    print()

    weather = await get_aggregated_weather()

    if weather:
        print("✓ AGGREGATED WEATHER SUCCESSFUL!")
        print()
        for period, data in weather.items():
            print(f"{period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C, {data['condition']}")
    else:
        print("✗ Failed to fetch aggregated weather")

    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_aggregated())
