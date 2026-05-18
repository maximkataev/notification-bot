#!/usr/bin/env python3
"""E2E test: Full morning digest with Spotify album integration."""

import asyncio
import sys
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bot.scheduler import _morning_digest_impl
from src.utils.doppler import get_secret
from aiogram import Bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_morning_digest_with_spotify():
    """Test full morning digest including Spotify album of the day."""
    logger.info("=" * 80)
    logger.info("E2E TEST: Morning Digest with Spotify Integration")
    logger.info("=" * 80)
    logger.info("")

    # Get credentials
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    user_id = int(get_secret("TELEGRAM_USER_ID") or get_secret("TELEGRAM_CHAT_ID"))
    chat_id = int(get_secret("TELEGRAM_CHAT_ID"))

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found in Doppler")
        return False

    logger.info(f"🤖 Using bot token (len={len(bot_token)})")
    logger.info(f"👤 User ID: {user_id}")
    logger.info(f"💬 Chat ID: {chat_id}")

    try:
        # Initialize bot
        bot = Bot(token=bot_token)
        logger.info("✓ Bot initialized")

        # Run morning digest (with timeout)
        logger.info("")
        logger.info("Starting morning digest generation...")
        logger.info("-" * 80)

        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(150):  # 2.5 minutes max
                    await _morning_digest_impl(
                        bot=bot,
                        user_id=user_id,
                        chat_id=chat_id,
                        include_tasks=True,
                        skip_sports=False,
                    )
            else:
                await asyncio.wait_for(
                    _morning_digest_impl(
                        bot=bot,
                        user_id=user_id,
                        chat_id=chat_id,
                        include_tasks=True,
                        skip_sports=False,
                    ),
                    timeout=150,
                )

            logger.info("-" * 80)
            logger.info("✓✓ Morning digest with Spotify album sent successfully!")
            logger.info("")
            logger.info("=" * 80)
            logger.info("✓ E2E TEST PASSED")
            logger.info("=" * 80)
            return True

        except asyncio.TimeoutError:
            logger.error("❌ Digest timed out (150s)")
            return False
        except Exception as e:
            logger.error(f"❌ Digest failed: {type(e).__name__}: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
            return False

    except Exception as e:
        logger.error(f"❌ Setup failed: {type(e).__name__}: {e}")
        return False


async def main():
    """Run the E2E test."""
    success = await test_morning_digest_with_spotify()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
