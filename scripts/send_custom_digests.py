#!/usr/bin/env python3
"""Send customized digests to specific users with options."""

import asyncio
import sys
import logging
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot
from src.utils.doppler import get_secret
from src.bot.scheduler import morning_digest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def send_digests():
    """Send customized digests to multiple users."""

    # Get bot token
    try:
        bot_token = get_secret("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN not found")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to get bot token: {e}")
        return False

    bot = Bot(token=bot_token)

    # Users to send to
    users = [
        {
            "user_id": 498233237,
            "skip_sports": True,
            "skip_tasks": True,
            "name": "User 1",
        },
        {
            "user_id": 184010236,
            "skip_sports": True,
            "skip_tasks": True,
            "name": "User 2",
        },
    ]

    results = {}

    for user in users:
        user_id = user["user_id"]
        skip_sports = user.get("skip_sports", False)
        skip_tasks = user.get("skip_tasks", False)
        name = user.get("name", f"User {user_id}")

        logger.info(f"\n{'='*60}")
        logger.info(f"Sending digest to {name} ({user_id})")
        if skip_sports or skip_tasks:
            parts = []
            if skip_sports:
                parts.append("sports")
            if skip_tasks:
                parts.append("tasks")
            logger.info(f"  Options: skip {', '.join(parts)}")
        logger.info(f"{'='*60}")

        try:
            await morning_digest(
                bot,
                user_id=user_id,
                skip_sports=skip_sports,
                skip_tasks=skip_tasks,
            )
            results[user_id] = "✓ SENT"
            logger.info(f"✓ Digest sent successfully to {name}")
        except Exception as e:
            results[user_id] = f"❌ FAILED: {type(e).__name__}"
            logger.error(f"❌ Failed to send digest to {name}: {type(e).__name__}: {e}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    for user_id, result in results.items():
        logger.info(f"{result}: User {user_id}")

    return all("✓" in r for r in results.values())


async def main():
    """Run the script."""
    logger.info("\n📨 CUSTOM DIGEST SENDER\n")
    success = await send_digests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
