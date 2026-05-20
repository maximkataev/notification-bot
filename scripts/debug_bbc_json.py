#!/usr/bin/env python3
"""Extract and analyze BBC Weather JSON data structure."""

import asyncio
import sys
import json
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_bbc_html


async def debug_bbc_json():
    """Extract BBC JSON and analyze its structure."""
    print("=" * 80)
    print("ANALYZING BBC WEATHER JSON STRUCTURE")
    print("=" * 80)
    print()

    html = await _fetch_bbc_html()
    if not html:
        print("Failed to fetch BBC HTML")
        return

    soup = BeautifulSoup(html, "html.parser")

    # Find script tags with application/json
    scripts = soup.find_all("script", type="application/json")
    print(f"Found {len(scripts)} script tags with application/json")
    print()

    for idx, script in enumerate(scripts):
        if not script.string:
            continue

        content = script.string.strip()

        # Try to parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[{idx}] Failed to parse JSON: {e}")
            continue

        # Check structure
        print(f"[{idx}] Script tag structure:")
        print("-" * 80)

        if isinstance(data, dict):
            print(f"  Root keys: {list(data.keys())}")

            # Check for data key
            if "data" in data:
                data_obj = data["data"]
                print(f"  data keys: {list(data_obj.keys()) if isinstance(data_obj, dict) else type(data_obj)}")

                # Check for forecasts
                if isinstance(data_obj, dict) and "forecasts" in data_obj:
                    forecasts = data_obj["forecasts"]
                    print(f"  forecasts: {len(forecasts)} items")

                    if forecasts and isinstance(forecasts[0], dict):
                        print(f"    [0] keys: {list(forecasts[0].keys())}")

                        # Check for detailed forecast
                        if "detailed" in forecasts[0]:
                            detailed = forecasts[0]["detailed"]
                            print(f"    detailed keys: {list(detailed.keys())}")

                            if "forecasts" in detailed:
                                period_forecasts = detailed["forecasts"]
                                print(f"    detailed.forecasts: {len(period_forecasts)} items")

                                if period_forecasts:
                                    first = period_forecasts[0]
                                    print(f"      [0] keys: {list(first.keys())}")
                                    print(f"      [0] content:")
                                    # Pretty print first forecast
                                    print(json.dumps(first, indent=8))

                            if "now" in detailed:
                                now = detailed["now"]
                                print(f"    detailed.now: {json.dumps(now, indent=8)}")

        print()

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_bbc_json())
