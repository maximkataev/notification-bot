"""Weather fetching with Playwright (handles JavaScript rendering) - with detailed logging."""

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


async def _fetch_with_playwright(url: str, timeout_ms: int = 15000, source: str = "source") -> Optional[str]:
    """Fetch page with Playwright (renders JavaScript)."""
    try:
        logger.info(f"[{source}] Launching browser and loading {url}...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            logger.info(f"[{source}] Navigating to {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            logger.info(f"[{source}] Page loaded, waiting for JavaScript to render...")
            await page.wait_for_timeout(3000)  # Wait for JS rendering

            html = await page.content()
            html_size = len(html)

            logger.info(f"[{source}] ✓ HTML fetched: {html_size} bytes")

            await context.close()
            await browser.close()
            return html
    except PlaywrightTimeoutError:
        logger.error(f"[{source}] ❌ Playwright timeout ({timeout_ms}ms)")
        return None
    except Exception as e:
        logger.error(f"[{source}] ❌ Playwright error: {type(e).__name__}: {str(e)[:200]}")
        return None


async def get_weather_gismeteo() -> Optional[Dict[str, Any]]:
    """Fetch from Gismeteo with Playwright."""
    url = "https://www.gismeteo.ru/weather-tbilisi-5277/"
    html = await _fetch_with_playwright(url, source="GISMETEO")
    if html:
        logger.info("[GISMETEO] ✓ Fetch success")
        return {"html": html, "source": "gismeteo"}
    else:
        logger.warning("[GISMETEO] ❌ Fetch failed")
        return None


async def get_weather_yandex() -> Optional[Dict[str, Any]]:
    """Fetch from Yandex with Playwright."""
    url = "https://yandex.ru/pogoda/ru/tbilisi"
    html = await _fetch_with_playwright(url, source="YANDEX")
    if html:
        logger.info("[YANDEX] ✓ Fetch success")
        return {"html": html, "source": "yandex"}
    else:
        logger.warning("[YANDEX] ❌ Fetch failed")
        return None


def _parse_gismeteo(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Gismeteo HTML (with multiple selector strategies)."""
    if not data or "html" not in data:
        logger.warning("[GISMETEO] No HTML data provided")
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        logger.info("[GISMETEO] Parsing HTML with multiple selectors...")

        # Try multiple selectors
        selectors = [
            ("div.time-item", soup.find_all("div", class_="time-item")),
            ("div.weather-card", soup.find_all("div", class_="weather-card")),
            ("div[data-period]", soup.find_all("div", attrs={"data-period": True})),
            ("div with 'period' class", soup.find_all("div", attrs={"class": lambda x: x and "period" in x})),
            ("div with 'weather' class", soup.find_all("div", attrs={"class": lambda x: x and "weather" in x})),
        ]

        cards = []
        for selector_name, result in selectors:
            logger.debug(f"[GISMETEO] Selector '{selector_name}': {len(result)} elements")
            if result:
                cards = result
                logger.info(f"[GISMETEO] ✓ Found {len(cards)} cards with selector: {selector_name}")
                break

        if not cards:
            # Log HTML snippet for debugging
            html_snippet = data["html"][:1000]
            logger.error(f"[GISMETEO] ❌ No weather cards found. HTML snippet:\n{html_snippet}")
            return None

        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]
            logger.debug(f"[GISMETEO] Processing period {idx}: {period_name}")

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
                    logger.debug(f"[GISMETEO] {period_name}: temp={temp}°C")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"[GISMETEO] Failed to parse temp for {period_name}: {e}")
                    temp = None
            else:
                logger.debug(f"[GISMETEO] No temperature element found for {period_name}")

            # Condition
            condition = "облачно"
            cond_elem = card.find("div", attrs={"class": lambda x: x and "description" in x})
            if not cond_elem:
                cond_elem = card.find("div", attrs={"class": lambda x: x and "condition" in x})
            if cond_elem:
                condition = cond_elem.get_text(strip=True).lower()
                logger.debug(f"[GISMETEO] {period_name}: condition={condition}")

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }

        logger.info(f"[GISMETEO] ✓ Parsed {len(weather_by_period)} periods")
        return weather_by_period if weather_by_period else None

    except Exception as e:
        logger.error(f"[GISMETEO] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


def _parse_yandex(data: Dict) -> Optional[Dict[str, Dict]]:
    """Parse Yandex HTML (with multiple selector strategies)."""
    if not data or "html" not in data:
        logger.warning("[YANDEX] No HTML data provided")
        return None

    try:
        soup = BeautifulSoup(data["html"], "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        logger.info("[YANDEX] Parsing HTML with multiple selectors...")

        # Try multiple selectors
        selectors = [
            ("div with 'forecast-item' class", soup.find_all("div", attrs={"class": lambda x: x and "forecast-item" in x})),
            ("li with 'forecast' class", soup.find_all("li", attrs={"class": lambda x: x and "forecast" in x})),
            ("div with 'period' class", soup.find_all("div", attrs={"class": lambda x: x and "period" in x})),
            ("div with 'temp' class", soup.find_all("div", attrs={"class": lambda x: x and "temp" in x})),
            ("div.weather-forecast", soup.find_all("div", class_="weather-forecast")),
        ]

        cards = []
        for selector_name, result in selectors:
            logger.debug(f"[YANDEX] Selector '{selector_name}': {len(result)} elements")
            if result:
                cards = result
                logger.info(f"[YANDEX] ✓ Found {len(cards)} cards with selector: {selector_name}")
                break

        if not cards:
            # Log HTML snippet for debugging
            html_snippet = data["html"][:1000]
            logger.error(f"[YANDEX] ❌ No weather cards found. HTML snippet:\n{html_snippet}")
            return None

        for idx, period_name in enumerate(periods[:len(cards)]):
            card = cards[idx]
            logger.debug(f"[YANDEX] Processing period {idx}: {period_name}")

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
                    logger.debug(f"[YANDEX] {period_name}: temp={temp}°C")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"[YANDEX] Failed to parse temp for {period_name}: {e}")
                    temp = None
            else:
                logger.debug(f"[YANDEX] No temperature element found for {period_name}")

            # Condition
            condition = "облачно"
            cond_elem = card.find("div", attrs={"class": lambda x: x and "condition" in x})
            if not cond_elem:
                cond_elem = card.find("div", attrs={"class": lambda x: x and "description" in x})
            if cond_elem:
                condition = cond_elem.get_text(strip=True).lower()
                logger.debug(f"[YANDEX] {period_name}: condition={condition}")

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }

        logger.info(f"[YANDEX] ✓ Parsed {len(weather_by_period)} periods")
        return weather_by_period if weather_by_period else None

    except Exception as e:
        logger.error(f"[YANDEX] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
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
        logger.error(f"[GISMETEO] Exception: {type(gismeteo_data).__name__}: {str(gismeteo_data)[:200]}")
    elif gismeteo_data:
        parsed = _parse_gismeteo(gismeteo_data)
        if parsed:
            results.append(("gismeteo", parsed))
            logger.info("✓ Gismeteo: OK")
        else:
            logger.warning("✗ Gismeteo: parse failed")
    else:
        logger.warning("[GISMETEO] Fetch returned None")

    # Process Yandex
    if isinstance(yandex_data, Exception):
        logger.error(f"[YANDEX] Exception: {type(yandex_data).__name__}: {str(yandex_data)[:200]}")
    elif yandex_data:
        parsed = _parse_yandex(yandex_data)
        if parsed:
            results.append(("yandex", parsed))
            logger.info("✓ Yandex: OK")
        else:
            logger.warning("✗ Yandex: parse failed")
    else:
        logger.warning("[YANDEX] Fetch returned None")

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
