"""Aggregate weather data from Gismeteo and Yandex."""

import logging
from typing import Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Emoji mapping for conditions
CONDITION_EMOJI: dict[str, str] = {
    "ясно": "☀️",
    "облачно": "☁️",
    "дождь": "🌧️",
    "снег": "❄️",
    "гроза": "⛈️",
    "туман": "🌫️",
    "переменная облачность": "⛅",
    "морось": "🌦️",
    "град": "🌨️",
    "ливень": "🌧️",
    "ледяной дождь": "🌧️",
}


async def get_weather_gismeteo() -> Optional[Dict[str, Any]]:
    """Fetch weather from Gismeteo HTML page."""
    url = "https://www.gismeteo.ru/weather-tbilisi-5277/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            logger.debug("✓ Gismeteo fetch success")
            return {"html": response.text, "source": "gismeteo"}
    except Exception as e:
        logger.warning(f"❌ Gismeteo fetch failed: {type(e).__name__}")
        return None


async def get_weather_yandex() -> Optional[Dict[str, Any]]:
    """Fetch weather from Yandex Pogoda HTML page."""
    url = "https://yandex.ru/pogoda/ru/tbilisi"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            logger.debug("✓ Yandex fetch success")
            return {"html": response.text, "source": "yandex"}
    except Exception as e:
        logger.warning(f"❌ Yandex fetch failed: {type(e).__name__}")
        return None


def _parse_gismeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Gismeteo HTML to extract weather by periods."""
    if not data or "html" not in data:
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")

        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        # Find weather cards or blocks
        # Gismeteo structure: look for temperature, condition, precipitation data
        cards = soup.find_all(class_=["weather-item", "weather-card", "period"])

        if not cards:
            # Try alternative selectors
            cards = soup.find_all("div", class_=lambda x: x and "weather" in x.lower())

        # Parse up to 4 periods
        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]

            # Extract temperature (look for common patterns)
            temp_text = card.find(class_=lambda x: x and "temp" in x.lower())
            if not temp_text:
                temp_text = card.find(class_=lambda x: x and "temperature" in x.lower())

            temp = None
            if temp_text:
                try:
                    temp_str = temp_text.get_text(strip=True)
                    temp = float(temp_str.split("°")[0].strip().replace("−", "-").replace("–", "-"))
                except (ValueError, AttributeError):
                    temp = None

            # Extract condition
            condition_elem = card.find(class_=lambda x: x and "condition" in x.lower())
            if not condition_elem:
                condition_elem = card.find(class_=lambda x: x and ("sky" in x.lower() or "desc" in x.lower()))

            condition = "облачно"
            if condition_elem:
                condition = condition_elem.get_text(strip=True).lower()

            # Get emoji
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }

        return weather_by_period if weather_by_period else None
    except Exception as e:
        logger.warning(f"Failed to parse Gismeteo: {e}")
        return None


def _parse_yandex(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Yandex Pogoda HTML to extract weather by periods."""
    if not data or "html" not in data:
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")

        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        # Find weather forecast blocks/cards
        cards = soup.find_all(class_=lambda x: x and ("forecast" in x.lower() or "period" in x.lower()))

        if not cards:
            # Try finding all divs with weather info
            cards = soup.find_all("div", class_=lambda x: x and "temp" in x.lower())

        # Parse up to 4 periods
        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]

            # Extract temperature
            temp_text = card.find(class_=lambda x: x and "temp" in x.lower())
            if not temp_text:
                temp_text = card.find(class_=lambda x: x and "temperature" in x.lower())

            temp = None
            if temp_text:
                try:
                    temp_str = temp_text.get_text(strip=True)
                    temp = float(temp_str.split("°")[0].strip().replace("−", "-").replace("–", "-"))
                except (ValueError, AttributeError):
                    temp = None

            # Extract condition/description
            condition_elem = card.find(class_=lambda x: x and ("desc" in x.lower() or "condition" in x.lower()))
            if not condition_elem:
                condition_elem = card.find("span", class_=lambda x: x and "desc" in x.lower())

            condition = "облачно"
            if condition_elem:
                condition = condition_elem.get_text(strip=True).lower()

            # Get emoji
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }

        return weather_by_period if weather_by_period else None
    except Exception as e:
        logger.warning(f"Failed to parse Yandex: {e}")
        return None


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch and aggregate weather from Gismeteo and Yandex."""
    logger.info("🌤️ Fetching weather from Gismeteo and Yandex...")

    import asyncio

    gismeteo_data, yandex_data = await asyncio.gather(
        get_weather_gismeteo(),
        get_weather_yandex(),
        return_exceptions=False,
    )

    results = []

    # Try Gismeteo
    if gismeteo_data:
        parsed = _parse_gismeteo(gismeteo_data)
        if parsed:
            results.append(("gismeteo", parsed))
            logger.info("✓ Gismeteo: OK")
        else:
            logger.warning("✗ Gismeteo: parse failed")
    else:
        logger.warning("✗ Gismeteo: fetch failed")

    # Try Yandex
    if yandex_data:
        parsed = _parse_yandex(yandex_data)
        if parsed:
            results.append(("yandex", parsed))
            logger.info("✓ Yandex: OK")
        else:
            logger.warning("✗ Yandex: parse failed")
    else:
        logger.warning("✗ Yandex: fetch failed")

    if not results:
        logger.error("❌ All weather sources failed")
        return None

    logger.info(f"Aggregating data from {len(results)} source(s)...")
    aggregated = {}

    for period in ["night", "morning", "day", "evening"]:
        temps = [r[1][period]["temperature"] for r in results if period in r[1]]
        conditions = [r[1][period]["condition"] for r in results if period in r[1]]
        precips = [r[1][period]["precipitation_mm"] for r in results if period in r[1]]

        if temps:
            avg_temp = round(sum(temps) / len(temps), 1)
            avg_precip = round(sum(precips) / len(precips), 1) if precips else 0.0

            # Use first condition or combine
            condition = conditions[0] if conditions else "облачно"
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            aggregated[period] = {
                "temperature": avg_temp,
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": avg_precip,
            }

    return aggregated if aggregated else None


async def generate_clothing_recommendation(weather: Optional[Dict[str, Dict]], is_raining: bool = False) -> Optional[str]:
    """Generate clothing recommendation based on weather, validated for jacket logic.

    Args:
        weather: Weather dict from get_aggregated_weather with periods (morning/day/evening/night)
        is_raining: Whether precipitation is expected (from precipitation_checker or weather condition)
    """
    if not weather:
        return None

    try:
        # Extract key weather info
        temps = []
        has_precipitation = is_raining

        # Keywords that indicate precipitation in condition string
        RAIN_KEYWORDS = ["дождь", "снег", "гроза", "морось", "ливень", "ледяной дождь", "град"]

        for period in ["morning", "day", "evening"]:
            if period in weather:
                temps.append(weather[period]["temperature"])
                # Check both precipitation_mm and condition keywords
                if not has_precipitation:
                    if weather[period].get("precipitation_mm", 0) > 0:
                        has_precipitation = True
                    elif any(kw in weather[period]["condition"].lower() for kw in RAIN_KEYWORDS):
                        has_precipitation = True

        if not temps:
            return None

        avg_temp = sum(temps) / len(temps)
        min_temp = min(temps)
        temp_range = f"{min_temp:.1f}°C - {max(temps):.1f}°C"

        conditions_list = [weather[p]["condition"] for p in ["morning", "day", "evening"] if p in weather]
        conditions = ", ".join(conditions_list)

        prompt = f"""Рекомендуй, во что одеться на день в Тбилиси.

Погода:
- Температура: {temp_range} (минимум {min_temp:.1f}°C)
- Условия: {conditions}
- {'Ожидаются осадки' if has_precipitation else 'Без осадков'}

ПРАВИЛО ДЛЯ КУРТКИ:
Куртка/пальто нужна ТОЛЬКО если:
  • Температура ниже 10°C, ИЛИ
  • Ожидаются осадки (дождь, снег, гроза)
В других случаях БЕЗ куртки!

Дай практичную рекомендацию (2-3 вещи) на русском. Будь конкретен:
- Укажи конкретные вещи (рубашка, джинсы, кроссовки и т.д.)
- Если {'ЕСТЬ осадки ИЛИ' if has_precipitation else ''} температура ниже 10°C - укажи конкретную куртку/пальто
- Если выше 10°C и нет осадков - НИКАКОЙ куртки!
- Учитывай сезон (май 2026)

Ответ - только список одежды, без объяснений."""

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=100,
            messages=[
                {"role": "system", "content": "You are a fashion advisor in Russian. Follow the jacket rule strictly."},
                {"role": "user", "content": prompt},
            ],
        )

        recommendation = response.choices[0].message.content.strip()

        # Validate jacket logic: add/remove jacket if AI got it wrong
        needs_jacket = avg_temp < 10 or has_precipitation
        jacket_keywords = ["куртка", "пальто", "ветровка", "жакет", "кардиган", "анорак"]
        has_jacket_mention = any(word in recommendation.lower() for word in jacket_keywords)

        # Fix if logic is wrong
        if needs_jacket and not has_jacket_mention:
            recommendation = f"Куртка (от {avg_temp:.1f}°C)\n{recommendation}"
        elif not needs_jacket and has_jacket_mention and avg_temp >= 10 and not has_precipitation:
            # Remove jacket mention if conditions don't warrant it
            lines = recommendation.split("\n")
            lines = [l for l in lines if not any(word in l.lower() for word in jacket_keywords)]
            recommendation = "\n".join(lines).strip()
            if not recommendation:
                recommendation = "Рубашка, джинсы, кроссовки"

        logger.info(f"✓ Clothing recommendation (temp:{avg_temp:.1f}°C, rain:{has_precipitation}, jacket_needed:{needs_jacket})")
        return recommendation

    except Exception as e:
        logger.warning(f"Failed to generate clothing recommendation: {e}")
        return None
