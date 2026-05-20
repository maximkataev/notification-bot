#!/usr/bin/env python3
"""Test weather parsers and show results."""

import asyncio
import sys
import logging

# Setup logging to see debug output
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s | %(name)s | %(message)s')

# Add project root to path
sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import (
    _fetch_bbc_html, _parse_bbc,
    _fetch_worldweather_html, _parse_worldweather,
    _fetch_wttr
)


async def test_sources():
    """Test all weather sources and display results."""
    print("=" * 80)
    print("TESTING WEATHER SOURCES")
    print("=" * 80)
    print()

    # Test BBC
    print("1. BBC WEATHER (https://www.bbc.com/weather/611717)")
    print("-" * 80)
    try:
        html = await _fetch_bbc_html()
        if html:
            print(f"✓ HTML fetched: {len(html)} bytes")
            print(f"  HTML snippet: {html[500:1000]}")
            print()
            weather = _parse_bbc(html)
            if weather:
                print("✓ PARSING SUCCESSFUL!")
                for period, data in weather.items():
                    print(f"  {period}: {data['temperature']}°C, {data['condition']} {data['emoji']}")
            else:
                print("✗ Parsing failed - no weather data extracted")
        else:
            print("✗ HTML fetch failed")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
    print()

    # Test world-weather.ru
    print("2. WORLD-WEATHER.RU (https://world-weather.ru/pogoda/georgia/tbilisi/7days/)")
    print("-" * 80)
    try:
        html = await _fetch_worldweather_html()
        if html:
            print(f"✓ HTML fetched: {len(html)} bytes")
            print(f"  HTML snippet: {html[500:1000]}")
            print()
            weather = _parse_worldweather(html)
            if weather:
                print("✓ PARSING SUCCESSFUL!")
                for period, data in weather.items():
                    print(f"  {period}: {data['temperature']}°C, {data['condition']} {data['emoji']}")
            else:
                print("✗ Parsing failed - no weather data extracted")
        else:
            print("✗ HTML fetch failed")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
    print()

    # Test wttr.in
    print("3. WTTR.IN (https://wttr.in/Tbilisi?format=j1)")
    print("-" * 80)
    try:
        weather = await _fetch_wttr()
        if weather:
            print("✓ PARSING SUCCESSFUL!")
            for period, data in weather.items():
                print(f"  {period}: {data['temperature']}°C, {data['condition']} {data['emoji']}")
        else:
            print("✗ Fetch/parse failed")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
    print()

    print("=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_sources())
