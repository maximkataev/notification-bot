"""Telegram notification service."""

import logging
from telegram import Bot
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)


async def send_notification(message: str) -> bool:
    """Send message to Telegram chat."""
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in Doppler")
        return False

    try:
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id, text=message, disable_web_page_preview=True
        )
        logger.info(f"Notification sent: {message[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        return False
