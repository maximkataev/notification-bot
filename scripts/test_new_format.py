#!/usr/bin/env python3
"""Test new event format."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def main():
    print("\n" + "="*100)
    print("🎭 TESTING NEW EVENT FORMAT")
    print("="*100 + "\n")

    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)

    # Fetch and filter
    all_events = await get_tbilisi_events(days_ahead=7)

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

    print(f"📊 Total events: {len(all_events)}")
    print(f"📅 Events in 7-day window: {len(future_events)}\n")

    # Format and display
    formatted = format_events_for_telegram(future_events)

    print("="*100)
    print("📱 NEW FORMAT OUTPUT")
    print("="*100 + "\n")
    print(formatted)

    print("="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
