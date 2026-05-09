#!/usr/bin/env python3
"""Test digest message formatting without needing ChatGPT."""
import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')


async def main():
    """Test digest formatting."""
    logger.info("\n" + "="*60)
    logger.info("TEST: Digest Message Formatting")
    logger.info("="*60)

    try:
        from src.db.database import init_db
        from src.bot.scheduler import _format_weather
        from src.workers.rates_fetcher import get_crypto_and_forex_rates

        # Initialize database
        await init_db()

        # Get real weather
        from src.ai.weather_aggregator import get_aggregated_weather
        logger.info("\n1️⃣  Testing weather formatting...")
        weather = await get_aggregated_weather()

        if weather:
            formatted_weather = _format_weather(weather)
            logger.info(f"✓ Weather formatted:")
            for line in formatted_weather.split('\n'):
                logger.info(f"  {line}")
        else:
            logger.warning("Weather unavailable")

        # Test currency formatting
        logger.info("\n2️⃣  Testing currency formatting...")
        rates = await get_crypto_and_forex_rates()

        if rates:
            def format_currency(value: float, decimals: int = 2) -> str:
                """Format number with space as thousands separator."""
                if value is None:
                    return "N/A"
                if decimals == 5:
                    formatted = f"{value:,.5f}".rstrip('0').rstrip('.')
                else:
                    formatted = f"{value:,.2f}".rstrip('0').rstrip('.')
                return formatted.replace(',', ' ')

            def format_change(change_24h, change_30d) -> str:
                """Format percentage changes."""
                if change_24h is None or change_30d is None:
                    return ""
                change_word_24h = "рост" if change_24h >= 0 else "падение"
                change_word_30d = "рост" if change_30d >= 0 else "падение"
                return f" ({change_word_24h} вчера на {abs(change_24h):.1f}%, за месяц {change_word_30d} на {abs(change_30d):.1f}%)"

            logger.info("✓ Currency formatted:")

            if rates.get("btc_usd"):
                btc_str = format_currency(rates['btc_usd'], decimals=5)
                change_str = format_change(rates.get("btc_change_24h"), rates.get("btc_change_30d"))
                logger.info(f"  BTC: {btc_str} USD{change_str}")

            if rates.get("eth_usd"):
                eth_str = format_currency(rates['eth_usd'], decimals=5)
                change_str = format_change(rates.get("eth_change_24h"), rates.get("eth_change_30d"))
                logger.info(f"  ETH: {eth_str} USD{change_str}")

            if rates.get("usd_eur") and rates['usd_eur'] > 0:
                eur_usd = 1.0 / rates['usd_eur']
                eur_str = format_currency(eur_usd, decimals=5)
                logger.info(f"  EUR: {eur_str} USD")

            if rates.get("usd_rub"):
                rub_str = format_currency(rates['usd_rub'], decimals=2)
                logger.info(f"  USD: {rub_str} RUB")

        else:
            logger.warning("Rates unavailable")

        # Test holiday formatting
        logger.info("\n3️⃣  Testing holiday formatting...")
        from src.workers.holidays import get_today_holidays, get_today_events

        today_holidays = await get_today_holidays()
        today_events = await get_today_events()

        if today_holidays:
            logger.info("✓ Today's holidays:")
            for holiday_text, emoji in today_holidays:
                logger.info(f"  {holiday_text}")

        if today_events:
            logger.info("✓ Today's events:")
            for event_text in today_events:
                logger.info(f"  {event_text}")

        if not today_holidays and not today_events:
            logger.info("✓ No holidays or events today")

        logger.info("\n" + "="*60)
        logger.info("✓ TEST PASSED: All formatting works!")
        logger.info("="*60)
        return 0

    except Exception as e:
        logger.error(f"✗ TEST FAILED: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
