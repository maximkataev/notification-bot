"""Main entry point - runs bot and currency monitor together."""

import asyncio
import logging
from src.utils.doppler import get_secret
from src.db.database import init_db
from src.bot.main import main as bot_main
from src.workers.currency_monitor import CurrencyMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run bot and currency monitor in parallel."""
    # Initialize database
    await init_db()
    logger.info("Starting notification bot with AI planner...")

    # Run bot and currency monitor concurrently
    bot_task = asyncio.create_task(bot_main())
    currency_task = asyncio.create_task(CurrencyMonitor().run_loop())

    # Keep both running
    await asyncio.gather(bot_task, currency_task)


if __name__ == "__main__":
    asyncio.run(main())
