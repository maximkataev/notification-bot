"""Handler for /health command - system status check."""

import logging
import asyncio
from aiogram import Router, types, Bot
from aiogram.filters import Command
from src.bot.auth import AuthorizedOnly
from src.db.database import get_user_profile
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)
router = Router()


async def _check_database() -> tuple[bool, str]:
    """Check database connectivity."""
    try:
        # Try to get user profile (simple DB query)
        profile = await get_user_profile(1)
        return True, "✅ Database OK"
    except Exception as e:
        return False, f"❌ Database: {str(e)[:50]}"


async def _check_openai() -> tuple[bool, str]:
    """Check OpenAI API key validity."""
    try:
        api_key = get_secret("OPENAI_API_KEY")
        if not api_key:
            return False, "❌ OpenAI: Missing API key"

        from src.utils.openai_client import get_client

        client = get_client()
        # Make a simple request to verify key works
        response = client.models.list()
        if response:
            return True, "✅ OpenAI API OK"
        return False, "❌ OpenAI API: No response"
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            return False, "❌ OpenAI: Invalid API key"
        return False, f"❌ OpenAI: {error_msg[:50]}"


async def _check_weather() -> tuple[bool, str]:
    """Check weather API connectivity."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try Open-Meteo (fast, free, no auth)
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": 41.7151,
                    "longitude": 44.7671,
                    "current": "temperature_2m",
                },
            )
            if response.status_code == 200:
                return True, "✅ Weather API OK"
            return False, f"❌ Weather API: {response.status_code}"
    except Exception as e:
        return False, f"❌ Weather: {str(e)[:50]}"


async def _check_news() -> tuple[bool, str]:
    """Check news RSS feeds."""
    try:
        import httpx
        import feedparser

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try BBC News RSS
            response = await client.get("https://feeds.bbc.co.uk/news/world/rss.xml")
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                if feed.entries:
                    return True, f"✅ News feeds OK ({len(feed.entries)} items)"
                return False, "❌ News: No entries"
            return False, f"❌ News: {response.status_code}"
    except Exception as e:
        return False, f"❌ News: {str(e)[:50]}"


async def _check_exchange_rates() -> tuple[bool, str]:
    """Check exchange rate APIs."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check exchangerate-api
            response = await client.get(
                "https://api.exchangerate-api.com/v4/latest/USD"
            )
            if response.status_code == 200:
                return True, "✅ Exchange Rates OK"
            return False, f"❌ Exchange Rates: {response.status_code}"
    except Exception as e:
        return False, f"❌ Exchange Rates: {str(e)[:50]}"


@router.message(Command("health"), AuthorizedOnly())
async def health_command(message: types.Message, bot: Bot):
    """Check bot and system health status."""
    checking_msg = await message.reply(
        "🔍 Проверяю здоровье системы...", disable_web_page_preview=True
    )

    # Run all checks in parallel
    results = await asyncio.gather(
        _check_database(),
        _check_openai(),
        _check_weather(),
        _check_news(),
        _check_exchange_rates(),
    )

    db_ok, db_msg = results[0]
    openai_ok, openai_msg = results[1]
    weather_ok, weather_msg = results[2]
    news_ok, news_msg = results[3]
    rates_ok, rates_msg = results[4]

    all_ok = all([db_ok, openai_ok, weather_ok, news_ok, rates_ok])
    status_emoji = "🟢" if all_ok else "🟡"

    response = f"{status_emoji} Статус системы:\n\n"
    response += f"{db_msg}\n"
    response += f"{openai_msg}\n"
    response += f"{weather_msg}\n"
    response += f"{news_msg}\n"
    response += f"{rates_msg}\n"

    if all_ok:
        response += "\n✅ Все системы работают нормально!"
    else:
        response += "\n⚠️  Некоторые системы имеют проблемы"

    await checking_msg.edit_text(response, disable_web_page_preview=True)
