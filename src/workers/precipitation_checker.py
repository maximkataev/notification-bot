"""Check for upcoming precipitation in Tbilisi.

Uses the SAME weather source as the morning digest (`get_aggregated_weather`:
Gismeteo → BBC → Georgian Weather) so rain alerts and the digest never disagree.
The aggregated weather is grouped into night/morning/day/evening periods; we look at
the period(s) overlapping the next N hours and flag rain from the condition text.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    TBILISI_TZ = ZoneInfo("Asia/Tbilisi")
except Exception:  # pragma: no cover - fallback if tzdata unavailable
    TBILISI_TZ = None

from src.ai.weather_sources import get_aggregated_weather

logger = logging.getLogger(__name__)

# Condition keywords that count as precipitation (match weather_sources condition keys)
RAIN_KEYWORDS = [
    "дождь", "снег", "гроза", "морось", "ливень", "ледяной дождь", "град",
]

# Period boundaries (hour ranges) — must mirror weather_sources period grouping
PERIODS = {
    "night": (0, 6),
    "morning": (6, 12),
    "day": (12, 18),
    "evening": (18, 24),
}

# Default emoji per condition keyword (for alert message)
CONDITION_EMOJI = {
    "дождь": "🌧️", "ливень": "🌧️", "морось": "🌦️", "ледяной дождь": "🌧️",
    "снег": "❄️", "гроза": "⛈️", "град": "🌨️",
}


def _tbilisi_now() -> datetime:
    """Current time in Tbilisi (naive), independent of server timezone (UTC)."""
    if TBILISI_TZ is not None:
        return datetime.now(TBILISI_TZ).replace(tzinfo=None)
    # Fallback: Tbilisi is UTC+4 year-round
    return datetime.utcnow() + timedelta(hours=4)


async def get_upcoming_precipitation(hours: int = 3) -> Optional[Dict[str, Any]]:
    """Check the digest weather source for precipitation in the next N hours.

    Returns dict with precipitation details if found, None otherwise:
    {
        "time": "15:00",        # approximate onset (start of the rainy period)
        "hours_from_now": 2,
        "condition": "дождь",
        "emoji": "🌧️",
    }
    """
    try:
        weather = await get_aggregated_weather()
        if not weather or not isinstance(weather, dict):
            return None

        now = _tbilisi_now()
        cur_hour = now.hour
        window_end = cur_hour + hours

        # Walk periods in chronological order; flag the first overlapping rainy one
        for period_name, (start, end) in PERIODS.items():
            # Does this period overlap [cur_hour, cur_hour + hours)?
            if start < window_end and end > cur_hour:
                period = weather.get(period_name)
                if not isinstance(period, dict):
                    continue

                condition = (period.get("condition") or "").lower()
                matched = next((kw for kw in RAIN_KEYWORDS if kw in condition), None)
                if not matched:
                    continue

                onset_hour = max(start, cur_hour)
                hours_from_now = max(0, onset_hour - cur_hour)
                emoji = period.get("emoji") or CONDITION_EMOJI.get(matched, "🌧️")

                return {
                    "time": f"{onset_hour:02d}:00",
                    "hours_from_now": hours_from_now,
                    "condition": condition,
                    "emoji": emoji,
                }

        return None

    except Exception as e:
        logger.warning(f"Precipitation check failed: {e}")
        return None
