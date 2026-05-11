"""EUR/USD exchange rate monitor - multi-source, alert when rate exceeds 1.18."""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from aiogram import Bot
from src.workers.forex_multi_source import check_eur_usd_threshold, EUR_USD_THRESHOLD

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 600  # 10 minutes
ALERT_COOLDOWN = 12 * 3600  # 12 hours between notifications


class CurrencyMonitor:
    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.last_alert_time: Optional[datetime] = None

    async def check(self) -> None:
        """Single check: fetch rate from multiple sources, notify once per 12h if above threshold."""
        result = await check_eur_usd_threshold(threshold=EUR_USD_THRESHOLD)
        if result is None:
            logger.warning("Could not fetch EUR/USD from any source")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        avg_rate = result.get("eur_usd_avg", 0)
        source1 = result.get("sources", [None, None])[0]
        source2 = result.get("sources", [None, None])[1]
        sources_available = result.get("sources_available", 0)
        exceeded = result.get("exceeded", False)

        status = "🚨 ALERT" if exceeded else "✓ OK"

        logger.info(
            f"[{timestamp}] EUR/USD: {avg_rate:.5f} "
            f"(src1={source1}, src2={source2}) | Threshold: {EUR_USD_THRESHOLD} | {status}"
        )

        if exceeded:
            now = datetime.now()
            # Send alert if never alerted OR 12h have passed since last alert
            if (
                self.last_alert_time is None
                or (now - self.last_alert_time).total_seconds() >= ALERT_COOLDOWN
            ):
                sources_exceeded = result.get("sources_exceeded", [])

                # Build message with source links
                message = f"🚨 EUR/USD: {avg_rate:.5f} (выше {EUR_USD_THRESHOLD})\n\n"

                # Add source details
                if source1:
                    message += f"📊 exchangerate-api.com: {source1:.5f}\n"
                if source2:
                    message += f"📊 exchangerate.host: {source2:.5f}\n"

                # Add source links
                message += "\n🔗 Источники:\n"
                message += "• https://exchangerate-api.com/\n"
                message += "• https://exchangerate.host/"

                await self.bot.send_message(chat_id=self.chat_id, text=message)
                self.last_alert_time = now
                logger.info(
                    f"Alert sent for rate {avg_rate:.5f} from sources: {sources_exceeded}"
                )

    async def run_loop(self) -> None:
        """Continuously monitor exchange rate from multiple sources."""
        logger.info(f"Currency monitor started (multi-source)")
        logger.info(f"Alert threshold: {EUR_USD_THRESHOLD}")
        logger.info(f"Checking every {CHECK_INTERVAL // 60} minutes")
        logger.info(f"Alert cooldown: 12 hours")
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
