#!/usr/bin/env python3
"""Simulate /events command execution with full logging."""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

# Setup logging to show all debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s | %(name)s | %(message)s'
)

from src.workers.tbilisi_events import format_events_for_telegram


async def simulate_events_command():
    """Simulate the /events command handler with mock data."""
    print("\n" + "="*100)
    print("🎭 SIMULATING /events COMMAND EXECUTION")
    print("="*100)
    print("\n📨 User sends: /events")
    print("⏱️  Bot processing...\n")
    print("-"*100)

    # Create mock message and bot objects
    mock_message = AsyncMock()
    mock_message.reply = AsyncMock(return_value=AsyncMock())
    mock_message.reply.return_value.edit_text = AsyncMock()

    mock_bot = AsyncMock()

    # Simulate the handler logic
    logger = logging.getLogger('src.bot.handlers.events_handler')

    logger.info("🎭 /events command started")

    # Create detailed log output
    logger.debug("📅 Fetching events for 7 days ahead")
    today = datetime.now().date()
    next_week_end = today + timedelta(days=7)
    logger.debug(f"   Period: {today} to {next_week_end}")

    # Create mock events instead of fetching
    logger.debug("📡 Creating mock events (real API sources unavailable)")

    mock_events = []
    event_descriptions = [
        ("2026-05-18", "Monday Workshop", "workshop", "Tech Hub", "https://techhub.ge"),
        ("2026-05-19", "Tuesday Meeting", "meetup", "Coffee House", "https://coffee.ge"),
        ("2026-05-20", "Wednesday Conference", "conference", "Marriott", "https://marriott.ge"),
        ("2026-05-21", "Thursday Training", "workshop", "Tech Hub", "https://techhub.ge"),
        ("2026-05-22", "Friday Sport", "sport", "Stadium", "https://stadium.ge"),
        ("2026-05-23", "Saturday Concert", "concert", "Concert Hall", "https://concert.ge"),
        ("2026-05-24", "Sunday Festival", "festival", "Central Park", "https://park.ge"),
        ("2026-05-25", "Monday Basketball", "sport", "Sports Arena", "https://arena.ge"),
    ]

    for date, title, category, location, url in event_descriptions:
        mock_events.append({
            "title": title,
            "date": date,
            "time": "19:00",
            "location": location,
            "description": f"Mock {category} event",
            "category": category,
            "source": "mock-test",
            "url": url,
        })

    logger.info(f"✅ Fetched {len(mock_events)} total events")

    # Filter to Saturday onwards (this is what the handler does)
    logger.debug("🔍 Filtering events (Saturday only)")
    saturday_events = []
    for event in mock_events:
        event_date = event.get("date")
        if not event_date:
            logger.debug(f"   ⏭️  Skipping event without date: {event.get('title', 'Unknown')}")
            continue

        try:
            event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
            day_of_week = event_dt.weekday()  # 0=Mon, 5=Sat, 6=Sun

            day_names_map = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}
            day_name = day_names_map.get(day_of_week, "?")

            logger.debug(f"   📅 {event.get('title', 'Unknown')[:30]}")
            logger.debug(f"      Date: {event_date}, Day: {day_of_week} (5=Sat, 6=Sun)")

            if day_of_week in (5, 6):
                saturday_events.append(event)
                logger.debug(f"      ✅ Included (weekend)")
            else:
                logger.debug(f"      ⏭️  Skipped (not weekend)")

        except ValueError as e:
            logger.warning(f"   ❌ Failed to parse date '{event_date}': {e}")
            continue

    logger.info(f"🔍 Filtered to {len(saturday_events)} weekend events")

    if saturday_events:
        logger.debug("📋 Weekend events found:")
        for i, event in enumerate(saturday_events, 1):
            logger.debug(f"   {i}. {event.get('category', 'other')} - {event.get('title', 'Unknown')[:50]}")
            logger.debug(f"      📍 {event.get('location', 'Unknown')}")
            logger.debug(f"      📅 {event.get('date', 'N/A')}")
            logger.debug(f"      🔗 {event.get('source', 'Unknown')}")

    logger.debug("🎨 Formatting events for Telegram")
    formatted_text = format_events_for_telegram(saturday_events)

    logger.info(f"📤 Sending {len(saturday_events)} events to user")
    logger.info("✅ /events command completed successfully")

    print("-"*100)
    print("\n📱 TELEGRAM MESSAGE RECEIVED:\n")
    print(formatted_text)

    print("\n" + "-"*100)
    print("\n📊 COMMAND STATISTICS:")
    print(f"   Total events fetched:       {len(mock_events)}")
    print(f"   Weekday events (filtered):  {len(mock_events) - len(saturday_events)}")
    print(f"   Weekend events (shown):     {len(saturday_events)}")
    print(f"   Processing time:           < 1 second")
    print(f"   Status:                     ✅ SUCCESS")
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(simulate_events_command())
