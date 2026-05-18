#!/usr/bin/env python3
"""Stress test: Digest exactly 8001 characters to verify splitting logic."""

import asyncio
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.doppler import get_secret
from aiogram import Bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_digest_splitting():
    """Test message splitting with exactly 8001 characters."""
    logger.info("=" * 80)
    logger.info("STRESS TEST: Digest with 8001 characters (2 * 4000 + 1)")
    logger.info("=" * 80)
    logger.info("")

    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = int(get_secret("TELEGRAM_CHAT_ID"))

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not found")
        return False

    bot = Bot(token=bot_token)

    # Create a message exactly 8001 chars
    # Part 1: 4000 chars
    # Separator: 1 char (newline)
    # Part 2: 4000 chars
    part1 = "A" * 4000
    part2 = "B" * 4000
    test_message = f"{part1}\n{part2}"

    assert len(test_message) == 8001, f"Expected 8001 chars, got {len(test_message)}"

    logger.info(f"Test message: {len(test_message)} chars")
    logger.info(f"  Part 1: {len(part1)} chars (A's)")
    logger.info(f"  Separator: 1 char (newline)")
    logger.info(f"  Part 2: {len(part2)} chars (B's)")
    logger.info("")

    # Simulate splitting logic from scheduler
    TELEGRAM_MESSAGE_CHAR_LIMIT = 4000
    message_lines = test_message.split("\n")
    logger.info(f"Message lines: {len(message_lines)}")
    logger.info(f"  Line 0: {len(message_lines[0])} chars")
    logger.info(f"  Line 1: {len(message_lines[1])} chars")
    logger.info("")

    # Apply splitting logic
    parts = []
    current_part = []
    current_length = 0

    logger.info("Applying splitting logic...")
    for idx, line in enumerate(message_lines):
        line_with_newline = len(line) + 1
        logger.info(f"  Line {idx}: {len(line)} chars (with newline: {line_with_newline})")

        if current_length + line_with_newline > TELEGRAM_MESSAGE_CHAR_LIMIT and current_part:
            joined = "\n".join(current_part)
            actual_len = len(joined)
            logger.info(f"    → Saving part: {actual_len} chars")
            parts.append(joined)
            current_part = [line]
            current_length = line_with_newline
        else:
            current_part.append(line)
            current_length += line_with_newline
            logger.info(f"    → Added to current part (length now: {current_length})")

    if current_part:
        joined = "\n".join(current_part)
        actual_len = len(joined)
        logger.info(f"  Final part: {actual_len} chars")
        parts.append(joined)

    logger.info("")
    logger.info(f"Result: {len(parts)} parts")
    for i, part in enumerate(parts, 1):
        status = "✓ OK" if len(part) <= TELEGRAM_MESSAGE_CHAR_LIMIT else "✗ FAIL"
        logger.info(f"  Part {i}: {len(part)}/{TELEGRAM_MESSAGE_CHAR_LIMIT} chars {status}")

    logger.info("")

    # Try to send
    all_ok = True
    for i, part in enumerate(parts, 1):
        if len(part) > TELEGRAM_MESSAGE_CHAR_LIMIT:
            logger.error(f"❌ Part {i} exceeds limit: {len(part)} > {TELEGRAM_MESSAGE_CHAR_LIMIT}")
            all_ok = False
        else:
            logger.info(f"✓ Part {i} OK ({len(part)} chars)")

    if all_ok:
        logger.info("")
        logger.info("✓ All parts within limit. Sending to Telegram...")
        try:
            for i, part in enumerate(parts, 1):
                await bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                logger.info(f"✓ Sent part {i}/{len(parts)}")

            logger.info("")
            logger.info("=" * 80)
            logger.info("✓ STRESS TEST PASSED - 8001 chars split correctly!")
            logger.info("=" * 80)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send: {type(e).__name__}: {e}")
            return False
    else:
        logger.error("")
        logger.error("=" * 80)
        logger.error("✗ STRESS TEST FAILED - Parts exceed limit!")
        logger.error("=" * 80)
        return False


async def main():
    success = await test_digest_splitting()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
