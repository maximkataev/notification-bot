"""Monitor air quality in Tbilisi."""
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# WAQI API endpoint (World Air Quality Index)
WAQI_API = "https://api.waqi.info/feed/tbilisi/"
# Free demo token (rate-limited but works for testing)
WAQI_TOKEN = "demo"


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


async def get_air_quality_tbilisi() -> Optional[Dict[str, Any]]:
    """
    Fetch air quality data for Tbilisi using World Air Quality Index API.

    Returns:
        {
            "aqi": int (0-500),
            "description": str,
            "pm25": float (µg/m³),
            "pm10": float (µg/m³),
            "o3": float (ppb),
            "no2": float (ppb)
        }
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            url = f"{WAQI_API}?token={WAQI_TOKEN}"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # Check if data is valid
            if data.get("status") != "ok":
                logger.warning(f"WAQI API returned status: {data.get('status')}")
                return None

            aqi_data = data.get("data", {})
            aqi = aqi_data.get("aqi")

            if aqi is None:
                logger.warning("No AQI value in response")
                return None

            # Extract pollutants if available
            iaqi = aqi_data.get("iaqi", {})
            pm25 = iaqi.get("pm25", {}).get("v")
            pm10 = iaqi.get("pm10", {}).get("v")
            o3 = iaqi.get("o3", {}).get("v")
            no2 = iaqi.get("no2", {}).get("v")

            result = {
                "aqi": int(aqi),
                "description": _get_aqi_description(int(aqi)),
                "pm25": pm25,
                "pm10": pm10,
                "o3": o3,
                "no2": no2,
            }

            logger.info(f"✓ Air quality fetched: AQI={aqi} ({result['description']})")
            return result

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch air quality: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
