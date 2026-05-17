#!/usr/bin/env python3
"""Test tkt.ge scraping with Playwright."""

import asyncio
import sys
import logging

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s | %(message)s'
)

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def main():
    print("\n" + "="*100)
    print("🎬 TESTING TKT.GE WITH PLAYWRIGHT")
    print("="*100 + "\n")

    print("📍 This test scrapes tkt.ge using Playwright to render JavaScript")
    print("⏱️  This may take 10-15 seconds...\n")
    print("-"*100 + "\n")

    try:
        events = await get_tbilisi_events(days_ahead=7)

        print("\n" + "-"*100)
        print(f"\n✅ SUCCESS! Fetched {len(events)} events\n")

        if events:
            print("📋 Events found:")
            for i, event in enumerate(events[:5], 1):
                print(f"   {i}. {event.get('date')} - {event.get('title', 'Unknown')[:50]}")
                print(f"      📍 {event.get('location', 'Unknown')}")
                print(f"      🔗 {event.get('source', 'Unknown')}\n")

            if len(events) > 5:
                print(f"   ... and {len(events) - 5} more\n")

            # Filter weekend events
            weekend_events = [
                e for e in events
                if e.get('date') and
                asyncio.get_event_loop().run_until_complete(_is_weekend(e))
            ]

            print(f"🎉 Weekend events: {len(weekend_events)}\n")

            if weekend_events:
                formatted = format_events_for_telegram(weekend_events)
                print("📱 Telegram output:\n")
                print(formatted)
        else:
            print("⚠️  No events found")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*100 + "\n")


async def _is_weekend(event):
    from datetime import datetime
    try:
        date = datetime.strptime(event.get('date', ''), "%Y-%m-%d").date()
        return date.weekday() in (5, 6)
    except:
        return False


if __name__ == "__main__":
    asyncio.run(main())
