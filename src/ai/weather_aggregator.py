"""Aggregate weather data from multiple sources for accuracy."""

import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

# Tbilisi coordinates
TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271


async def get_weather_openmeteo() -> Optional[Dict[str, Any]]:
    """Fetch hourly weather from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={TBILISI_LAT}&longitude={TBILISI_LON}&hourly=temperature_2m,weather_code,wind_speed_10m&temperature_unit=celsius&timezone=Asia/Tbilisi"
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


def _parse_openmeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Open-Meteo response into period format."""
    if not data or "hourly" not in data:
        return None

    try:
        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        codes = data["hourly"]["weather_code"]
        winds = data["hourly"]["wind_speed_10m"]

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

            for i, time_str in enumerate(times):
                try:
                    hour = int(time_str.split("T")[1].split(":")[0])
                    if start_hour <= hour < end_hour:
                        period_temps.append(temps[i])
                        period_winds.append(winds[i])
                except (IndexError, ValueError) as e:
                    logger.debug(f"Failed to parse hour from {time_str}: {e}")
                    continue

            if period_temps and period_winds:
                avg_temp = sum(period_temps) / len(period_temps)
                avg_wind = sum(period_winds) / len(period_winds)
                weather_by_period[period_name] = {
                    "temperature": round(avg_temp, 1),
                    "wind_speed": round(avg_wind, 1),
                }

        return weather_by_period if weather_by_period else None
    except Exception as e:
        logger.warning(f"Failed to parse Open-Meteo: {e}")
        return None


def _parse_wttr(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse wttr.in response into period format."""
    if not data or "current_condition" not in data:
        return None

    try:
        current = data["current_condition"][0]
        temp = float(current["temp_C"])
        wind = float(current["windspeedKmph"])

        # Simple approach: use current conditions for all periods
        weather_by_period = {
            "night": {
                "temperature": round(temp - 3, 1),
                "wind_speed": round(wind * 0.8, 1),
            },
            "morning": {
                "temperature": round(temp - 1, 1),
                "wind_speed": round(wind * 0.9, 1),
            },
            "day": {
                "temperature": round(temp + 2, 1),
                "wind_speed": round(wind * 1.1, 1),
            },
            "evening": {"temperature": round(temp, 1), "wind_speed": round(wind, 1)},
        }

        return weather_by_period
    except Exception as e:
        logger.warning(f"Failed to parse wttr.in: {e}")
        return None


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch and aggregate weather from multiple sources."""
    logger.info("🌤️ Fetching weather from multiple sources...")

    results = []

    # Try Open-Meteo (most reliable)
    openmeteo_data = await get_weather_openmeteo()
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
    wttr_data = await get_weather_wttr()
    if wttr_data:
        parsed = _parse_wttr(wttr_data)
        if parsed:
            results.append(("wttr.in", parsed))
            logger.info("✓ wttr.in: OK")
        else:
            logger.warning("✗ wttr.in: parse failed")
    else:
        logger.warning("✗ wttr.in: fetch failed")

    if not results:
        logger.error("❌ All weather sources failed")
        return None

    # If we have both sources, average the temperatures
    if len(results) == 2:
        logger.info("Aggregating data from 2 sources...")
        aggregated = {}
        for period in ["night", "morning", "day", "evening"]:
            temps = [r[1][period]["temperature"] for r in results if period in r[1]]
            winds = [r[1][period]["wind_speed"] for r in results if period in r[1]]

            # Only average if we have data from both sources
            if temps and winds:
                aggregated[period] = {
                    "temperature": round(sum(temps) / len(temps), 1),
                    "wind_speed": round(sum(winds) / len(winds), 1),
                }

        # Return aggregated data if available, otherwise use first source
        return aggregated if aggregated else results[0][1]

    # Otherwise use the first successful source
    logger.info(f"Using single source: {results[0][0]}")
    return results[0][1]
