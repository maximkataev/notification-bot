"""Weather fetching from BBC Weather with world-weather.ru fallback."""

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
    "sunny": "☀️", "clear": "☀️", "partly cloudy": "⛅", "cloudy": "☁️",
    "overcast": "☁️", "light rain": "🌦️", "rain": "🌧️", "heavy rain": "🌧️",
    "showers": "🌧️", "thunderstorms": "⛈️", "snow": "❄️", "sleet": "🌨️",
}

# Map BBC weather descriptions to Russian
BBC_TO_RU = {
    "sunny": "ясно",
    "clear": "ясно",
    "partly cloudy": "переменная облачность",
    "cloudy": "облачно",
    "overcast": "облачно",
    "light rain": "морось",
    "rain": "дождь",
    "heavy rain": "ливень",
    "showers": "дождь",
    "thunderstorms": "гроза",
    "thunder": "гроза",
    "snow": "снег",
    "sleet": "град",
    "mist": "туман",
    "fog": "туман",
}


async def get_weather_bbc() -> Optional[Dict[str, Dict]]:
    """Fetch weather from BBC Weather for Tbilisi (611717)."""
    url = "https://www.bbc.com/weather/611717"  # Tbilisi code

    try:
        logger.info("[BBC] Launching browser and loading page...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            logger.info(f"[BBC] Navigating to {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            logger.info("[BBC] Page loaded, waiting for content to render...")
            await page.wait_for_timeout(3000)

            html = await page.content()
            html_size = len(html)
            logger.info(f"[BBC] ✓ HTML fetched: {html_size} bytes")

            await context.close()
            await browser.close()

            # Parse weather from HTML
            return _parse_bbc_weather(html)

    except PlaywrightTimeoutError:
        logger.error("[BBC] ❌ Playwright timeout")
        return None
    except Exception as e:
        logger.error(f"[BBC] ❌ Fetch error: {type(e).__name__}: {str(e)[:200]}")
        return None


def _parse_bbc_weather(html: str) -> Optional[Dict[str, Dict]]:
    """Parse BBC Weather HTML to extract weather by periods."""
    if not html:
        logger.error("[BBC] No HTML provided")
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        logger.info("[BBC] Parsing HTML...")

        # BBC Weather has forecast items with specific structure
        # Look for daily forecast items
        forecast_items = soup.find_all("div", attrs={"data-testid": lambda x: x and "forecast" in x.lower()})
        logger.debug(f"[BBC] Found {len(forecast_items)} forecast items with data-testid")

        if not forecast_items:
            # Try alternative selectors
            forecast_items = soup.find_all("div", class_=lambda x: x and "forecast" in x.lower())
            logger.debug(f"[BBC] Found {len(forecast_items)} forecast items with class selector")

        if not forecast_items:
            # BBC uses specific structure - look for weather cards
            forecast_items = soup.find_all("div", attrs={"role": "img"})
            logger.debug(f"[BBC] Found {len(forecast_items)} items with role=img")

        if not forecast_items:
            # Last resort - look for any div with temperature
            forecast_items = soup.find_all("div", attrs={"aria-label": lambda x: x and ("°" in x or "temperature" in x.lower())})
            logger.debug(f"[BBC] Found {len(forecast_items)} items with aria-label temperature")

        if not forecast_items:
            logger.error("[BBC] ❌ No forecast items found. HTML preview:")
            logger.error(html[:2000])
            return None

        logger.info(f"[BBC] Found {len(forecast_items)} forecast items")

        # Extract period-by-period weather
        # BBC organizes as: Today (day/night), Tomorrow (day/night), etc.
        parsed_count = 0

        for idx, item in enumerate(forecast_items[:len(periods)]):
            period_name = periods[idx] if idx < len(periods) else None
            if not period_name:
                break

            logger.debug(f"[BBC] Processing item {idx}: {period_name}")

            # Try to extract temperature
            temp = None

            # Look for temperature in various places
            temp_elem = item.find(attrs={"aria-label": lambda x: x and "°" in x})
            if temp_elem:
                try:
                    temp_text = temp_elem.get_text(strip=True)
                    # Extract number from "21°C" or similar
                    temp_val = ''.join(c for c in temp_text if c.isdigit() or c == '-')
                    if temp_val:
                        temp = float(temp_val)
                        logger.debug(f"[BBC] {period_name}: temp={temp}°C")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"[BBC] Failed to parse temp: {e}")

            # Try to extract condition
            condition = "облачно"

            # BBC uses aria-label or title attributes for weather conditions
            aria_label = item.get("aria-label", "").lower()
            title = item.get("title", "").lower()
            alt_text = item.get("alt", "").lower()

            combined_text = f"{aria_label} {title} {alt_text}".lower()
            logger.debug(f"[BBC] {period_name}: aria-label='{aria_label}'")

            # Map BBC description to Russian
            for bbc_cond, ru_cond in BBC_TO_RU.items():
                if bbc_cond in combined_text:
                    condition = ru_cond
                    logger.debug(f"[BBC] {period_name}: condition={condition}")
                    break

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }
                parsed_count += 1

        logger.info(f"[BBC] ✓ Parsed {parsed_count} periods")
        return weather_by_period if weather_by_period else None

    except Exception as e:
        logger.error(f"[BBC] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


async def get_weather_worldweather() -> Optional[Dict[str, Dict]]:
    """Fetch weather from world-weather.ru (fallback source)."""
    url = "https://world-weather.ru/pogoda/georgia/tbilisi/7days/"

    try:
        logger.info("[WORLDWEATHER] Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            logger.info(f"[WORLDWEATHER] Navigating to {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            logger.info("[WORLDWEATHER] Page loaded, waiting for content...")
            await page.wait_for_timeout(3000)

            html = await page.content()
            html_size = len(html)
            logger.info(f"[WORLDWEATHER] ✓ HTML fetched: {html_size} bytes")

            await context.close()
            await browser.close()

            return _parse_worldweather(html)

    except PlaywrightTimeoutError:
        logger.error("[WORLDWEATHER] ❌ Timeout")
        return None
    except Exception as e:
        logger.error(f"[WORLDWEATHER] ❌ Fetch error: {type(e).__name__}: {str(e)[:200]}")
        return None


def _parse_worldweather(html: str) -> Optional[Dict[str, Dict]]:
    """Parse world-weather.ru HTML."""
    if not html:
        logger.error("[WORLDWEATHER] No HTML provided")
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        weather_by_period = {}
        periods = ["night", "morning", "day", "evening"]

        logger.info("[WORLDWEATHER] Parsing HTML...")

        # Look for weather forecast cards
        # world-weather.ru uses specific structure
        forecast_items = soup.find_all("div", class_=lambda x: x and "forecast" in x.lower())
        logger.debug(f"[WORLDWEATHER] Found {len(forecast_items)} forecast items")

        if not forecast_items:
            forecast_items = soup.find_all("div", attrs={"class": lambda x: x and "weather" in x.lower()})
            logger.debug(f"[WORLDWEATHER] Found {len(forecast_items)} weather items")

        if not forecast_items:
            forecast_items = soup.find_all("div", attrs={"data-weather": True})
            logger.debug(f"[WORLDWEATHER] Found {len(forecast_items)} data-weather items")

        if not forecast_items:
            logger.error("[WORLDWEATHER] ❌ No forecast items found. HTML preview:")
            logger.error(html[:2000])
            return None

        logger.info(f"[WORLDWEATHER] Found {len(forecast_items)} forecast items")

        parsed_count = 0

        for idx, item in enumerate(forecast_items[:len(periods)]):
            period_name = periods[idx] if idx < len(periods) else None
            if not period_name:
                break

            logger.debug(f"[WORLDWEATHER] Processing item {idx}: {period_name}")

            # Extract temperature
            temp = None
            temp_elem = item.find(attrs={"class": lambda x: x and "temp" in x.lower()})
            if not temp_elem:
                temp_elem = item.find("span")
            if not temp_elem:
                temp_elem = item.find("div")

            if temp_elem:
                try:
                    temp_text = temp_elem.get_text(strip=True)
                    temp_val = ''.join(c for c in temp_text if c.isdigit() or c == '-')
                    if temp_val:
                        temp = float(temp_val)
                        logger.debug(f"[WORLDWEATHER] {period_name}: temp={temp}°C")
                except (ValueError, AttributeError):
                    pass

            # Extract condition
            condition = "облачно"
            text_content = item.get_text(strip=True).lower()
            alt_text = item.get("alt", "").lower()
            title = item.get("title", "").lower()

            combined_text = f"{text_content} {alt_text} {title}".lower()
            logger.debug(f"[WORLDWEATHER] {period_name}: text='{combined_text[:100]}'")

            # Map conditions to Russian
            for bbc_cond, ru_cond in BBC_TO_RU.items():
                if bbc_cond in combined_text:
                    condition = ru_cond
                    logger.debug(f"[WORLDWEATHER] {period_name}: condition={condition}")
                    break

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_by_period[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }
                parsed_count += 1

        logger.info(f"[WORLDWEATHER] ✓ Parsed {parsed_count} periods")
        return weather_by_period if weather_by_period else None

    except Exception as e:
        logger.error(f"[WORLDWEATHER] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch weather from BBC Weather, fallback to world-weather.ru."""
    logger.info("🌤️ Fetching weather (BBC → world-weather.ru)...")

    # Try BBC first
    bbc_weather, worldweather = await asyncio.gather(
        get_weather_bbc(),
        get_weather_worldweather(),
        return_exceptions=True,
    )

    results = []

    # Process BBC
    if isinstance(bbc_weather, Exception):
        logger.warning(f"[BBC] Exception: {bbc_weather}")
    elif bbc_weather:
        logger.info(f"✓ BBC Weather: OK ({len(bbc_weather)} periods)")
        results.append(("bbc", bbc_weather))
    else:
        logger.warning("[BBC] Fetch returned None, trying fallback...")

    # Process world-weather.ru fallback
    if not results:
        if isinstance(worldweather, Exception):
            logger.warning(f"[WORLDWEATHER] Exception: {worldweather}")
        elif worldweather:
            logger.info(f"✓ World-Weather: OK ({len(worldweather)} periods)")
            results.append(("worldweather", worldweather))
        else:
            logger.error("❌ All weather sources failed")
            return None

    if not results:
        logger.error("❌ All weather sources failed")
        return None

    # Use first successful source
    aggregated = results[0][1]
    source_name = results[0][0]
    logger.info(f"Using weather from: {source_name}")

    return aggregated


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
