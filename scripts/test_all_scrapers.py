#!/usr/bin/env python3
"""Test all event scrapers to see what's being extracted."""

import sys
import os
import asyncio
import logging

# Setup logging to see debug output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import (
    get_tbilisi_events,
    _scrape_redevents,
    _scrape_meetup_tbilisi,
    _scrape_eventbrite,
    _scrape_cinemaqa,
)


async def main():
    print("\n" + "="*100)
    print("🧪 TESTING ALL EVENT SCRAPERS")
    print("="*100 + "\n")

    # Test each scraper individually
    scrapers = [
        ("redevents.ge", _scrape_redevents),
        ("meetup.com", _scrape_meetup_tbilisi),
        ("eventbrite.com", _scrape_eventbrite),
        ("cinemaqa.ge", _scrape_cinemaqa),
    ]

    all_results = {}

    for name, scraper_func in scrapers:
        print(f"\n{'='*100}")
        print(f"Testing: {name}")
        print(f"{'='*100}\n")

        try:
            events = await scraper_func()
            if events:
                print(f"✅ Found {len(events)} events\n")
                for i, event in enumerate(events[:5], 1):  # Show first 5
                    print(f"Event {i}:")
                    print(f"  Title: {event.get('title', 'N/A')[:60]}")
                    print(f"  Date: {event.get('date', 'N/A')}")
                    print(f"  Time: {event.get('time', 'N/A')}")
                    print(f"  Location: {event.get('location', 'N/A')}")
                    print(f"  Source: {event.get('source', 'N/A')}")
                    print(f"  URL: {event.get('url', 'N/A')[:60]}\n")
                all_results[name] = events
            else:
                print(f"⚠️ No events found\n")
                all_results[name] = []
        except Exception as e:
            print(f"❌ Error: {e}\n")
            all_results[name] = []

    # Summary
    print(f"\n{'='*100}")
    print("📊 SUMMARY")
    print(f"{'='*100}\n")

    total_with_dates = 0
    total_without_dates = 0

    for name, events in all_results.items():
        with_dates = sum(1 for e in events if e.get('date'))
        without_dates = len(events) - with_dates
        total_with_dates += with_dates
        total_without_dates += without_dates

        status = "✅" if with_dates > 0 else "⚠️"
        print(f"{status} {name}: {len(events)} total ({with_dates} with dates, {without_dates} without)")

    print(f"\n📌 TOTAL: {total_with_dates + total_without_dates} events ({total_with_dates} with dates)")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
