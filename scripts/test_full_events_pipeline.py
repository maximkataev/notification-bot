#!/usr/bin/env python3
"""Test full events pipeline with GPT descriptions."""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram
from src.ai.event_describer import generate_event_descriptions


async def main():
    print("\n" + "="*100)
    print("🎭 FULL EVENTS PIPELINE TEST (WITH GPT DESCRIPTIONS)")
    print("="*100 + "\n")

    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)

    print(f"📅 Current date: {today}")
    print(f"⏰ 7-day window: {today} → {next_week_end}\n")

    # Step 1: Fetch events
    print("Step 1️⃣ Fetching events from sources...")
    all_events = await get_tbilisi_events(days_ahead=7)
    print(f"✅ Fetched {len(all_events)} events\n")

    # Step 2: Filter to 7 days
    print("Step 2️⃣ Filtering to 7-day window...")
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

    print(f"✅ Filtered to {len(future_events)} events\n")

    if not future_events:
        print("⚠️ No events in 7-day window")
        return

    # Step 3: Generate descriptions
    print("Step 3️⃣ Generating descriptions via ChatGPT...")
    print("   (This takes 10-30 seconds per event)\n")

    future_events = await generate_event_descriptions(future_events)
    print("✅ Descriptions generated\n")

    # Step 4: Format for Telegram
    print("Step 4️⃣ Formatting for Telegram...")
    formatted = format_events_for_telegram(future_events)
    print("✅ Formatted\n")

    # Display result
    print("="*100)
    print("📱 FINAL OUTPUT")
    print("="*100 + "\n")
    print(formatted)
    print("="*100 + "\n")

    # Stats
    print("📊 STATISTICS")
    print(f"  Total events processed: {len(future_events)}")
    print(f"  Events with descriptions: {sum(1 for e in future_events if e.get('description'))}")
    print(f"  Average description length: {sum(len(e.get('description', '')) for e in future_events) // max(1, len(future_events))} chars")


if __name__ == "__main__":
    asyncio.run(main())
