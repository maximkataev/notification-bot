#!/usr/bin/env python3
"""Simulate /events command execution."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def simulate_events_command():
    """Simulate what /events command does"""
    print("\n" + "="*100)
    print("📱 SIMULATING /events COMMAND")
    print("="*100 + "\n")

    # Mimic what the handler does
    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)
    print(f"📅 Time window: {today} to {next_week_end} (next 7 days)\n")

    # Fetch events
    print("🔍 Fetching events...")
    all_events = await get_tbilisi_events(days_ahead=7)
    print(f"✅ Fetched {len(all_events)} events total\n")

    # Filter to 7-day window (as handler does)
    print("🔍 Filtering to 7-day window...")
    future_events = []
    for event in all_events:
        event_date = event.get("date")
        if not event_date:
            continue

        try:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
            # Include events within next 7 days
            if today <= event_dt <= next_week_end:
                future_events.append(event)
        except ValueError:
            continue

    print(f"✅ Filtered to {len(future_events)} events in 7-day window\n")

    # Format and display
    if future_events:
        print("📊 Events by source:")
        by_source = {}
        for event in future_events:
            source = event.get('source', 'unknown')
            by_source[source] = by_source.get(source, 0) + 1

        for source, count in sorted(by_source.items()):
            print(f"  • {source}: {count} events")

        print("\n" + "="*100)
        print("📱 TELEGRAM MESSAGE")
        print("="*100 + "\n")

        formatted = format_events_for_telegram(future_events)
        print(formatted)
    else:
        print("⚠️ No events found in 7-day window")

    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(simulate_events_command())
