#!/usr/bin/env python3
"""Debug redevents.ge scraper."""

import sys
import os
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import _scrape_redevents


async def main():
    print("\n" + "="*100)
    print("🧪 DEBUGGING REDEVENTS.GE SCRAPER")
    print("="*100 + "\n")

    events = await _scrape_redevents()

    if events:
        print(f"\n✅ Found {len(events)} events\n")
        for i, event in enumerate(events, 1):
            print(f"Event {i}:")
            print(f"  Title: {event.get('title', 'N/A')[:70]}")
            print(f"  Date: {event.get('date', 'N/A')}")
            print(f"  Time: {event.get('time', 'N/A')}")
            print(f"  Description: {event.get('description', 'N/A')[:80]}")
            print(f"  URL: {event.get('url', 'N/A')[:80]}")
            print()
    else:
        print("❌ No events found!")


if __name__ == "__main__":
    asyncio.run(main())
