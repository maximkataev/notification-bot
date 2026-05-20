#!/usr/bin/env python3
"""Analyze BBC daily forecast structure."""

import asyncio
import sys
import json
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_bbc_html


async def debug_daily():
    """Extract and analyze daily forecasts."""
    print("=" * 80)
    print("ANALYZING BBC DAILY FORECAST STRUCTURE")
    print("=" * 80)
    print()

    html = await _fetch_bbc_html()
    if not html:
        print("Failed to fetch BBC HTML")
        return

    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/json")

    for script in scripts:
        if not script.string:
            continue

        content = script.string.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue

        if not isinstance(data, dict) or "data" not in data:
            continue

        data_obj = data["data"]
        if not isinstance(data_obj, dict) or "forecasts" not in data_obj:
            continue

        forecasts = data_obj["forecasts"]
        print(f"Found {len(forecasts)} daily forecasts")
        print()

        # Analyze structure of first few forecasts
        for idx, forecast in enumerate(forecasts[:3]):
            print(f"[{idx}] Forecast for day")
            print("-" * 80)
            print(f"  Keys: {list(forecast.keys())}")

            if "summary" in forecast:
                summary = forecast["summary"]
                print(f"  summary keys: {list(summary.keys()) if isinstance(summary, dict) else type(summary)}")
                if isinstance(summary, dict):
                    print(f"    content: {json.dumps(summary, indent=6)}")

            if "detailed" in forecast:
                detailed = forecast["detailed"]
                print(f"  detailed keys: {list(detailed.keys())}")

                # Check what's in the detailed forecast
                if "now" in detailed:
                    now = detailed["now"]
                    print(f"  detailed.now keys: {list(now.keys())}")
                    print(f"    Now: temp={now.get('temperatureC', 'N/A')}°C, weather={now.get('weatherTypeText', 'N/A')}")

            print()

        print("=" * 80)
        break


if __name__ == "__main__":
    asyncio.run(debug_daily())
