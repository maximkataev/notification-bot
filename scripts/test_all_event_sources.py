#!/usr/bin/env python3
"""Test all event sources and verify multi-source aggregation."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import (
    get_tbilisi_events,
    format_events_for_telegram,
)
from datetime import datetime


async def main():
    print("\n" + "="*100)
    print("🎭 TESTING ALL TBILISI EVENT SOURCES")
    print("="*100 + "\n")

    print("⏳ Fetching events from all sources...")
    events = await get_tbilisi_events(days_ahead=7)

    print(f"\n✅ Total events fetched: {len(events)}\n")

    if events:
        # Group by source
        by_source = {}
        for event in events:
            source = event.get('source', 'unknown')
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(event)

        print("📊 Events by source:")
        for source, source_events in sorted(by_source.items()):
            print(f"  • {source}: {len(source_events)} events")

        # Group by date
        print("\n📅 Events by date:")
        by_date = {}
        for event in events:
            date = event.get('date', 'no-date')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(event)

        for date in sorted(by_date.keys(), key=lambda x: x or "9999-12-31"):
            count = len(by_date[date])
            if date != 'no-date':
                try:
                    dt = datetime.strptime(date, "%Y-%m-%d").date()
                    day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                    day_name = day_names[dt.weekday()]
                    print(f"  {date} ({day_name}): {count} events")
                except:
                    print(f"  {date}: {count} events")
            else:
                print(f"  {date}: {count} events")

        # Sample events
        print("\n📋 Sample events (first 5):")
        for i, event in enumerate(events[:5], 1):
            print(f"\n  {i}. {event.get('title', 'Unknown')}")
            print(f"     📅 {event.get('date')} {event.get('time', '')}".strip())
            print(f"     📍 {event.get('location', 'Unknown')}")
            print(f"     🏷️  {event.get('category', 'other')}")
            print(f"     🔗 {event.get('source', 'unknown')}")

        # Format for Telegram
        print("\n" + "="*100)
        print("📱 FORMATTED FOR TELEGRAM")
        print("="*100 + "\n")
        formatted = format_events_for_telegram(events)
        print(formatted)

    else:
        print("⚠️ No events found from any source")

    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
