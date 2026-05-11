"""Hourly water cut monitoring for Vazha Iverievi street."""

import asyncio
import logging
from datetime import datetime, date
from typing import Optional
from aiogram import Bot
from src.workers.gwp_checker import check_water_cuts_today

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 3600  # 1 hour
ALERT_COOLDOWN = 86400  # 24 hours (don't repeat same alert in a day)


class WaterCutMonitor:
    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.last_alert_date: Optional[date] = None
        self.last_alert_message: Optional[str] = None

    async def check(self) -> None:
        """Single check: fetch water cut info, notify once per day if found."""
        water_cuts = await check_water_cuts_today()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if water_cuts:
            logger.info(f"[{timestamp}] Water cut detected: {water_cuts}")

            today = date.today()
            # Send alert if never alerted OR different day
            if self.last_alert_date is None or self.last_alert_date != today:
                message = f"🚨 {water_cuts}"
                await self.bot.send_message(chat_id=self.chat_id, text=message)
                self.last_alert_date = today
                self.last_alert_message = water_cuts
                logger.info(f"Water cut alert sent for {today}")
        else:
            logger.debug(f"[{timestamp}] No water cuts on Vazha Iverievi")

    async def run_loop(self) -> None:
        """Continuously monitor water cuts hourly."""
        logger.info(
            f"Water cut monitor started. Checking every {CHECK_INTERVAL // 3600} hour(s)."
        )
        while True:
            try:
                await self.check()
            except Exception as e:
                logger.error(f"Water cut monitor check failed: {type(e).__name__}: {e}")

            await asyncio.sleep(CHECK_INTERVAL)
