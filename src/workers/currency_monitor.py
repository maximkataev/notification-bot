"""EUR/USD exchange rate monitor - alert when rate exceeds 1.18."""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot
from src.utils.tbc_bank import get_eur_usd_rate

logger = logging.getLogger(__name__)

ALERT_THRESHOLD = 1.18
CHECK_INTERVAL = 600  # 10 minutes
ALERT_COOLDOWN = 12 * 3600  # 12 hours between notifications


class CurrencyMonitor:
    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.last_alert_time: Optional[datetime] = None

    async def check(self) -> None:
        """Single check: fetch rate, notify once per 12h if above threshold."""
        current_rate = await get_eur_usd_rate()
        if current_rate is None:
            logger.warning("Could not fetch current EUR/USD rate")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "ALERT" if current_rate > ALERT_THRESHOLD else "OK"

        logger.info(
            f"[{timestamp}] EUR/USD: {current_rate:.4f} | Threshold: {ALERT_THRESHOLD} | {status}"
        )

        if current_rate > ALERT_THRESHOLD:
            now = datetime.now()
            # Send alert if never alerted OR 12h have passed since last alert
            if self.last_alert_time is None or (now - self.last_alert_time).total_seconds() >= ALERT_COOLDOWN:
                message = f"🚨 EUR/USD: {current_rate:.4f} (выше {ALERT_THRESHOLD})"
                await self.bot.send_message(chat_id=self.chat_id, text=message)
                self.last_alert_time = now
                logger.info(f"Alert sent for rate {current_rate:.4f}")

    async def run_loop(self) -> None:
        """Continuously monitor exchange rate."""
        logger.info(f"Currency monitor started. Alert threshold: {ALERT_THRESHOLD}")
        logger.info(f"Checking every {CHECK_INTERVAL // 60} minutes.")
        while True:
            try:
                await self.check()
            except Exception as e:
                logger.error(f"Monitor check failed: {e}")

            await asyncio.sleep(CHECK_INTERVAL)


# Example usage (requires bot_token and chat_id set)
if __name__ == "__main__":
    from src.utils.doppler import get_secret

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = get_secret("TELEGRAM_CHAT_ID")
    bot = Bot(token=bot_token)
    monitor = CurrencyMonitor(bot=bot, chat_id=int(chat_id))
    asyncio.run(monitor.run_loop())
