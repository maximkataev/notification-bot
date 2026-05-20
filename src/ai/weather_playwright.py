"""Weather fetching with Playwright (handles JavaScript rendering)."""

import asyncio
import logging
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

CONDITION_EMOJI = {
    "ясно": "☀️", "облачно": "☁️", "дождь": "🌧️", "снег": "❄️",
    "гроза": "⛈️", "туман": "🌫️", "переменная облачность": "⛅",
    "морось": "🌦️", "град": "🌨️", "ливень": "🌧️", "ледяной дождь": "🌧️",
}


async def _fetch_with_playwright(url: str, timeout_ms: int = 15000) -> Optional[str]:
    """Fetch page with Playwright (renders JavaScript)."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(2000)  # Extra wait for JS rendering
            html = await page.content()
            await context.close()
            await browser.close()
            return html
    except PlaywrightTimeoutError:
        logger.warning(f"Playwright timeout for {url}")
        return None
    except Exception as e:
        logger.warning(f"Playwright error: {type(e).__name__}: {str(e)[:100]}")
        return None


async def get_weather_gismeteo() -> Optional[Dict[str, Any]]:
    """Fetch from Gismeteo with Playwright."""
    url = "https://www.gismeteo.ru/weather-tbilisi-5277/"
    html = await _fetch_with_playwright(url)
    if html:
        logger.debug("✓ Gismeteo fetch success")
        return {"html": html, "source": "gismeteo"}
    else:
        logger.warning("❌ Gismeteo fetch failed")
        return None


async def get_weather_yandex() -> Optional[Dict[str, Any]]:
    """Fetch from Yandex with Playwright."""
    url = "https://yandex.ru/pogoda/ru/tbilisi"
    html = await _fetch_with_playwright(url)
    if html:
        logger.debug("✓ Yandex fetch success")
        return {"html": html, "source": "yandex"}
    else:
        logger.warning("❌ Yandex fetch failed")
        return None


def _parse_gismeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Gismeteo HTML (with multiple selector strategies)."""
    if not data or "html" not in data:
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        # Try multiple selectors
        cards = soup.find_all("div", class_="time-item")
        if not cards:
            cards = soup.find_all("div", class_="weather-card")
        if not cards:
            cards = soup.find_all("div", attrs={"data-period": True})
        if not cards:
            cards = soup.find_all("div", attrs={"class": lambda x: x and "period" in x})

        logger.debug(f"Gismeteo: found {len(cards)} cards")
        if not cards:
            return None

        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]

            # Temperature
            temp_elem = card.find("span", class_="unit")
            if not temp_elem:
                temp_elem = card.find("span", attrs={"class": lambda x: x and "temp" in x})
            if not temp_elem:
                temp_elem = card.find("div", attrs={"class": lambda x: x and "temp" in x})

            temp = None
            if temp_elem:
                try:
                    temp_str = temp_elem.get_text(strip=True)
                    temp_val = temp_str.split("°")[0].strip()
                    temp = float(temp_val.replace("−", "-").replace("–", "-"))
                except (ValueError, AttributeError):
                    temp = None

            # Condition
            condition = "облачно"
            cond_elem = card.find("div", attrs={"class": lambda x: x and "description" in x})
            if not cond_elem:
                cond_elem = card.find("div", attrs={"class": lambda x: x and "condition" in x})
            if cond_elem:
                condition = cond_elem.get_text(strip=True).lower()

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
        logger.warning(f"Gismeteo parse error: {type(e).__name__}: {str(e)[:100]}")
        return None


def _parse_yandex(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Yandex HTML (with multiple selector strategies)."""
    if not data or "html" not in data:
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        # Try multiple selectors
        cards = soup.find_all("div", attrs={"class": lambda x: x and "forecast-item" in x})
        if not cards:
            cards = soup.find_all("li", attrs={"class": lambda x: x and "forecast" in x})
        if not cards:
            cards = soup.find_all("div", attrs={"class": lambda x: x and "period" in x})

        logger.debug(f"Yandex: found {len(cards)} cards")
        if not cards:
            return None

        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]

            # Temperature
            temp_elem = card.find("span", attrs={"class": lambda x: x and "temp" in x})
            if not temp_elem:
                temp_elem = card.find("div", attrs={"class": lambda x: x and "temperature" in x})

            temp = None
            if temp_elem:
                try:
                    temp_str = temp_elem.get_text(strip=True)
                    temp_val = temp_str.split("°")[0].strip().replace("+", "")
                    temp = float(temp_val.replace("−", "-").replace("–", "-"))
                except (ValueError, AttributeError):
                    temp = None

            # Condition
            condition = "облачно"
            cond_elem = card.find("div", attrs={"class": lambda x: x and "condition" in x})
            if not cond_elem:
                cond_elem = card.find("div", attrs={"class": lambda x: x and "description" in x})
            if cond_elem:
                condition = cond_elem.get_text(strip=True).lower()

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
        logger.warning(f"Yandex parse error: {type(e).__name__}: {str(e)[:100]}")
        return None


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch and aggregate weather from both sources."""
    logger.info("🌤️ Fetching weather (Gismeteo + Yandex via Playwright)...")

    gismeteo_data, yandex_data = await asyncio.gather(
        get_weather_gismeteo(),
        get_weather_yandex(),
        return_exceptions=True,
    )

    results = []

    # Process Gismeteo
    if isinstance(gismeteo_data, Exception):
        logger.warning(f"Gismeteo: {gismeteo_data}")
    elif gismeteo_data:
        parsed = _parse_gismeteo(gismeteo_data)
        if parsed:
            results.append(("gismeteo", parsed))
            logger.info("✓ Gismeteo: OK")
        else:
            logger.warning("✗ Gismeteo: parse failed")

    # Process Yandex
    if isinstance(yandex_data, Exception):
        logger.warning(f"Yandex: {yandex_data}")
    elif yandex_data:
        parsed = _parse_yandex(yandex_data)
        if parsed:
            results.append(("yandex", parsed))
            logger.info("✓ Yandex: OK")
        else:
            logger.warning("✗ Yandex: parse failed")

    if not results:
        logger.error("❌ All weather sources failed")
        return None

    logger.info(f"Aggregating from {len(results)} source(s)")
    aggregated = {}

    for period in ["night", "morning", "day", "evening"]:
        temps = [r[1][period]["temperature"] for r in results if period in r[1]]
        conditions = [r[1][period]["condition"] for r in results if period in r[1]]
        precips = [r[1][period]["precipitation_mm"] for r in results if period in r[1]]

        if temps:
            avg_temp = round(sum(temps) / len(temps), 1)
            avg_precip = round(sum(precips) / len(precips), 1) if precips else 0.0
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
