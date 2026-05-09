#!/usr/bin/env python3
"""Quick test: fetch current EUR/USD rate and check alert threshold."""
import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, "/Users/maximkataev/Desktop/notification-bot")

from src.utils.tbc_bank import get_eur_usd_rate

ALERT_THRESHOLD = 1.18


async def test():
    logger.info("Fetching current EUR/USD rate...")
    rate = await get_eur_usd_rate()

    if rate:
        logger.info(f"Current rate: {rate:.4f}")
        logger.info(f"Alert threshold: {ALERT_THRESHOLD}")
        if rate > ALERT_THRESHOLD:
            logger.warning(f"ALERT: Rate {rate:.4f} exceeds threshold!")
        else:
            logger.info(f"OK: Rate {rate:.4f} is below threshold")
    else:
        logger.error("Failed to fetch rate from all APIs")


if __name__ == "__main__":
    asyncio.run(test())
