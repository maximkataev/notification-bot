#!/usr/bin/env python3
"""Test Georgian weather parser."""

import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(name)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_georgian_weather_html, _parse_georgian_weather


async def test():
    """Test Georgian weather fetching and parsing."""
    print("=" * 80)
    print("TESTING GEORGIAN WEATHER PARSER")
    print("=" * 80)
    print()

    html = await _fetch_georgian_weather_html()

    if not html:
        print("Failed to fetch Georgian weather HTML")
        return

    print(f"✓ HTML fetched: {len(html)} bytes")
    print()

    weather = _parse_georgian_weather(html)

    print()
    if weather:
        print("✓ PARSING SUCCESSFUL!")
        print()
        for period in ["night", "morning", "day", "evening"]:
            if period in weather:
                data = weather[period]
                print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C, {data['condition']}")
    else:
        print("✗ Parsing failed")

    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test())
