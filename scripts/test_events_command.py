#!/usr/bin/env python3
"""Test the complete /events command flow."""

import sys
import os
import asyncio
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram
from src.ai.event_describer import generate_event_descriptions


async def main():
    print("\n" + "="*100)
    print("🎭 COMPLETE /EVENTS COMMAND TEST")
    print("="*100 + "\n")

    # Fetch events
    print("📡 Fetching events...")
    events = await get_tbilisi_events(days_ahead=7)
    print(f"✅ Fetched {len(events)} total events\n")

    # Filter to 7-day window
    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)

    future_events = []
    for event in events:
        event_date = event.get("date")
        if not event_date:
            continue

        try:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
            if today <= event_dt <= next_week_end:
                future_events.append(event)
        except ValueError:
            continue

    print(f"📅 Filtered to {len(future_events)} events in next 7 days\n")

    if future_events:
        print("📊 Events by source:")
        by_source = {}
        for event in future_events:
            source = event.get("source", "Unknown")
            by_source[source] = by_source.get(source, 0) + 1
        for source in sorted(by_source.keys()):
            print(f"   {source}: {by_source[source]}")
        print()

    # Generate descriptions
    print("🤖 Generating descriptions via ChatGPT...")
    try:
        future_events = await generate_event_descriptions(future_events)
        print("✅ Descriptions generated\n")
    except Exception as e:
        print(f"⚠️ Failed to generate descriptions: {e}\n")

    # Format for Telegram
    print("🎨 Formatting for Telegram...\n")
    formatted = format_events_for_telegram(future_events)

    print("="*100)
    print("📱 TELEGRAM MESSAGE OUTPUT")
    print("="*100 + "\n")
    print(formatted)
    print("\n" + "="*100)
    print(f"📊 MESSAGE LENGTH: {len(formatted)} characters")
    print("="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
