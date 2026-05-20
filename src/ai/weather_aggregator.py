"""Aggregate weather data from Gismeteo and Yandex."""

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Constants
PERIODS = ["night", "morning", "day", "evening"]
FETCH_TIMEOUT_SECONDS = 10.0
JACKET_TEMP_THRESHOLD = 10
CLOTHING_MAX_TOKENS = 100

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


def _parse_temperature(temp_str: str) -> Optional[float]:
    """Parse temperature from string, handling various dash variants."""
    try:
        cleaned = temp_str.split("°")[0].strip()
        cleaned = cleaned.replace("−", "-").replace("–", "-")
        return float(cleaned)
    except (ValueError, AttributeError, IndexError):
        return None


def _extract_temperature(card) -> Optional[float]:
    """Extract temperature from a weather card."""
    temp_text = card.find(class_=lambda x: x and "temp" in x.lower())
    if not temp_text:
        temp_text = card.find(class_=lambda x: x and "temperature" in x.lower())
    if temp_text:
        temp_str = temp_text.get_text(strip=True)
        return _parse_temperature(temp_str)
    return None


def _extract_condition(card) -> str:
    """Extract weather condition from a card."""
    condition_elem = card.find(class_=lambda x: x and "condition" in x.lower())
    if not condition_elem:
        condition_elem = card.find(class_=lambda x: x and ("sky" in x.lower() or "desc" in x.lower()))
    if condition_elem:
        return condition_elem.get_text(strip=True).lower()
    return "облачно"


async def get_weather_gismeteo() -> Optional[Dict[str, Any]]:
    """Fetch weather from Gismeteo HTML page."""
    url = "https://www.gismeteo.ru/weather-tbilisi-5277/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
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
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            logger.debug("✓ Yandex fetch success")
            return {"html": response.text, "source": "yandex"}
    except Exception as e:
        logger.warning(f"❌ Yandex fetch failed: {type(e).__name__}")
        return None


def _parse_weather_html(html: str, source: str) -> Optional[Dict[str, Dict]]:
    """Parse weather HTML from various sources."""
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        weather_by_period = {}

        cards = []
        if source == "gismeteo":
            cards = soup.find_all(class_=["weather-item", "weather-card", "period"])
            if not cards:
                cards = soup.find_all("div", class_=lambda x: x and "weather" in x.lower())
        elif source == "yandex":
            cards = soup.find_all(class_=lambda x: x and ("forecast" in x.lower() or "period" in x.lower()))
            if not cards:
                cards = soup.find_all("div", class_=lambda x: x and "temp" in x.lower())

        for idx, period_name in enumerate(PERIODS[:len(cards)]):
            card = cards[idx]
            temp = _extract_temperature(card)
            condition = _extract_condition(card)
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                }

        return weather_by_period or None
    except Exception as e:
        logger.warning(f"Failed to parse {source}: {e}")
        return None


def _parse_gismeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Gismeteo HTML to extract weather by periods."""
    if not data or "html" not in data:
        return None
    return _parse_weather_html(data["html"], "gismeteo")


def _parse_yandex(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Yandex Pogoda HTML to extract weather by periods."""
    if not data or "html" not in data:
        return None
    return _parse_weather_html(data["html"], "yandex")


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch and aggregate weather from Gismeteo and Yandex."""
    logger.info("🌤️ Fetching weather from Gismeteo and Yandex...")

    gismeteo_data, yandex_data = await asyncio.gather(
        get_weather_gismeteo(),
        get_weather_yandex(),
        return_exceptions=False,
    )

    results = []

    if gismeteo_data:
        parsed = _parse_gismeteo(gismeteo_data)
        if parsed:
            results.append(("gismeteo", parsed))
            logger.info("✓ Gismeteo: OK")
        else:
            logger.warning("✗ Gismeteo: parse failed")
    else:
        logger.warning("✗ Gismeteo: fetch failed")

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

    for period in PERIODS:
        temps = [r[1][period]["temperature"] for r in results if period in r[1]]
        conditions = [r[1][period]["condition"] for r in results if period in r[1]]

        if temps:
            avg_temp = round(sum(temps) / len(temps), 1)
            condition = conditions[0] if conditions else "облачно"
            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            aggregated[period] = {
                "temperature": avg_temp,
                "condition": condition,
                "emoji": emoji,
            }

    return aggregated or None


async def generate_clothing_recommendation(weather: Optional[Dict[str, Dict]]) -> Optional[str]:
    """Generate clothing recommendation based on weather with jacket logic validation."""
    if not weather:
        return None

    try:
        # Extract temperatures from available periods
        temps = [weather[p]["temperature"] for p in ["morning", "day", "evening"] if p in weather]
        if not temps:
            return None

        avg_temp = sum(temps) / len(temps)
        min_temp = min(temps)
        temp_range = f"{min_temp:.1f}°C - {max(temps):.1f}°C"

        # Check for rain keywords in conditions
        rain_keywords = ["дождь", "снег", "гроза", "морось", "ливень", "ледяной дождь", "град"]
        has_precipitation = any(
            any(kw in weather.get(p, {}).get("condition", "").lower() for kw in rain_keywords)
            for p in ["morning", "day", "evening"]
        )

        conditions = ", ".join(weather[p]["condition"] for p in ["morning", "day", "evening"] if p in weather)

        prompt = f"""Рекомендуй, во что одеться на день в Тбилиси.

Погода:
- Температура: {temp_range} (минимум {min_temp:.1f}°C)
- Условия: {conditions}
- {'Ожидаются осадки' if has_precipitation else 'Без осадков'}

ПРАВИЛО ДЛЯ КУРТКИ:
Куртка/пальто нужна ТОЛЬКО если:
  • Температура ниже {JACKET_TEMP_THRESHOLD}°C, ИЛИ
  • Ожидаются осадки (дождь, снег, гроза)
В других случаях БЕЗ куртки!

Дай практичную рекомендацию (2-3 вещи) на русском. Будь конкретен:
- Укажи конкретные вещи (рубашка, джинсы, кроссовки и т.д.)
- Если {'ЕСТЬ осадки ИЛИ' if has_precipitation else ''} температура ниже {JACKET_TEMP_THRESHOLD}°C - укажи конкретную куртку/пальто
- Если выше {JACKET_TEMP_THRESHOLD}°C и нет осадков - НИКАКОЙ куртки!
- Учитывай сезон (май 2026)

Ответ - только список одежды, без объяснений."""

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=CLOTHING_MAX_TOKENS,
            messages=[
                {"role": "system", "content": "You are a fashion advisor in Russian. Follow the jacket rule strictly."},
                {"role": "user", "content": prompt},
            ],
        )

        recommendation = response.choices[0].message.content.strip()

        # Validate and fix jacket logic if needed
        needs_jacket = avg_temp < JACKET_TEMP_THRESHOLD or has_precipitation
        jacket_keywords = ["куртка", "пальто", "ветровка", "жакет", "кардиган", "анорак"]
        has_jacket_mention = any(word in recommendation.lower() for word in jacket_keywords)

        if needs_jacket and not has_jacket_mention:
            recommendation = f"Куртка (от {avg_temp:.1f}°C)\n{recommendation}"
        elif not needs_jacket and has_jacket_mention and avg_temp >= JACKET_TEMP_THRESHOLD and not has_precipitation:
            lines = recommendation.split("\n")
            lines = [l for l in lines if not any(word in l.lower() for word in jacket_keywords)]
            recommendation = "\n".join(lines).strip() or "Рубашка, джинсы, кроссовки"

        logger.info(f"✓ Clothing recommendation (temp:{avg_temp:.1f}°C, rain:{has_precipitation}, jacket_needed:{needs_jacket})")
        return recommendation

    except Exception as e:
        logger.warning(f"Failed to generate clothing recommendation: {e}")
        return None
