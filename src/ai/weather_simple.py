"""Simple weather fetcher using Open-Meteo API (no HTML parsing, pure JSON)."""

import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# WMO Weather codes to Russian
WMO_CODES = {
    0: "ясно", 1: "облачно", 2: "переменная облачность", 3: "облачно",
    45: "туман", 48: "туман", 51: "морось", 53: "морось", 55: "морось",
    61: "дождь", 63: "дождь", 65: "ливень", 71: "снег", 73: "снег", 75: "снег",
    77: "снег", 80: "дождь", 81: "ливень", 82: "ливень", 85: "снег", 86: "снег",
    95: "гроза", 96: "гроза", 99: "гроза",
}

CONDITION_EMOJI = {
    "ясно": "☀️", "облачно": "☁️", "дождь": "🌧️", "снег": "❄️",
    "гроза": "⛈️", "туман": "🌫️", "переменная облачность": "⛅",
    "морось": "🌦️", "град": "🌨️", "ливень": "🌧️", "ледяной дождь": "🌧️",
}


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch weather from Open-Meteo API (free JSON API, no JS required)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": 41.7151,  # Tbilisi
                    "longitude": 44.8271,
                    "hourly": "temperature_2m,weather_code,precipitation",
                    "timezone": "Asia/Tbilisi",
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error(f"❌ Weather fetch failed: {type(e).__name__}")
        return None

    try:
        hourly = data["hourly"]
        temps = hourly["temperature_2m"]
        codes = hourly["weather_code"]
        precips = hourly.get("precipitation", [0] * len(temps))

        # Group by periods
        periods = {
            "night": (0, 6),      # 00:00-06:00
            "morning": (6, 12),   # 06:00-12:00
            "day": (12, 18),      # 12:00-18:00
            "evening": (18, 24),  # 18:00-24:00
        }

        weather_by_period = {}
        for period_name, (start_h, end_h) in periods.items():
            period_temps = temps[start_h:end_h]
            period_codes = codes[start_h:end_h]
            period_precips = precips[start_h:end_h]

            if period_temps:
                avg_temp = round(sum(period_temps) / len(period_temps), 1)
                most_common_code = max(set(period_codes), key=period_codes.count)
                condition = WMO_CODES.get(most_common_code, "облачно")
                emoji = CONDITION_EMOJI.get(condition, "🌤️")
                total_precip = round(sum(period_precips), 1)

                weather_by_period[period_name] = {
                    "temperature": avg_temp,
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": total_precip,
                }

        logger.info(f"✓ Weather: {len(weather_by_period)} periods OK")
        return weather_by_period if weather_by_period else None

    except Exception as e:
        logger.error(f"❌ Weather parse failed: {type(e).__name__}: {str(e)[:100]}")
        return None


async def generate_clothing_recommendation(weather: Optional[Dict[str, Dict]], is_raining: bool = False) -> Optional[str]:
    """Generate clothing recommendation."""
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
                {"role": "user", "content": f"Что надеть на день в Тбилиси? Температура {avg_temp:.1f}°C, {'осадки' if has_precip else 'без осадков'}. Ответ: 2-3 вещи, без объяснений."},
            ],
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Clothing rec failed: {e}")
        return None
