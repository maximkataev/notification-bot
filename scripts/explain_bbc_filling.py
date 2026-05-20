#!/usr/bin/env python3
"""Explain how BBC parser fills in all periods."""

import asyncio
import sys
import json
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_bbc_html


async def explain():
    """Show step-by-step how periods are filled."""
    print("=" * 90)
    print("HOW BBC PARSER FILLS PERIODS (night/morning/day/evening)")
    print("=" * 90)
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

        try:
            data = json.loads(script.string.strip())
        except:
            continue

        if not isinstance(data, dict) or "data" not in data:
            continue

        data_obj = data["data"]
        if "forecasts" not in data_obj:
            continue

        forecasts = data_obj["forecasts"]
        today_forecast = forecasts[0]

        # Step 1: Extract daily summary
        print("STEP 1: Extract daily min/max from summary")
        print("-" * 90)
        if "summary" in today_forecast:
            summary = today_forecast["summary"]
            if "report" in summary:
                report = summary["report"]
                min_temp = report.get("minTempC")
                max_temp = report.get("maxTempC")
                weather = report.get("weatherTypeText")
                print(f"Daily min temperature: {min_temp}°C")
                print(f"Daily max temperature: {max_temp}°C")
                print(f"Weather: {weather}")
        print()

        # Step 2: Extract hourly data
        print("STEP 2: Extract hourly forecast data")
        print("-" * 90)
        if "detailed" not in today_forecast:
            print("No detailed forecast")
            break

        detailed = today_forecast["detailed"]
        if "reports" not in detailed:
            print("No reports")
            break

        reports = detailed["reports"]
        print(f"Total hourly reports: {len(reports)}")
        print()

        # Show first 10 reports
        print(f"Hourly breakdown (showing first 10):")
        print()
        print("   Hour  | Temp | Period Assignment")
        print("-" * 90)

        period_temps = {
            "night": [],
            "morning": [],
            "day": [],
            "evening": [],
        }

        for idx, report in enumerate(reports[:10]):
            timeslot = report.get("timeslot", "")
            temp = report.get("temperatureC")

            if timeslot and temp is not None:
                hour = int(timeslot.split(":")[0])

                # Determine period
                if 0 <= hour < 6:
                    period = "night"
                elif 6 <= hour < 12:
                    period = "morning"
                elif 12 <= hour < 18:
                    period = "day"
                elif 18 <= hour < 24:
                    period = "evening"
                else:
                    period = "unknown"

                period_temps[period].append((hour, temp))
                print(f"  {timeslot:>5} | {temp:>4}°C | {period:>15}")

        print()

        # Step 3: Aggregate by period
        print("STEP 3: Aggregate temperatures by period")
        print("-" * 90)
        filled_periods = {}

        for period, temps in period_temps.items():
            if temps:
                avg = sum(t[1] for t in temps) / len(temps)
                hours = [f"{t[0]:02d}h" for t in temps]
                filled_periods[period] = {
                    "source": "hourly data",
                    "temp": avg,
                    "hours": hours,
                    "count": len(temps)
                }
                print(f"{period:>8}: avg={avg:.1f}°C from {len(temps)} hours: {', '.join(hours)}")
            else:
                print(f"{period:>8}: (no hourly data)")

        print()

        # Step 4: Fill missing periods using daily min/max
        print("STEP 4: Fill missing periods using daily min/max strategy")
        print("-" * 90)

        min_temp = report.get("minTempC") if "summary" not in today_forecast else data_obj["forecasts"][0]["summary"]["report"].get("minTempC")
        max_temp = report.get("maxTempC") if "summary" not in today_forecast else data_obj["forecasts"][0]["summary"]["report"].get("maxTempC")

        # Get actual values
        for script2 in scripts:
            if not script2.string:
                continue
            try:
                data2 = json.loads(script2.string.strip())
                if "data" in data2 and "forecasts" in data2["data"]:
                    if "summary" in data2["data"]["forecasts"][0]:
                        min_temp = data2["data"]["forecasts"][0]["summary"]["report"].get("minTempC")
                        max_temp = data2["data"]["forecasts"][0]["summary"]["report"].get("maxTempC")
                        break
            except:
                pass

        print(f"Using daily min={min_temp}°C, max={max_temp}°C")
        print()

        fill_strategy = {
            "night": ("min_temp + 0.5", lambda: min_temp + 0.5),
            "morning": ("(min + max) / 2 - 1", lambda: (min_temp + max_temp) / 2 - 1),
            "day": ("max_temp - 0.5", lambda: max_temp - 0.5),
            "evening": ("(min + max) / 2", lambda: (min_temp + max_temp) / 2),
        }

        for period, (formula, calc) in fill_strategy.items():
            if period not in filled_periods:
                estimated = round(calc())
                print(f"{period:>8}: {formula:>25} = {estimated}°C (FILLED)")
                filled_periods[period] = {
                    "source": "daily min/max estimate",
                    "temp": estimated,
                    "formula": formula
                }
            else:
                print(f"{period:>8}: {filled_periods[period]['source']}")

        print()
        print("=" * 90)
        print("FINAL RESULT")
        print("=" * 90)
        print()

        for period in ["night", "morning", "day", "evening"]:
            info = filled_periods[period]
            temp = info["temp"]
            source = info["source"]
            print(f"  {period:>8}: {temp:>5.1f}°C  ({source})")

        print()
        print("=" * 90)
        break


if __name__ == "__main__":
    asyncio.run(explain())
