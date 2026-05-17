#!/usr/bin/env python3
"""Actually call the /events handler with real bot setup."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot, types

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.utils.doppler import get_secret
from src.bot.handlers.events_handler import events_command


async def call_events_command_real():
    """Actually invoke the events_command handler."""
    print("\n" + "="*100)
    print("🎭 REAL /events COMMAND INVOCATION")
    print("="*100 + "\n")

    # Get real bot token from Doppler
    print("🔐 Loading credentials from Doppler...")
    try:
        bot_token = get_secret("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in Doppler")
            return

        print(f"✅ Bot token loaded (last 5 chars: ...{bot_token[-5:]})")
    except Exception as e:
        print(f"❌ ERROR loading secrets: {e}")
        return

    # Create real Bot instance
    print("🤖 Creating Bot instance...")
    bot = Bot(token=bot_token)

    # Create mock Message object with all required fields
    print("📝 Creating mock Message object...")
    mock_message = AsyncMock(spec=types.Message)
    mock_message.chat = MagicMock()
    mock_message.chat.id = 12345
    mock_message.from_user = MagicMock()
    mock_message.from_user.id = 12345

    # Mock the reply method to capture output
    sent_messages = []

    async def mock_reply(text, **kwargs):
        """Capture reply text."""
        print(f"\n📤 Bot attempting to send message...")
        print(f"   Message size: {len(text)} characters")
        print(f"   Options: {kwargs}")
        sent_messages.append(text)

        # Return mock message with edit_text method
        result = AsyncMock(spec=types.Message)
        result.text = text

        async def mock_edit(new_text, **kwargs):
            sent_messages[-1] = new_text
            print(f"✅ Message edited: {len(new_text)} characters")
            return result

        result.edit_text = mock_edit
        return result

    mock_message.reply = mock_reply

    # Call the actual handler
    print("\n" + "-"*100)
    print("📞 Calling events_command handler...")
    print("-"*100 + "\n")

    try:
        await events_command(mock_message, bot)
        print("\n" + "-"*100)
        print("✅ Handler completed successfully!")
        print("-"*100)

        if sent_messages:
            print("\n📱 ACTUAL MESSAGE SENT TO USER:\n")
            print(sent_messages[-1])
            print("\n" + "-"*100)
            print(f"\n📊 Message Details:")
            print(f"   Size: {len(sent_messages[-1])} characters")
            print(f"   Lines: {len(sent_messages[-1].split(chr(10)))}")
            print(f"   Status: ✅ Successfully sent")
        else:
            print("⚠️  No message was sent")

    except Exception as e:
        print(f"\n❌ ERROR in handler: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await bot.session.close()
        print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(call_events_command_real())
