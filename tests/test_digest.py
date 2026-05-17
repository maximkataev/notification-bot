#!/usr/bin/env python3
"""Test digest system end-to-end without running the bot."""
import asyncio
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, "/Users/maximkataev/Desktop/notification-bot")


async def test_news_fetcher():
    """Test RSS feed fetching."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: News Fetcher (RSS feeds)")
    logger.info("=" * 60)

    try:
        from src.workers.news_fetcher import get_recent_news

        news = await get_recent_news(hours=12)
        logger.info(f"✓ Fetched {len(news)} news items")
        if news:
            logger.info(f"  Sample: {news[0]['title'][:60]}...")
            logger.info(f"  Source: {news[0]['source']}")
            logger.info(f"  URL: {news[0]['url']}")
        return True
    except Exception as e:
        logger.error(f"✗ News fetcher failed: {e}", exc_info=True)
        return False


async def test_weather():
    """Test weather aggregation."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Weather Aggregator")
    logger.info("=" * 60)

    try:
        from src.ai.weather_aggregator import get_aggregated_weather

        weather = await get_aggregated_weather()
        if weather:
            logger.info(f"✓ Weather fetched successfully")
            for period, data in weather.items():
                temp = data.get("temperature", "?")
                wind = data.get("wind_speed", "?")
                logger.info(f"  {period}: {temp}°C, wind {wind} km/h")
        else:
            logger.warning("⚠️  Weather returned None")
        return True
    except Exception as e:
        logger.error(f"✗ Weather aggregator failed: {e}", exc_info=True)
        return False


async def test_rates():
    """Test exchange rates."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Exchange Rates")
    logger.info("=" * 60)

    try:
        from src.workers.rates_fetcher import get_crypto_and_forex_rates

        rates = await get_crypto_and_forex_rates()
        if rates:
            logger.info(f"✓ Rates fetched successfully")
            logger.info(f"  BTC: ${rates.get('btc_usd', 'N/A')}")
            logger.info(f"  ETH: ${rates.get('eth_usd', 'N/A')}")
            logger.info(f"  USD/EUR: {rates.get('usd_eur', 'N/A')}")
            logger.info(f"  USD/RUB: {rates.get('usd_rub', 'N/A')}")
        else:
            logger.warning("⚠️  Rates returned None")
        return True
    except Exception as e:
        logger.error(f"✗ Exchange rates failed: {e}", exc_info=True)
        return False


async def test_holidays():
    """Test holiday fetching."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Holidays & Events")
    logger.info("=" * 60)

    try:
        from src.workers.holidays import (
            get_today_holidays,
            get_today_events,
            get_upcoming_holidays,
        )

        today_holidays = await get_today_holidays()
        today_events = await get_today_events()
        upcoming = await get_upcoming_holidays(days_ahead=7)

        logger.info(f"✓ Holidays module loaded")
        if today_holidays:
            logger.info(f"  Today's holidays: {today_holidays}")
        if today_events:
            logger.info(f"  Today's events: {today_events}")
        if upcoming:
            logger.info(f"  Upcoming: {upcoming[:2]}...")  # Show first 2
        else:
            logger.info("  No upcoming holidays in next 7 days")
        return True
    except Exception as e:
        logger.error(f"✗ Holidays failed: {e}", exc_info=True)
        return False


async def test_gwp():
    """Test GWP works checker."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: GWP Works Checker")
    logger.info("=" * 60)

    try:
        from src.workers.gwp_checker import check_gwp_works, check_water_cuts

        gwp_works = await check_gwp_works()
        water_cuts = await check_water_cuts()

        logger.info(f"✓ GWP module loaded")
        if gwp_works:
            logger.info(f"  Found {len(gwp_works)} scheduled/unscheduled works")
            for work in gwp_works[:2]:
                logger.info(f"    - {work[:80]}...")
        else:
            logger.info("  No scheduled works on Vazha Iverievi")

        if water_cuts:
            logger.info(f"  Water cuts: {water_cuts[:80]}...")
        else:
            logger.info("  No water cuts scheduled")

        return True
    except Exception as e:
        logger.error(f"✗ GWP checker failed: {e}", exc_info=True)
        return False


async def test_database():
    """Test database initialization."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Database")
    logger.info("=" * 60)

    try:
        from src.db.database import init_db, get_user_profile

        await init_db()
        logger.info(f"✓ Database initialized")

        # Try to get a test user profile
        profile = await get_user_profile(user_id=123)
        if profile:
            logger.info(
                f"✓ Got user profile: wake={profile.wake_time}, sleep={profile.sleep_time}"
            )

        return True
    except Exception as e:
        logger.error(f"✗ Database failed: {e}", exc_info=True)
        return False


async def main():
    """Run all tests."""
    logger.info("🧪 TESTING DIGEST SYSTEM")
    logger.info(f"Test time: {datetime.now().isoformat()}")

    results = {}

    results["news"] = await test_news_fetcher()
    results["weather"] = await test_weather()
    results["rates"] = await test_rates()
    results["holidays"] = await test_holidays()
    results["gwp"] = await test_gwp()
    results["database"] = await test_database()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        logger.info("\n✓ All systems operational!")
        return 0
    else:
        logger.warning(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
