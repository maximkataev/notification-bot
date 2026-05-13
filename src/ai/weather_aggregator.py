"""Aggregate weather data from multiple sources for accuracy."""

import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)

# Tbilisi coordinates
TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271

# WMO weather code to (Russian condition, emoji) mapping
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


async def get_weather_openmeteo() -> Optional[Dict[str, Any]]:
    """Fetch hourly weather from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={TBILISI_LAT}&longitude={TBILISI_LON}&hourly=temperature_2m,weather_code,wind_speed_10m,precipitation&temperature_unit=celsius&timezone=Asia/Tbilisi"
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Open-Meteo failed: {e}")
        return None


async def get_weather_wttr() -> Optional[Dict[str, Any]]:
    """Fetch weather from wttr.in API."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = "https://wttr.in/Tbilisi?format=j1"
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"wttr.in failed: {e}")
        return None


async def get_weather_yrno() -> Optional[Dict[str, Any]]:
    """Fetch weather from yr.no (Norwegian Meteorological Institute)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={TBILISI_LAT}&lon={TBILISI_LON}"
            headers = {
                "User-Agent": "notification-bot/1.0 github.com/user/notification-bot"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"yr.no failed: {e}")
        return None


def _parse_openmeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Open-Meteo response into period format."""
    if not data or "hourly" not in data:
        return None

    try:
        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        codes = data["hourly"]["weather_code"]
        winds = data["hourly"]["wind_speed_10m"]
        precips = data["hourly"].get("precipitation", [None] * len(times))

        periods = {
            "night": (0, 6),
            "morning": (6, 12),
            "day": (12, 18),
            "evening": (18, 24),
        }

        weather_by_period = {}
        for period_name, (start_hour, end_hour) in periods.items():
            period_temps = []
            period_winds = []
            period_codes = []
            period_precips = []

            for i, time_str in enumerate(times):
                try:
                    hour = int(time_str.split("T")[1].split(":")[0])
                    if start_hour <= hour < end_hour:
                        period_temps.append(temps[i])
                        period_winds.append(winds[i])
                        period_codes.append(codes[i])
                        if precips[i] is not None:
                            period_precips.append(precips[i])
                except (IndexError, ValueError) as e:
                    logger.debug(f"Failed to parse hour from {time_str}: {e}")
                    continue

            if period_temps and period_winds:
                avg_temp = sum(period_temps) / len(period_temps)
                avg_wind = sum(period_winds) / len(period_winds)
                # Use most frequent weather code for the period
                most_common_code = (
                    Counter(period_codes).most_common(1)[0][0] if period_codes else 0
                )
                avg_precip = (
                    sum(period_precips) / len(period_precips) if period_precips else 0.0
                )

                condition, emoji = WMO_CODES.get(most_common_code, ("неизвестно", "🌤️"))

                weather_by_period[period_name] = {
                    "temperature": round(avg_temp, 1),
                    "wind_speed": round(avg_wind, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": round(avg_precip, 1),
                    "weather_code": most_common_code,
                }

        return weather_by_period if weather_by_period else None
    except Exception as e:
        logger.warning(f"Failed to parse Open-Meteo: {e}")
        return None


def _parse_yrno(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse yr.no response into period format."""
    if (
        not data
        or "properties" not in data
        or "timeseries" not in data.get("properties", {})
    ):
        return None

    try:
        timeseries = data["properties"]["timeseries"]
        if not timeseries:
            return None

        periods = {
            "night": (0, 6),
            "morning": (6, 12),
            "day": (12, 18),
            "evening": (18, 24),
        }

        weather_by_period = {}
        for period_name, (start_hour, end_hour) in periods.items():
            period_temps = []
            period_winds = []
            period_precips = []

            for entry in timeseries:
                try:
                    time_str = entry.get("time", "")
                    hour = (
                        int(time_str.split("T")[1].split(":")[0])
                        if "T" in time_str
                        else -1
                    )

                    if start_hour <= hour < end_hour:
                        instant = (
                            entry.get("data", {}).get("instant", {}).get("details", {})
                        )
                        next_hours = entry.get("data", {}).get("next_1_hours", {})

                        temp = instant.get("air_temperature")
                        wind = instant.get("wind_speed")
                        precip = next_hours.get("details", {}).get(
                            "precipitation_amount", 0
                        )

                        if temp is not None:
                            period_temps.append(temp)
                        if wind is not None:
                            period_winds.append(wind)
                        period_precips.append(precip)
                except (KeyError, ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse yr.no entry: {e}")
                    continue

            if period_temps and period_winds:
                avg_temp = sum(period_temps) / len(period_temps)
                avg_wind = sum(period_winds) / len(period_winds)
                avg_precip = (
                    sum(period_precips) / len(period_precips) if period_precips else 0.0
                )

                # Use generic weather code and condition for yr.no (less reliable)
                weather_code = 3  # default to overcast
                condition = "облачно"
                emoji = "☁️"

                weather_by_period[period_name] = {
                    "temperature": round(avg_temp, 1),
                    "wind_speed": round(avg_wind, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": round(avg_precip, 1),
                    "weather_code": weather_code,
                }

        return weather_by_period if weather_by_period else None
    except Exception as e:
        logger.warning(f"Failed to parse yr.no: {e}")
        return None


def _parse_wttr(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse wttr.in response into period format."""
    if not data or "current_condition" not in data:
        return None

    try:
        current = data["current_condition"][0]
        temp = float(current["temp_C"])
        wind = float(current["windspeedKmph"])
        desc = current.get("description", "").lower()

        # Map wttr.in description to condition and emoji
        condition = desc if desc else "облачно"
        emoji = (
            "🌧️"
            if "rain" in desc or "дождь" in desc
            else (
                "❄️"
                if "snow" in desc or "снег" in desc
                else (
                    "☁️"
                    if "cloud" in desc or "облач" in desc
                    else (
                        "🌫️"
                        if "fog" in desc or "туман" in desc
                        else "⛈️" if "thunder" in desc or "гроза" in desc else "🌤️"
                    )
                )
            )
        )

        # Estimate weather code from description
        weather_code = 3  # default to overcast
        if "clear" in desc or "sunny" in desc:
            weather_code = 0
        elif "rain" in desc:
            weather_code = 63
        elif "snow" in desc:
            weather_code = 73
        elif "thunder" in desc:
            weather_code = 95

        # Simple approach: use current conditions for all periods
        weather_by_period = {
            "night": {
                "temperature": round(temp - 3, 1),
                "wind_speed": round(wind * 0.8, 1),
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": 0.0,
                "weather_code": weather_code,
            },
            "morning": {
                "temperature": round(temp - 1, 1),
                "wind_speed": round(wind * 0.9, 1),
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": 0.0,
                "weather_code": weather_code,
            },
            "day": {
                "temperature": round(temp + 2, 1),
                "wind_speed": round(wind * 1.1, 1),
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": 0.0,
                "weather_code": weather_code,
            },
            "evening": {
                "temperature": round(temp, 1),
                "wind_speed": round(wind, 1),
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": 0.0,
                "weather_code": weather_code,
            },
        }

        return weather_by_period
    except Exception as e:
        logger.warning(f"Failed to parse wttr.in: {e}")
        return None


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch and aggregate weather from multiple sources."""
    logger.info("🌤️ Fetching weather from multiple sources...")

    results = []

    # Fetch all sources concurrently
    import asyncio

    openmeteo_data, wttr_data, yrno_data = await asyncio.gather(
        get_weather_openmeteo(),
        get_weather_wttr(),
        get_weather_yrno(),
        return_exceptions=False,
    )

    # Try Open-Meteo (most reliable)
    if openmeteo_data:
        parsed = _parse_openmeteo(openmeteo_data)
        if parsed:
            results.append(("open-meteo", parsed))
            logger.info("✓ Open-Meteo: OK")
        else:
            logger.warning("✗ Open-Meteo: parse failed")
    else:
        logger.warning("✗ Open-Meteo: fetch failed")

    # Try wttr.in (backup)
    if wttr_data:
        parsed = _parse_wttr(wttr_data)
        if parsed:
            results.append(("wttr.in", parsed))
            logger.info("✓ wttr.in: OK")
        else:
            logger.warning("✗ wttr.in: parse failed")
    else:
        logger.warning("✗ wttr.in: fetch failed")

    # Try yr.no (3rd source)
    if yrno_data:
        parsed = _parse_yrno(yrno_data)
        if parsed:
            results.append(("yr.no", parsed))
            logger.info("✓ yr.no: OK")
        else:
            logger.warning("✗ yr.no: parse failed")
    else:
        logger.warning("✗ yr.no: fetch failed")

    if not results:
        logger.error("❌ All weather sources failed")
        return None

    logger.info(f"Aggregating data from {len(results)} source(s)...")
    aggregated = {}

    for period in ["night", "morning", "day", "evening"]:
        temps = [r[1][period]["temperature"] for r in results if period in r[1]]
        winds = [r[1][period]["wind_speed"] for r in results if period in r[1]]
        precips = [r[1][period]["precipitation_mm"] for r in results if period in r[1]]
        codes = [r[1][period]["weather_code"] for r in results if period in r[1]]
        conditions = [r[1][period]["condition"] for r in results if period in r[1]]

        if temps and winds:
            # Average numeric values
            avg_temp = round(sum(temps) / len(temps), 1)
            avg_wind = round(sum(winds) / len(winds), 1)
            avg_precip = round(sum(precips) / len(precips), 1) if precips else 0.0

            # Collect all unique conditions from different sources
            unique_conditions = []
            seen = set()
            for cond in conditions:
                if cond and cond.lower() not in seen:
                    unique_conditions.append(cond)
                    seen.add(cond.lower())

            # Join conditions with "/" if they differ, else use single condition
            if unique_conditions:
                condition = "/".join(unique_conditions) if len(unique_conditions) > 1 else unique_conditions[0]
            else:
                condition = "облачно"

            # Use Open-Meteo's weather code if available (most reliable)
            primary_source = next((r for r in results if r[0] == "open-meteo"), None)
            if primary_source:
                emoji = primary_source[1][period]["emoji"]
            else:
                # Fallback: use most common code
                weather_code = Counter(codes).most_common(1)[0][0] if codes else 3
                _, emoji = WMO_CODES.get(weather_code, ("облачно", "☁️"))

            aggregated[period] = {
                "temperature": avg_temp,
                "wind_speed": avg_wind,
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": avg_precip,
            }

    return aggregated if aggregated else None
