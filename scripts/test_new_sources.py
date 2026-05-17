#!/usr/bin/env python3
"""Test new event sources: Meetup.com and Cinemaqa.ge"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def main():
    print("\n" + "="*100)
    print("🎭 TESTING NEW EVENT SOURCES (Meetup.com + Cinemaqa.ge)")
    print("="*100 + "\n")

    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)

    print(f"📅 Period: {today} → {next_week_end}\n")

    # Fetch events
    print("🔍 Fetching from ALL sources:")
    print("  1. redevents.ge")
    print("  2. eventbrite.com")
    print("  3. meetup.com (NEW)")
    print("  4. cinemaqa.ge (NEW)\n")

    all_events = await get_tbilisi_events(days_ahead=7)

    print(f"✅ Total events fetched: {len(all_events)}\n")

    # Group by source
    by_source = {}
    for event in all_events:
        source = event.get('source', 'unknown')
        by_source[source] = by_source.get(source, 0) + 1

    print("📊 Events by source:")
    for source in sorted(by_source.keys()):
        count = by_source[source]
        emoji = "✅" if count > 0 else "❌"
        print(f"  {emoji} {source}: {count} events")

    print("\n" + "="*100)
    print("📋 ALL EVENTS DETAILS")
    print("="*100 + "\n")

    for i, event in enumerate(all_events, 1):
        date_str = event.get('date') or 'N/A'
        time_str = event.get('time') or 'N/A'
        title = event.get('title', 'Unknown')[:60]
        source = event.get('source', 'unknown')

        print(f"{i}. {title}")
        print(f"   📅 {date_str} @ {time_str}")
        print(f"   📍 {event.get('location', 'N/A')}")
        print(f"   🏷️  {source}")
        print()

    # Filter to 7 days
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

    print(f"✅ Events in 7-day window: {len(future_events)}\n")

    if future_events:
        formatted = format_events_for_telegram(future_events)
        print("="*100)
        print("📱 TELEGRAM OUTPUT")
        print("="*100 + "\n")
        print(formatted)

    print("="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
