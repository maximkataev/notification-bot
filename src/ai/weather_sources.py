"""Weather from BBC, world-weather.ru, wttr.in with smart fallback."""

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

CONDITION_EMOJI = {
    "ясно": "☀️", "облачно": "☁️", "дождь": "🌧️", "снег": "❄️",
    "гроза": "⛈️", "туман": "🌫️", "переменная облачность": "⛅",
    "морось": "🌦️", "град": "🌨️", "ливень": "🌧️", "ледяной дождь": "🌧️",
}


# ============ BBC WEATHER ============

async def _fetch_bbc_html() -> Optional[str]:
    """Fetch BBC Weather page with Playwright."""
    try:
        logger.info("[BBC] Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            url = "https://www.bbc.com/weather/611717"
            logger.info(f"[BBC] Loading {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)

            html = await page.content()
            logger.info(f"[BBC] ✓ HTML fetched: {len(html)} bytes")

            await context.close()
            await browser.close()
            return html

    except PlaywrightTimeoutError:
        logger.error("[BBC] ❌ Timeout")
        return None
    except Exception as e:
        logger.error(f"[BBC] ❌ Fetch error: {type(e).__name__}: {str(e)[:100]}")
        return None


def _parse_bbc(html: str) -> Optional[Dict[str, Dict]]:
    """Parse BBC Weather HTML using embedded JSON data."""
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("[BBC] Parsing HTML (JSON method)...")

        # BBC embeds all data as JSON in script tags
        scripts = soup.find_all("script", type="application/json")
        logger.debug(f"[BBC] Found {len(scripts)} JSON script tags")

        if not scripts:
            logger.error("[BBC] ❌ No JSON data found in HTML")
            return None

        for script in scripts:
            if not script.string:
                continue

            try:
                import json
                data = json.loads(script.string.strip())
            except Exception:
                continue

            # Check if this is the main weather data script
            if not isinstance(data, dict) or "data" not in data:
                continue

            data_obj = data["data"]
            if not isinstance(data_obj, dict) or "forecasts" not in data_obj:
                continue

            forecasts = data_obj["forecasts"]
            if not forecasts:
                continue

            # Get today's forecast (first forecast)
            today_forecast = forecasts[0]
            if not isinstance(today_forecast, dict):
                continue

            # Extract hourly data from detailed forecast
            weather_by_period = {}
            periods = {
                "night": (0, 6),
                "morning": (6, 12),
                "day": (12, 18),
                "evening": (18, 24),
            }

            if "detailed" not in today_forecast:
                logger.error("[BBC] ❌ No detailed forecast")
                return None

            detailed = today_forecast["detailed"]
            if "reports" not in detailed:
                logger.error("[BBC] ❌ No hourly reports in detailed forecast")
                return None

            reports = detailed["reports"]
            logger.debug(f"[BBC] Found {len(reports)} hourly reports")

            # Group reports by period and calculate average temps
            period_temps = {period: [] for period in periods.keys()}
            condition_overall = "облачно"

            for report in reports:
                timeslot = report.get("timeslot", "")
                if not timeslot:
                    continue

                try:
                    hour = int(timeslot.split(":")[0])
                    temp_c = report.get("temperatureC")

                    if temp_c is None:
                        continue

                    # Determine which period this hour belongs to
                    for period_name, (start_hour, end_hour) in periods.items():
                        if start_hour <= hour < end_hour:
                            period_temps[period_name].append(temp_c)
                            break

                except (ValueError, IndexError, AttributeError):
                    pass

            # Get overall weather description from summary
            if "summary" in today_forecast:
                summary = today_forecast["summary"]
                if isinstance(summary, dict) and "report" in summary:
                    report_data = summary["report"]
                    weather_text = report_data.get("weatherTypeText", "").lower()

                    # Map English weather to Russian
                    if "rain" in weather_text or "shower" in weather_text:
                        condition_overall = "дождь"
                    elif "thunderstorm" in weather_text or "thundery" in weather_text:
                        condition_overall = "гроза"
                    elif "snow" in weather_text:
                        condition_overall = "снег"
                    elif "clear" in weather_text or "sunny" in weather_text:
                        condition_overall = "ясно"
                    elif "cloud" in weather_text:
                        condition_overall = "облачно"
                    elif "fog" in weather_text or "mist" in weather_text:
                        condition_overall = "туман"
                    else:
                        condition_overall = "облачно"

                    logger.debug(f"[BBC] Weather description: {weather_text} → {condition_overall}")

            # Calculate average temperature for each period
            for period_name, temps in period_temps.items():
                if temps:
                    avg_temp = sum(temps) / len(temps)
                    emoji = CONDITION_EMOJI.get(condition_overall, "🌤️")
                    weather_by_period[period_name] = {
                        "temperature": round(avg_temp, 1),
                        "condition": condition_overall,
                        "emoji": emoji,
                        "precipitation_mm": 0.0,
                    }
                    logger.info(f"[BBC] {period_name}: {avg_temp:.1f}°C ({len(temps)} hours), {condition_overall}")

            # If we have fewer than 4 periods, try to fill gaps using daily summary min/max
            if len(weather_by_period) < 4 and "summary" in today_forecast:
                summary = today_forecast["summary"]
                if isinstance(summary, dict) and "report" in summary:
                    report_data = summary["report"]
                    min_temp = report_data.get("minTempC")
                    max_temp = report_data.get("maxTempC")

                    if min_temp is not None and max_temp is not None:
                        logger.debug(f"[BBC] Daily min={min_temp}°C, max={max_temp}°C")

                        # Fill missing periods with estimated temperatures
                        # Night: use lower temps (around min)
                        # Morning: use rising temps (from min to avg)
                        # Day: use higher temps (around max or slightly below)
                        # Evening: use cooling temps (between day and min)

                        if "night" not in weather_by_period:
                            night_temp = round(min_temp + 0.5)  # Slightly above minimum
                            weather_by_period["night"] = {
                                "temperature": night_temp,
                                "condition": condition_overall,
                                "emoji": CONDITION_EMOJI.get(condition_overall, "🌤️"),
                                "precipitation_mm": 0.0,
                            }
                            logger.info(f"[BBC] night (filled): {night_temp}°C (from daily min)")

                        if "morning" not in weather_by_period:
                            morning_temp = round((min_temp + max_temp) / 2 - 1)  # Between min and max, slightly lower
                            weather_by_period["morning"] = {
                                "temperature": morning_temp,
                                "condition": condition_overall,
                                "emoji": CONDITION_EMOJI.get(condition_overall, "🌤️"),
                                "precipitation_mm": 0.0,
                            }
                            logger.info(f"[BBC] morning (filled): {morning_temp}°C (estimated)")

                        if "day" not in weather_by_period:
                            day_temp = round(max_temp - 0.5)  # Slightly below maximum
                            weather_by_period["day"] = {
                                "temperature": day_temp,
                                "condition": condition_overall,
                                "emoji": CONDITION_EMOJI.get(condition_overall, "🌤️"),
                                "precipitation_mm": 0.0,
                            }
                            logger.info(f"[BBC] day (filled): {day_temp}°C (from daily max)")

                        if "evening" not in weather_by_period:
                            evening_temp = round((min_temp + max_temp) / 2)  # Between min and max
                            weather_by_period["evening"] = {
                                "temperature": evening_temp,
                                "condition": condition_overall,
                                "emoji": CONDITION_EMOJI.get(condition_overall, "🌤️"),
                                "precipitation_mm": 0.0,
                            }
                            logger.info(f"[BBC] evening (filled): {evening_temp}°C (estimated)")

            if weather_by_period:
                logger.info(f"[BBC] ✓ Parsed {len(weather_by_period)} periods")
                return weather_by_period

            logger.error("[BBC] ❌ No period data extracted")
            return None

        logger.error("[BBC] ❌ No valid weather data JSON found")
        return None

    except Exception as e:
        logger.error(f"[BBC] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


# ============ WORLD-WEATHER.RU ============

async def _fetch_worldweather_html() -> Optional[str]:
    """Fetch world-weather.ru page with Playwright."""
    try:
        logger.info("[WORLDWEATHER] Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            url = "https://world-weather.ru/pogoda/georgia/tbilisi/7days/"
            logger.info(f"[WORLDWEATHER] Loading {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)

            html = await page.content()
            logger.info(f"[WORLDWEATHER] ✓ HTML fetched: {len(html)} bytes")

            await context.close()
            await browser.close()
            return html

    except PlaywrightTimeoutError:
        logger.error("[WORLDWEATHER] ❌ Timeout")
        return None
    except Exception as e:
        logger.error(f"[WORLDWEATHER] ❌ Fetch error: {type(e).__name__}: {str(e)[:100]}")
        return None


def _parse_worldweather(html: str) -> Optional[Dict[str, Dict]]:
    """Parse world-weather.ru HTML - smart selector approach."""
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("[WORLDWEATHER] Parsing HTML...")

        weather_data = {}
        periods = ["night", "morning", "day", "evening"]

        # Look for temperature values in HTML
        all_divs = soup.find_all("div")
        logger.debug(f"[WORLDWEATHER] Found {len(all_divs)} total divs")

        temp_candidates = []
        for div in all_divs:
            text = div.get_text(strip=True)
            if "°" in text and any(c.isdigit() for c in text):
                temp_candidates.append(div)

        logger.info(f"[WORLDWEATHER] Found {len(temp_candidates)} temperature candidates")

        if not temp_candidates:
            logger.error("[WORLDWEATHER] ❌ No temperature data found")
            return None

        # Extract from candidates
        for idx, div in enumerate(temp_candidates[:len(periods)]):
            period_name = periods[idx] if idx < len(periods) else None
            if not period_name:
                break

            text = div.get_text(strip=True)
            logger.debug(f"[WORLDWEATHER] Candidate {idx} ({period_name}): {text[:100]}")

            # Extract temperature
            temp = None
            for char_idx, char in enumerate(text):
                if char.isdigit() or (char == '-' and char_idx == 0):
                    num_str = ""
                    for c in text[char_idx:]:
                        if c.isdigit() or c == '-':
                            num_str += c
                        else:
                            break
                    if num_str:
                        try:
                            temp = float(num_str)
                            logger.debug(f"[WORLDWEATHER] {period_name}: extracted temp={temp}")
                            break
                        except ValueError:
                            pass

            # Extract condition
            condition = "облачно"
            text_lower = text.lower()
            for cond in ["дождь", "ясно", "облачно", "снег", "гроза", "туман"]:
                if cond in text_lower:
                    condition = cond
                    break

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_data[period_name] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }
                logger.info(f"[WORLDWEATHER] {period_name}: {temp}°C, {condition}")

        return weather_data if weather_data else None

    except Exception as e:
        logger.error(f"[WORLDWEATHER] ❌ Parse error: {type(e).__name__}: {str(e)[:100]}")
        return None


# ============ GEORGIAN WEATHER (FALLBACK 3) ============

async def _fetch_georgian_weather_html() -> Optional[str]:
    """Fetch weather from xn--lodgobmh.com (Georgian weather service)."""
    try:
        logger.info("[GEORGIAN] Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            url = "https://weather.xn--lodgobmh.com/Tbilisi"
            logger.info(f"[GEORGIAN] Loading {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            logger.info(f"[GEORGIAN] ✓ HTML fetched: {len(html)} bytes")

            await context.close()
            await browser.close()
            return html

    except PlaywrightTimeoutError:
        logger.error("[GEORGIAN] ❌ Timeout")
        return None
    except Exception as e:
        logger.error(f"[GEORGIAN] ❌ Fetch error: {type(e).__name__}: {str(e)[:100]}")
        return None


def _parse_georgian_weather(html: str) -> Optional[Dict[str, Dict]]:
    """Parse Georgian weather HTML table."""
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        logger.info("[GEORGIAN] Parsing HTML...")

        weather_data = {}
        periods = ["night", "morning", "day", "evening"]

        # Find the main weather table
        table = soup.find("table", {"class": "table"})
        if not table:
            logger.error("[GEORGIAN] ❌ No weather table found")
            return None

        rows = table.find_all("tr")
        logger.debug(f"[GEORGIAN] Found {len(rows)} rows in table")

        # Table structure:
        # Row 0: Header
        # Row 1-4: Today (Night has rowspan=4, Morning/Day/Evening follow)
        # Row 5+: Other days

        # Get first day's rows (rows 1-4: Night/Morning/Day/Evening)
        data_rows = rows[1:5]

        if len(data_rows) < 4:
            logger.error(f"[GEORGIAN] ❌ Not enough rows for all periods (got {len(data_rows)})")
            return None

        for row_idx, row in enumerate(data_rows):
            cells = row.find_all("td")

            # First row has 6 cells (including date), others have 5
            if row_idx == 0 and len(cells) == 6:
                # Night row with date
                period_name = cells[1].get_text(strip=True)
                temp_cell = cells[3]
                img_cell = cells[2]
                start_cell_idx = 0
            elif len(cells) >= 5:
                # Other period rows (Morning, Day, Evening)
                period_name = cells[0].get_text(strip=True)
                temp_cell = cells[2]
                img_cell = cells[1]
                start_cell_idx = -1
            else:
                logger.debug(f"[GEORGIAN] Row {row_idx}: unexpected cell count {len(cells)}")
                continue

            # Normalize period name
            period_key = period_name.lower()
            if period_key not in periods:
                logger.debug(f"[GEORGIAN] Skipping unknown period: {period_name}")
                continue

            logger.debug(f"[GEORGIAN] {period_key}: {len(cells)} cells")

            # Extract temperature (e.g., "14...15°C" → average 14.5)
            temp_text = temp_cell.get_text(strip=True)
            logger.debug(f"[GEORGIAN] {period_key}: temp_text='{temp_text}'")

            temp = None
            try:
                # Parse "14...15°C" format
                if "°C" in temp_text:
                    temp_range = temp_text.split("°C")[0]
                    if "..." in temp_range:
                        min_t, max_t = temp_range.split("...")
                        temp = (float(min_t) + float(max_t)) / 2
                    else:
                        temp = float(temp_range)
                    logger.debug(f"[GEORGIAN] {period_key}: extracted temp={temp}")
            except (ValueError, IndexError) as e:
                logger.debug(f"[GEORGIAN] {period_key}: failed to parse temperature: {e}")

            # Extract condition from image filename
            condition = "облачно"
            img = img_cell.find("img")
            if img:
                img_src = img.get("src", "")
                logger.debug(f"[GEORGIAN] {period_key}: img_src='{img_src}'")

                # Map image filenames to Russian conditions
                if "clearsky" in img_src or "fair" in img_src:
                    condition = "ясно"
                elif "heavyrain" in img_src or "rain" in img_src:
                    condition = "дождь"
                elif "cloudy" in img_src or "cloud" in img_src:
                    condition = "облачно"
                elif "fog" in img_src or "mist" in img_src:
                    condition = "туман"
                elif "partlycloudy" in img_src:
                    condition = "переменная облачность"
                else:
                    condition = "облачно"

            emoji = CONDITION_EMOJI.get(condition, "🌤️")

            if temp is not None:
                weather_data[period_key] = {
                    "temperature": round(temp, 1),
                    "condition": condition,
                    "emoji": emoji,
                    "precipitation_mm": 0.0,
                }
                logger.info(f"[GEORGIAN] {period_key}: {temp:.1f}°C, {condition}")

        if weather_data:
            logger.info(f"[GEORGIAN] ✓ Parsed {len(weather_data)} periods")
            return weather_data

        logger.error("[GEORGIAN] ❌ No period data extracted")
        return None

    except Exception as e:
        logger.error(f"[GEORGIAN] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


# ============ MAIN FUNCTION ============

async def get_aggregated_weather() -> Optional[Dict[str, Dict]]:
    """Fetch weather: BBC → Georgian Weather"""
    logger.info("🌤️ Fetching weather (BBC → Georgian Weather)...")

    # Try BBC first (now uses JSON parsing - accurate hourly data)
    logger.info("[BBC] Attempting...")
    bbc_html = await _fetch_bbc_html()
    if bbc_html:
        bbc_weather = _parse_bbc(bbc_html)
        if bbc_weather:
            logger.info("✓ Using BBC Weather")
            return bbc_weather
        else:
            logger.warning("[BBC] Parse failed, trying fallback 1...")
    else:
        logger.warning("[BBC] Fetch failed, trying fallback 1...")

    # Try Georgian Weather (fallback 1 - xn--lodgobmh.com)
    logger.info("[GEORGIAN] Attempting fallback 1...")
    georgian_html = await _fetch_georgian_weather_html()
    if georgian_html:
        georgian_weather = _parse_georgian_weather(georgian_html)
        if georgian_weather:
            logger.info("✓ Using Georgian Weather (fallback 1)")
            return georgian_weather
        else:
            logger.warning("[GEORGIAN] Parse failed, all sources exhausted...")
    else:
        logger.warning("[GEORGIAN] Fetch failed, all sources exhausted...")

    logger.error("❌ All weather sources failed")
    return None


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
