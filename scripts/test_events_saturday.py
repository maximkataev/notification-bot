#!/usr/bin/env python3
"""Test script to check Tbilisi events with detailed logging."""

import asyncio
import logging
import sys
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram


async def main():
    print("\n" + "="*80)
    print("🎭 TBILISI EVENTS TEST - CHECKING SATURDAY/SUNDAY FILTERING")
    print("="*80 + "\n")

    today = datetime.now().date()
    print(f"Today: {today.strftime('%A, %Y-%m-%d')}")
    print(f"Next week period: {today} to {(today + timedelta(days=7)).strftime('%Y-%m-%d')}")
    print("\n" + "-"*80 + "\n")

    # Fetch events
    print("📡 Fetching events from all sources...")
    events = await get_tbilisi_events(days_ahead=7)
    print(f"✅ Total events fetched: {len(events)}\n")

    if not events:
        print("❌ No events found at all!")
        return

    # Analyze all events
    print("📋 ALL EVENTS BREAKDOWN:")
    print("-" * 80)

    saturday_events = []
    other_events = []

    for i, event in enumerate(events, 1):
        event_date = event.get("date")
        title = event.get("title", "Unknown")[:50]
        source = event.get("source", "Unknown")
        category = event.get("category", "other")

        if not event_date:
            print(f"{i:2}. ⚠️  NO DATE | {category:10} | {title} ({source})")
            other_events.append(event)
            continue

        try:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
            day_of_week = event_dt.weekday()  # 0=Mon, 5=Sat, 6=Sun
            day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

            is_weekend = day_of_week in (5, 6)
            marker = "✅ WEEKEND" if is_weekend else "⏭️  weekday"

            print(f"{i:2}. {marker:20} | {day_names[day_of_week].upper():4} | {event_date} | {category:10} | {title} ({source})")

            if is_weekend:
                saturday_events.append(event)
            else:
                other_events.append(event)

        except ValueError:
            print(f"{i:2}. ❌ PARSE ERROR | {event_date} | {title}")
            other_events.append(event)

    print("\n" + "="*80)
    print(f"🔍 FILTERING RESULTS:")
    print(f"   Weekend events (Sat/Sun):  {len(saturday_events)}")
    print(f"   Weekday events:             {len(other_events)}")
    print(f"   Total:                      {len(saturday_events) + len(other_events)}")
    print("="*80 + "\n")

    # Format and display
    print("📤 FORMATTED OUTPUT FOR TELEGRAM:")
    print("-" * 80)
    formatted = format_events_for_telegram(saturday_events)
    print(formatted)
    print("-" * 80 + "\n")

    if saturday_events:
        print("✅ WEEKEND EVENTS FOUND - Logic is working!\n")
        for i, event in enumerate(saturday_events, 1):
            event_dt = datetime.strptime(event.get("date", ""), "%Y-%m-%d").date()
            day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
            print(f"   {i}. [{day_names[event_dt.weekday()].upper()}] {event.get('title', 'Unknown')[:50]}")
            print(f"      📍 {event.get('location', 'Unknown')}")
            print(f"      🔗 {event.get('source', 'Unknown')}")
            print()
    else:
        print("⚠️  NO WEEKEND EVENTS FOUND")
        if other_events:
            print("\n   But there ARE weekday events:")
            for event in other_events[:3]:
                event_dt = datetime.strptime(event.get("date", ""), "%Y-%m-%d").date()
                day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
                try:
                    print(f"   - [{day_names[event_dt.weekday()].upper()}] {event.get('title', 'Unknown')[:50]}")
                except:
                    pass
        print("\n   This suggests the weekend filter is working correctly!")


if __name__ == "__main__":
    asyncio.run(main())
