#!/usr/bin/env python3
"""Extract BBC Weather reports (hourly data) and analyze structure."""

import asyncio
import sys
import json
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_bbc_html


async def debug_reports():
    """Extract and show BBC reports structure."""
    print("=" * 80)
    print("ANALYZING BBC WEATHER REPORTS (HOURLY DATA)")
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

        # Check for data -> forecasts -> detailed -> reports
        if not isinstance(data, dict) or "data" not in data:
            continue

        data_obj = data["data"]
        if not isinstance(data_obj, dict) or "forecasts" not in data_obj:
            continue

        forecasts = data_obj["forecasts"]
        if not forecasts or not isinstance(forecasts[0], dict):
            continue

        if "detailed" not in forecasts[0]:
            continue

        detailed = forecasts[0]["detailed"]
        if "reports" not in detailed:
            continue

        reports = detailed["reports"]
        print(f"Found {len(reports)} hourly reports for today")
        print()

        # Show structure of first few reports
        print("First 5 reports:")
        print("-" * 80)
        for idx, report in enumerate(reports[:5]):
            print(f"[{idx}] Report keys: {list(report.keys())}")
            print(f"     timeslot: {report.get('timeslot', 'N/A')}")
            print(f"     localDate: {report.get('localDate', 'N/A')}")
            print(f"     temperatureC: {report.get('temperatureC', 'N/A')}°C")
            print(f"     weatherTypeText: {report.get('weatherTypeText', 'N/A')}")
            print()

        # Group reports by period
        periods = {
            "night": [],
            "morning": [],
            "day": [],
            "evening": []
        }

        for report in reports:
            timeslot = report.get("timeslot", "")
            local_date = report.get("localDate", "")
            if not timeslot or not local_date:
                continue

            # Extract hour from timeslot (format like "23:00" or "01:00")
            try:
                hour = int(timeslot.split(":")[0])
                temp = report.get("temperatureC")

                if 0 <= hour < 6:
                    periods["night"].append((hour, temp))
                elif 6 <= hour < 12:
                    periods["morning"].append((hour, temp))
                elif 12 <= hour < 18:
                    periods["day"].append((hour, temp))
                elif 18 <= hour < 24:
                    periods["evening"].append((hour, temp))
            except (ValueError, IndexError):
                pass

        print()
        print("Temperatures grouped by period:")
        print("-" * 80)
        for period, temps in periods.items():
            if temps:
                avg_temp = sum(t[1] for t in temps) / len(temps)
                min_temp = min(t[1] for t in temps)
                max_temp = max(t[1] for t in temps)
                times = [f"{h:02d}h" for h, _ in temps]
                print(f"{period:>8}: {times}")
                print(f"         min={min_temp}°C, avg={avg_temp:.1f}°C, max={max_temp}°C")
            else:
                print(f"{period:>8}: (no data)")

        print()
        print("=" * 80)
        break


if __name__ == "__main__":
    asyncio.run(debug_reports())
