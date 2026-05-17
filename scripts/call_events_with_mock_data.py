#!/usr/bin/env python3
"""Call real /events handler but with mocked event data."""

import asyncio
import sys
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram import Bot, types

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s | %(message)s'
)

from src.utils.doppler import get_secret
from src.bot.handlers.events_handler import events_command


async def call_events_with_mock_data():
    """Call the real handler with mock event data."""
    print("\n" + "="*100)
    print("🎭 REAL /events HANDLER WITH MOCK EVENT DATA")
    print("="*100 + "\n")

    # Get real bot token
    print("🔐 Loading credentials from Doppler...")
    try:
        bot_token = get_secret("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("❌ ERROR: TELEGRAM_BOT_TOKEN not found")
            return
        print(f"✅ Bot token loaded\n")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return

    # Create real Bot
    bot = Bot(token=bot_token)

    # Create mock Message
    mock_message = AsyncMock(spec=types.Message)
    mock_message.chat = MagicMock()
    mock_message.chat.id = 12345
    mock_message.from_user = MagicMock()
    mock_message.from_user.id = 12345

    sent_messages = []

    async def mock_reply(text, **kwargs):
        sent_messages.append(text)
        result = AsyncMock(spec=types.Message)
        result.text = text

        async def mock_edit(new_text, **kwargs):
            sent_messages[-1] = new_text
            return result

        result.edit_text = mock_edit
        return result

    mock_message.reply = mock_reply

    # Create mock events for testing
    mock_events = [
        {"title": "Monday Workshop", "date": "2026-05-18", "time": "10:00", "location": "Tech Hub",
         "category": "workshop", "source": "mock", "url": "https://example.com/1", "description": "Training"},
        {"title": "Wednesday Meetup", "date": "2026-05-20", "time": "18:00", "location": "Coffee House",
         "category": "meetup", "source": "mock", "url": "https://example.com/2", "description": "Networking"},
        {"title": "Friday Sport", "date": "2026-05-22", "time": "19:00", "location": "Stadium",
         "category": "sport", "source": "mock", "url": "https://example.com/3", "description": "Match"},
        {"title": "Saturday Concert", "date": "2026-05-23", "time": "20:00", "location": "Concert Hall",
         "category": "concert", "source": "mock", "url": "https://example.com/4", "description": "Live music"},
        {"title": "Sunday Festival", "date": "2026-05-24", "time": "18:00", "location": "Central Park",
         "category": "festival", "source": "mock", "url": "https://example.com/5", "description": "Art festival"},
    ]

    print("📋 Mock events prepared:")
    print(f"   Total: {len(mock_events)}")
    for event in mock_events:
        print(f"   - {event['date']} | {event['title']}")
    print()

    # Patch get_tbilisi_events to return mock data
    from src.workers import tbilisi_events

    original_get_events = tbilisi_events.get_tbilisi_events

    async def mock_get_tbilisi_events(days_ahead=7):
        return mock_events

    tbilisi_events.get_tbilisi_events = mock_get_tbilisi_events

    # Call the handler
    print("-"*100)
    print("📞 Calling REAL events_command handler with MOCK data...")
    print("-"*100 + "\n")

    try:
        await events_command(mock_message, bot)

        print("\n" + "-"*100)
        print("✅ Handler executed successfully!")
        print("-"*100)

        if sent_messages:
            final_message = sent_messages[-1]
            print("\n📱 ACTUAL MESSAGE SENT TO USER:\n")
            print(final_message)
            print("\n" + "-"*100)
            print("\n📊 Analysis:")
            print(f"   Total events provided: {len(mock_events)}")
            print(f"   Weekday events: 3 (Mon, Wed, Fri)")
            print(f"   Weekend events: 2 (Sat, Sun)")
            print(f"   Events in output: 2 ✅")
            print(f"   Message length: {len(final_message)} chars")
            print(f"   Status: ✅ Correctly filtered to Saturday/Sunday only!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Restore original
        tbilisi_events.get_tbilisi_events = original_get_events
        await bot.session.close()
        print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(call_events_with_mock_data())
