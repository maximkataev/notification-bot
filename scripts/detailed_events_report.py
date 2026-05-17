#!/usr/bin/env python3
"""Detailed events report with deduplication stats."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def main():
    print("\n" + "="*100)
    print("📊 DETAILED EVENTS REPORT WITH DEDUPLICATION")
    print("="*100 + "\n")

    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)

    print(f"📅 Current date: {today}")
    print(f"⏰ 7-day window: {today} → {next_week_end}\n")

    # Fetch events
    print("🔍 Fetching events from all sources...")
    all_events = await get_tbilisi_events(days_ahead=7)

    print(f"\n✅ Total events after aggregation & deduplication: {len(all_events)}\n")

    # Group by source
    by_source = {}
    for event in all_events:
        source = event.get('source', 'unknown')
        by_source[source] = by_source.get(source, 0) + 1

    print("📡 Events by source:")
    for source in sorted(by_source.keys()):
        count = by_source[source]
        print(f"  • {source}: {count} events")

    # Show all events with details
    print("\n" + "="*100)
    print("📋 ALL EVENTS (sorted by date/time)")
    print("="*100 + "\n")

    for i, event in enumerate(all_events, 1):
        date_str = event.get('date') or 'No date'
        time_str = event.get('time') or 'No time'
        title = event.get('title', 'Unknown')[:60]
        location = event.get('location', 'Unknown')
        source = event.get('source', 'unknown')

        print(f"{i}. {title}")
        print(f"   📅 {date_str} @ {time_str}")
        print(f"   📍 {location}")
        print(f"   🔗 {source}\n")

    # Filter to 7-day window
    print("="*100)
    print("🔍 FILTERING TO 7-DAY WINDOW")
    print("="*100 + "\n")

    future_events = []
    for event in all_events:
        event_date = event.get("date")
        if not event_date:
            continue

        try:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
            if today <= event_dt <= next_week_end:
                future_events.append(event)
        except ValueError:
            continue

    print(f"✅ Events within 7 days: {len(future_events)}\n")

    if future_events:
        print("📋 Events in 7-day window:")
        for i, event in enumerate(future_events, 1):
            date_str = event.get('date')
            time_str = event.get('time') or 'N/A'
            title = event.get('title', 'Unknown')[:50]
            print(f"  {i}. {title} ({date_str} {time_str})")

    # Final output
    print("\n" + "="*100)
    print("📱 FINAL TELEGRAM MESSAGE")
    print("="*100 + "\n")

    formatted = format_events_for_telegram(future_events)
    print(formatted)

    # Summary
    print("="*100)
    print("📊 SUMMARY")
    print("="*100)
    print(f"Total events fetched: {len(all_events)}")
    print(f"Events in 7-day window: {len(future_events)}")
    print(f"Filtered out: {len(all_events) - len(future_events)}")
    print("="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
