"""Check for upcoming precipitation using Open-Meteo hourly forecast."""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
    TBILISI_TZ = ZoneInfo("Asia/Tbilisi")
except Exception:  # pragma: no cover - fallback if tzdata unavailable
    TBILISI_TZ = None
import httpx

logger = logging.getLogger(__name__)

# Tbilisi coordinates
TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271


def _tbilisi_now() -> datetime:
    """Current time in Tbilisi (naive), independent of server timezone (UTC)."""
    if TBILISI_TZ is not None:
        return datetime.now(TBILISI_TZ).replace(tzinfo=None)
    # Fallback: Tbilisi is UTC+4 year-round
    return datetime.utcnow() + timedelta(hours=4)

# WMO weather code to (Russian condition, emoji) mapping (same as weather_aggregator)
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("ясно", "☀️"),
    1: ("преимущественно ясно", "🌤️"),
    2: ("переменная облачность", "⛅"),
    3: ("пасмурно", "☁️"),
    45: ("туман", "🌫️"),
    48: ("туман с инеем", "🌫️"),
    51: ("небольшая морось", "🌦️"),
    53: ("умеренная морось", "🌦️"),
    55: ("сильная морось", "🌧️"),
    56: ("замерзающая морось", "🌧️"),
    57: ("сильная замерзающая морось", "🌧️"),
    61: ("небольшой дождь", "🌧️"),
    63: ("дождь", "🌧️"),
    65: ("сильный дождь", "🌧️"),
    66: ("ледяной дождь", "🌧️"),
    67: ("сильный ледяной дождь", "🌧️"),
    71: ("небольшой снег", "🌨️"),
    73: ("снег", "🌨️"),
    75: ("сильный снег", "❄️"),
    77: ("снежная крупа", "❄️"),
    80: ("кратковременный дождь", "🌦️"),
    81: ("умеренный ливень", "🌧️"),
    82: ("сильный ливень", "⛈️"),
    85: ("кратковременный снег", "🌨️"),
    86: ("сильный кратковременный снег", "❄️"),
    95: ("гроза", "⛈️"),
    96: ("гроза с градом", "⛈️"),
    99: ("гроза с сильным градом", "⛈️"),
}


async def get_upcoming_precipitation(hours: int = 3) -> Optional[Dict[str, Any]]:
    """Check Open-Meteo hourly forecast for precipitation in next N hours.

    Returns dict with precipitation details if found, None otherwise:
    {
        "time": "15:00",
        "hours_from_now": 2,
        "weather_code": 63,
        "condition": "дождь",
        "emoji": "🌧️",
        "precipitation_mm": 1.2
    }
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={TBILISI_LAT}&longitude={TBILISI_LON}"
                f"&hourly=weather_code,precipitation"
                f"&temperature_unit=celsius"
                f"&timezone=Asia/Tbilisi"
            )
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            if not data or "hourly" not in data:
                return None

            times = data["hourly"]["time"]
            codes = data["hourly"]["weather_code"]
            precips = data["hourly"].get("precipitation", [])

            # Find current hour — times[] are in Asia/Tbilisi, so compare against
            # Tbilisi local time (NOT server/UTC time, which produced negative hours).
            now = _tbilisi_now()
            current_hour_str = now.strftime("%Y-%m-%dT%H:00")

            current_idx = None
            for i, time_str in enumerate(times):
                if time_str >= current_hour_str:
                    current_idx = i
                    break

            if current_idx is None:
                return None

            # Check next N hours for precipitation
            for i in range(current_idx, min(current_idx + hours, len(times))):
                code = codes[i] if i < len(codes) else 0
                precip_mm = precips[i] if i < len(precips) else 0.0

                # Precipitation threshold: weather_code >= 51 (drizzle and above)
                if code >= 51 and precip_mm > 0:
                    time_str = times[i]
                    # Parse the local forecast timestamp and diff against local now,
                    # so the result is correct even across midnight.
                    forecast_dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
                    hour = forecast_dt.hour
                    hours_from_now = max(0, round((forecast_dt - now).total_seconds() / 3600))

                    condition, emoji = WMO_CODES.get(code, ("осадки", "🌧️"))

                    return {
                        "time": f"{hour:02d}:00",
                        "hours_from_now": hours_from_now,
                        "weather_code": code,
                        "condition": condition,
                        "emoji": emoji,
                        "precipitation_mm": round(precip_mm, 1),
                    }

            return None

    except Exception as e:
        logger.warning(f"Precipitation check failed: {e}")
        return None
