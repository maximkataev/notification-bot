"""Handler for /events command - check Tbilisi events."""

import logging
from datetime import datetime, timedelta
from aiogram import Router, types, Bot
from aiogram.filters import Command
from src.bot.auth import AuthorizedOnly
from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram
from src.ai.event_describer import generate_event_descriptions

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("events"), AuthorizedOnly())
async def events_command(message: types.Message, bot: Bot):
    """Check and display Tbilisi events for next 7 days."""
    logger.info("🎭 /events command started")

    checking_msg = await message.reply(
        "🔍 Загружаю мероприятия в Тбилиси...\n⚠️ Источники могут быть недоступны",
        disable_web_page_preview=True
    )

    try:
        logger.debug("📅 Fetching events for 7 days ahead")
        today = datetime.now().date()
        next_week_end = today + timedelta(days=7)
        logger.debug(f"   Period: {today} to {next_week_end}")

        # Fetch events
        logger.debug("📡 Calling get_tbilisi_events(days_ahead=7)")
        events = await get_tbilisi_events(days_ahead=7)
        logger.info(f"✅ Fetched {len(events)} total events")

        # Filter to future events (7 days ahead)
        logger.debug("🔍 Filtering events (next 7 days)")
        future_events = []
        for event in events:
            event_date = event.get("date")
            if not event_date:
                logger.debug(f"   ⏭️  Skipping event without date: {event.get('title', 'Unknown')}")
                continue

            try:
                event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()

                logger.debug(f"   📅 {event.get('title', 'Unknown')[:30]}")
                logger.debug(f"      Date: {event_date}")

                # Include events within next 7 days
                if today <= event_dt <= next_week_end:
                    future_events.append(event)
                    logger.debug(f"      ✅ Included")
                else:
                    logger.debug(f"      ⏭️  Skipped (outside 7-day window)")

            except ValueError as e:
                logger.warning(f"   ❌ Failed to parse date '{event_date}': {e}")
                continue

        logger.info(f"🔍 Filtered to {len(future_events)} events in next 7 days")

        # Log each event detail
        if future_events:
            logger.debug("📋 Events found:")
            for i, event in enumerate(future_events, 1):
                logger.debug(f"   {i}. {event.get('category', 'other')} - {event.get('title', 'Unknown')[:50]}")
                logger.debug(f"      📍 {event.get('location', 'Unknown')}")
                logger.debug(f"      📅 {event.get('date', 'N/A')}")
                logger.debug(f"      🔗 {event.get('source', 'Unknown')}")
        else:
            logger.warning("⚠️  No events found in next 7 days")

        # Generate descriptions for events (280 chars via ChatGPT)
        logger.debug("🤖 Generating event descriptions via ChatGPT")
        future_events = await generate_event_descriptions(future_events)

        # Format for Telegram
        logger.debug("🎨 Formatting events for Telegram")
        formatted_text = format_events_for_telegram(future_events)

        logger.info(f"📤 Sending {len(future_events)} events to user")
        await checking_msg.edit_text(formatted_text, disable_web_page_preview=True)

        logger.info("✅ /events command completed successfully")

    except Exception as e:
        logger.exception(f"❌ Error fetching events: {e}")
        error_msg = f"❌ Ошибка при загрузке мероприятий:\n{str(e)[:200]}"
        await checking_msg.edit_text(error_msg, disable_web_page_preview=True)
