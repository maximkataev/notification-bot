"""Fetch holidays and special events from open APIs."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# Country codes: Georgia, Russia, Cyprus
COUNTRIES = {"GE": "🇬🇪 Georgia", "RU": "🇷🇺 Russia", "CY": "🇨🇾 Cyprus"}


async def _fetch_holidays_nager(
    country_code: str, year: int
) -> Optional[List[Dict[str, Any]]]:
    """Fetch holidays from Nager.Date API."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch holidays for {country_code}: {e}")
        return None


async def _fetch_dst_dates() -> Optional[Dict[str, str]]:
    """Fetch DST dates from timeanddate.com (simplified approach using API)."""
    try:
        # Using a simple approach: DST in Europe typically:
        # - Starts: last Sunday of March at 02:00 (clocks forward +1h)
        # - Ends: last Sunday of October at 03:00 (clocks back -1h)
        # This is hardcoded for 2026 as a reliable reference

        today = datetime.now()
        year = today.year

        # Calculate last Sunday of March (DST start)
        march_31 = datetime(year, 3, 31)
        dst_start = march_31 - timedelta(days=(march_31.weekday() + 1) % 7)

        # Calculate last Sunday of October (DST end)
        oct_31 = datetime(year, 10, 31)
        dst_end = oct_31 - timedelta(days=(oct_31.weekday() + 1) % 7)

        return {
            "dst_start_date": dst_start.strftime("%m-%d"),
            "dst_start_text": f"⏰ Daylight Saving Time begins at 02:00 (clocks forward +1h)",
            "dst_end_date": dst_end.strftime("%m-%d"),
            "dst_end_text": f"⏰ Daylight Saving Time ends at 03:00 (clocks back -1h)",
        }
    except Exception as e:
        logger.warning(f"Failed to calculate DST dates: {e}")
        return None


async def get_today_holidays() -> Optional[List[tuple]]:
    """Get holidays for today in Georgia, Russia, Cyprus from APIs."""
    today = datetime.now()

    holidays = []

    for country_code, country_name in COUNTRIES.items():
        holidays_list = await _fetch_holidays_nager(country_code, today.year)
        if holidays_list:
            for holiday in holidays_list:
                # Check if holiday is today
                if holiday.get("date") == today.strftime("%Y-%m-%d"):
                    name = holiday.get("name", "Holiday")
                    holiday_types = holiday.get(
                        "types", []
                    )  # Types: Public, Bank, School, etc.
                    emoji = "🎉"  # Default emoji

                    # Add info about government offices being closed
                    holiday_text = f"{country_name}: {name}"
                    if "Public" in holiday_types:
                        holiday_text += ". Государственные учреждения сегодня закрыты."

                    holidays.append((holiday_text, emoji))
                    logger.info(
                        f"Today's holiday: {name} in {country_name} (types: {holiday_types})"
                    )

    return holidays if holidays else None


async def get_today_events() -> Optional[List[str]]:
    """Get important events for today (DST changes, etc.)."""
    today = datetime.now().strftime("%m-%d")
    events = []

    dst_info = await _fetch_dst_dates()
    if dst_info:
        if today == dst_info["dst_start_date"]:
            events.append(dst_info["dst_start_text"])
            logger.info(f"DST event today: {dst_info['dst_start_text']}")
        elif today == dst_info["dst_end_date"]:
            events.append(dst_info["dst_end_text"])
            logger.info(f"DST event today: {dst_info['dst_end_text']}")

    return events if events else None
