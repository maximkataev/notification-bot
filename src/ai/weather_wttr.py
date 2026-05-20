"""Weather from wttr.in - simple, reliable, JSON API."""

import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

CONDITION_EMOJI = {
    "ясно": "☀️", "облачно": "☁️", "дождь": "🌧️", "снег": "❄️",
    "гроза": "⛈️", "туман": "🌫️", "переменная облачность": "⛅",
    "морось": "🌦️", "град": "🌨️", "ливень": "🌧️", "ледяной дождь": "🌧️",
    "sunny": "☀️", "clear": "☀️", "partly cloudy": "⛅", "cloudy": "☁️",
}


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch weather from wttr.in (simple JSON API)."""
    logger.info("🌤️ Fetching weather from wttr.in...")

    try:
        # wttr.in has a simple JSON endpoint - no authentication, no JavaScript needed
        # Format: https://wttr.in/{location}?format=j1
        url = "https://wttr.in/Tbilisi?format=j1"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        logger.info("[WTTR.IN] ✓ HTML fetched")

        # Parse the JSON response
        weather_by_period = _parse_wttr(data)

        if weather_by_period:
            logger.info(f"[WTTR.IN] ✓ Parsed {len(weather_by_period)} periods")
            return weather_by_period
        else:
            logger.error("[WTTR.IN] ❌ Parse failed")
            return None

    except httpx.TimeoutException:
        logger.error("[WTTR.IN] ❌ Timeout")
        return None
    except Exception as e:
        logger.error(f"[WTTR.IN] ❌ Error: {type(e).__name__}: {str(e)[:200]}")
        return None


def _parse_wttr(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse wttr.in JSON response."""
    if not data or "current_condition" not in data:
        logger.error("[WTTR.IN] No weather data in response")
        return None

    try:
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        logger.info("[WTTR.IN] Parsing JSON response...")

        # wttr.in provides hourly data
        # We'll group by periods using hourly temperatures
        try:
            # Current weather
            current = data.get("current_condition", [{}])[0]
            current_temp = float(current.get("temp_C", 0))
            current_desc = current.get("weatherDesc", [{}])[0].get("value", "").lower()

            logger.debug(f"Current temp: {current_temp}°C, condition: {current_desc}")

            # For simplicity, use current conditions for all periods
            # In a real scenario, we'd parse hourly data for different periods
            condition = _map_condition(current_desc)
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            # Assume we have data for at least one period
            if current_temp:
                for period in periods:
                    weather_by_period[period] = {
                        "temperature": round(current_temp, 1),
                        "condition": condition,
                        "emoji": emoji,
                        "precipitation_mm": float(current.get("precipMM", 0)),
                    }

            if weather_by_period:
                logger.info(f"[WTTR.IN] ✓ Extracted weather from current conditions")
                return weather_by_period
            else:
                logger.error("[WTTR.IN] No temperature data found")
                return None

        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error(f"[WTTR.IN] JSON parse error: {e}")
            return None

    except Exception as e:
        logger.error(f"[WTTR.IN] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


def _map_condition(desc: str) -> str:
    """Map wttr.in condition description to Russian."""
    desc_lower = desc.lower()

    mapping = {
        "sunny": "ясно",
        "clear": "ясно",
        "partly cloudy": "переменная облачность",
        "cloudy": "облачно",
        "overcast": "облачно",
        "mist": "туман",
        "fog": "туман",
        "light rain": "морось",
        "patchy light rain": "морось",
        "light rain shower": "морось",
        "rain": "дождь",
        "moderate rain": "дождь",
        "heavy rain": "ливень",
        "rain shower": "дождь",
        "thundery": "гроза",
        "thunder": "гроза",
        "thunderstorm": "гроза",
        "snow": "снег",
        "light snow": "снег",
        "sleet": "град",
        "blizzard": "буран",
    }

    for key, value in mapping.items():
        if key in desc_lower:
            return value

    return "облачно"


async def generate_clothing_recommendation(weather: Optional[Dict[str, Dict]], is_raining: bool = False) -> Optional[str]:
    """Generate clothing recommendation based on weather."""
    if not weather:
        return None

    try:
        from src.utils.openai_client import get_client

        temps = [weather[p]["temperature"] for p in ["morning", "day", "evening"] if p in weather]
        if not temps:
            return None

        avg_temp = sum(temps) / len(temps)
        has_precip = is_raining or any(
            any(kw in weather[p]["condition"].lower() for kw in ["дождь", "снег", "гроза"])
            for p in ["morning", "day", "evening"] if p in weather
        )

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=100,
            messages=[
                {"role": "system", "content": "You are a fashion advisor in Russian."},
                {"role": "user", "content": f"Во что одеться в Тбилиси? Температура {avg_temp:.1f}°C, {'с осадками' if has_precip else 'без осадков'}. Ответ: 2-3 вещи, без объяснений."},
            ],
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"Clothing recommendation failed: {e}")
        return None
