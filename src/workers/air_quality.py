"""Monitor air quality in Tbilisi using Open-Meteo air quality API."""

import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# Tbilisi coordinates
TBILISI_LAT = 41.7151
TBILISI_LON = 44.8271


def _calculate_aqi_from_pm25(pm25: float) -> int:
    """
    Calculate US AQI from PM2.5 concentration (µg/m³).

    US EPA AQI calculation for PM2.5:
    - 0-12.0: AQI 0-50 (Good)
    - 12.1-35.4: AQI 51-100 (Moderate)
    - 35.5-55.4: AQI 101-150 (Unhealthy for Sensitive Groups)
    - 55.5-150.4: AQI 151-200 (Unhealthy)
    - 150.5-250.4: AQI 201-300 (Very Unhealthy)
    - 250.5+: AQI 301+ (Hazardous)
    """
    if pm25 <= 12.0:
        return int((pm25 / 12.0) * 50)
    elif pm25 <= 35.4:
        return int(((pm25 - 12.0) / (35.4 - 12.0)) * (100 - 50) + 50)
    elif pm25 <= 55.4:
        return int(((pm25 - 35.5) / (55.4 - 35.5)) * (150 - 101) + 101)
    elif pm25 <= 150.4:
        return int(((pm25 - 55.5) / (150.4 - 55.5)) * (200 - 151) + 151)
    elif pm25 <= 250.4:
        return int(((pm25 - 150.5) / (250.4 - 150.5)) * (300 - 201) + 201)
    else:
        return min(500, int(((pm25 - 250.5) / 100) * (500 - 301) + 301))


def _get_aqi_description(aqi: int) -> str:
    """Convert AQI number to description."""
    if aqi <= 50:
        return "Хорошо"
    elif aqi <= 100:
        return "Приемлемо"
    elif aqi <= 150:
        return "Умеренно загрязнено"
    elif aqi <= 200:
        return "Загрязнено"
    elif aqi <= 300:
        return "Сильно загрязнено"
    else:
        return "Опасно"


async def get_air_quality(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Fetch air quality data for any location (by lat/lon) via Open-Meteo air quality API.

    Returns actual PM2.5 concentration in µg/m³ (not sub-index).
    Calculates AQI from PM2.5 using US EPA formula.

    Returns:
        {
            "aqi": int (0-500, calculated from PM2.5),
            "description": str,
            "pm25": float (µg/m³),
            "pm10": float (µg/m³),
        }
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = (
                f"https://air-quality-api.open-meteo.com/v1/air-quality?"
                f"latitude={lat}&longitude={lon}"
                f"&current=pm10,pm2_5"
            )
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})
            pm25 = current.get("pm2_5")
            pm10 = current.get("pm10")

            if pm25 is None:
                logger.warning("No PM2.5 value in Open-Meteo response")
                return None

            # Calculate AQI from PM2.5 concentration
            aqi = _calculate_aqi_from_pm25(pm25)

            result = {
                "aqi": aqi,
                "description": _get_aqi_description(aqi),
                "pm25": pm25,
                "pm10": pm10,
            }

            logger.info(
                f"✓ Air quality fetched: PM2.5={pm25:.1f}µg/m³, AQI={aqi} ({result['description']})"
            )
            return result

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch air quality: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None


async def get_air_quality_tbilisi() -> Optional[Dict[str, Any]]:
    """Backward-compatible Tbilisi air quality (delegates to get_air_quality)."""
    return await get_air_quality(TBILISI_LAT, TBILISI_LON)
