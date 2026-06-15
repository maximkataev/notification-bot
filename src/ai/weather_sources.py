"""Weather from Gismeteo (primary), BBC, and Georgian Weather with smart fallback.

All sources are fetched via Playwright (JavaScript-rendered pages) and return real
data. There are no hardcoded fallbacks — if every source fails, None is returned.
"""

import asyncio
import logging
import time
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

# Supported weather locations. Each digest fetches weather ONCE per location
# (cached + lock-guarded below) so all users in the same city see identical weather.
# Gismeteo is scraping-based and only configured where we have a verified city slug;
# Open-Meteo (lat/lon JSON API) is the reliable universal fallback for any city.
LOCATIONS: Dict[str, Dict[str, Any]] = {
    "tbilisi": {
        "label_prep": "Тбилиси",
        "gismeteo_url": "https://www.gismeteo.ru/weather-tbilisi-5277/",
        "bbc_url": "https://www.bbc.com/weather/611717",
        "georgian": True,  # xn--lodgobmh.com is Tbilisi/Georgia only
        "lat": 41.7151,
        "lon": 44.8271,
    },
    "vienna": {
        "label_prep": "Вене",
        "gismeteo_url": "https://www.gismeteo.ru/weather-vienna-2911/",
        "bbc_url": "https://www.bbc.com/weather/2761369",
        "georgian": False,
        "lat": 48.2082,
        "lon": 16.3738,
    },
}

# WMO weather_code → (Russian condition, emoji) for the Open-Meteo fallback
WMO_CODES: Dict[int, tuple] = {
    0: ("ясно", "☀️"), 1: ("переменная облачность", "🌤️"), 2: ("переменная облачность", "⛅"),
    3: ("облачно", "☁️"), 45: ("туман", "🌫️"), 48: ("туман", "🌫️"),
    51: ("морось", "🌦️"), 53: ("морось", "🌦️"), 55: ("морось", "🌧️"),
    56: ("морось", "🌧️"), 57: ("морось", "🌧️"),
    61: ("дождь", "🌧️"), 63: ("дождь", "🌧️"), 65: ("ливень", "🌧️"),
    66: ("ледяной дождь", "🌧️"), 67: ("ледяной дождь", "🌧️"),
    71: ("снег", "🌨️"), 73: ("снег", "🌨️"), 75: ("снег", "❄️"), 77: ("снег", "❄️"),
    80: ("ливень", "🌦️"), 81: ("ливень", "🌧️"), 82: ("ливень", "⛈️"),
    85: ("снег", "🌨️"), 86: ("снег", "❄️"),
    95: ("гроза", "⛈️"), 96: ("гроза", "⛈️"), 99: ("гроза", "⛈️"),
}

# Per-location weather cache (shared across users in one digest run) + locks
_weather_cache: Dict[str, tuple] = {}  # location -> (timestamp, weather_dict)
_weather_locks: Dict[str, asyncio.Lock] = {}
_WEATHER_TTL_SECONDS = 1800  # 30 minutes

# Map Gismeteo's Russian condition phrases to our internal condition keys
GISMETEO_CONDITION_MAP = [
    ("ясно", "ясно"),
    ("безоблач", "ясно"),
    ("малооблач", "переменная облачность"),
    ("переменная облач", "переменная облачность"),
    ("пасмурно", "облачно"),
    ("облачно", "облачно"),
    ("гроза", "гроза"),
    ("ливень", "ливень"),
    ("дождь", "дождь"),
    ("морос", "морось"),
    ("снег", "снег"),
    ("туман", "туман"),
]


def _map_gismeteo_condition(text: str) -> str:
    """Map a Gismeteo condition tooltip to an internal condition key."""
    t = (text or "").lower()
    for needle, condition in GISMETEO_CONDITION_MAP:
        if needle in t:
            return condition
    return "облачно"


# ============ SHARED PLAYWRIGHT FETCH ============

async def _fetch_rendered_html(
    url: str,
    label: str,
    wait_selector: Optional[str] = None,
    settle_ms: int = 2500,
    nav_timeout_ms: int = 45000,
) -> Optional[str]:
    """Render a JS page with Playwright and return its HTML.

    Hardened against the 15s timeouts we were hitting on slow days even though the
    sites load fine in a browser:
      - blocks images / fonts / media / stylesheets (we never parse them) so the
        navigation completes much faster
      - uses a generous navigation timeout instead of 15s
      - waits for a specific data selector when given, rather than a blind sleep
      - returns whatever HTML did load even if navigation or the selector wait
        times out, so a partially-loaded-but-parseable page still gets a chance
    """
    browser = None
    try:
        logger.info(f"[{label}] Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )

            # Abort heavy resource requests we never read. We still parse <img src>
            # attributes / JSON script tags from the DOM, which remain intact.
            async def _block(route):
                if route.request.resource_type in ("image", "media", "font", "stylesheet"):
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", _block)
            page = await context.new_page()

            logger.info(f"[{label}] Loading {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            except PlaywrightTimeoutError:
                logger.warning(f"[{label}] navigation timeout — parsing whatever loaded")

            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=15000)
                except PlaywrightTimeoutError:
                    logger.warning(f"[{label}] selector '{wait_selector}' not ready — parsing current DOM")

            await page.wait_for_timeout(settle_ms)
            html = await page.content()
            logger.info(f"[{label}] ✓ HTML fetched: {len(html)} bytes")
            return html

    except Exception as e:
        logger.error(f"[{label}] ❌ Fetch error: {type(e).__name__}: {str(e)[:100]}")
        return None
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


# ============ GISMETEO (PRIMARY) ============

async def _fetch_gismeteo_html(url: str) -> Optional[str]:
    """Fetch a Gismeteo city page with Playwright (renders the forecast widget)."""
    return await _fetch_rendered_html(url, "GISMETEO", wait_selector=".widget-row-datetime-time")


def _parse_gismeteo(html: str) -> Optional[Dict[str, Dict]]:
    """Parse Gismeteo's today widget into night/morning/day/evening periods.

    Widget structure:
      - time row (`widget-row-datetime-time`): 8 three-hour slots, e.g. 1:00..22:00
      - air temp row (`widget-row-chart-temperature-air`): <temperature-value value=..>
      - icon row (`widget-row-icon`): row-item[data-tooltip] condition per slot
    """
    if not html:
        return None

    try:
        import re
        soup = BeautifulSoup(html, "html.parser")
        logger.info("[GISMETEO] Parsing widget...")

        # Time slots (hours)
        time_row = soup.find(class_="widget-row-datetime-time")
        if not time_row:
            logger.error("[GISMETEO] ❌ No time row found")
            return None
        time_texts = [el.get_text(strip=True) for el in time_row.find_all(class_="row-item")]
        if not time_texts:
            time_texts = time_row.get_text(" ", strip=True).split()
        hours = []
        for t in time_texts:
            m = re.match(r"(\d{1,2}):", t)
            hours.append(int(m.group(1)) if m else None)

        # Air temperatures
        air_row = soup.find(class_=re.compile("widget-row-chart-temperature-air"))
        if not air_row:
            logger.error("[GISMETEO] ❌ No air temperature row found")
            return None
        temps = []
        for tv in air_row.find_all("temperature-value"):
            val = tv.get("value")
            if val is None:
                continue
            try:
                temps.append(float(val))
            except ValueError:
                continue

        # Conditions (tooltips on icon row)
        icon_row = soup.find(class_=re.compile(r"\bwidget-row-icon\b"))
        conditions = []
        if icon_row:
            conditions = [
                el.get("data-tooltip", "")
                for el in icon_row.find_all(attrs={"data-tooltip": True})
            ]

        n = min(len(hours), len(temps))
        if n == 0:
            logger.error(f"[GISMETEO] ❌ No aligned data (hours={len(hours)}, temps={len(temps)})")
            return None

        periods = {"night": (0, 6), "morning": (6, 12), "day": (12, 18), "evening": (18, 24)}
        bucket_temps = {p: [] for p in periods}
        bucket_conds = {p: [] for p in periods}

        for i in range(n):
            hour = hours[i]
            if hour is None:
                continue
            for period_name, (start, end) in periods.items():
                if start <= hour < end:
                    bucket_temps[period_name].append(temps[i])
                    if i < len(conditions) and conditions[i]:
                        bucket_conds[period_name].append(conditions[i])
                    break

        weather_by_period = {}
        for period_name in periods:
            t_list = bucket_temps[period_name]
            if not t_list:
                continue
            avg_temp = round(sum(t_list) / len(t_list), 1)
            cond_text = bucket_conds[period_name][0] if bucket_conds[period_name] else "облачно"
            condition = _map_gismeteo_condition(cond_text)
            weather_by_period[period_name] = {
                "temperature": avg_temp,
                "condition": condition,
                "emoji": CONDITION_EMOJI.get(condition, "🌤️"),
                "precipitation_mm": 0.0,
            }
            logger.info(f"[GISMETEO] {period_name}: {avg_temp}°C, {condition}")

        if weather_by_period:
            logger.info(f"[GISMETEO] ✓ Parsed {len(weather_by_period)} periods")
            return weather_by_period

        logger.error("[GISMETEO] ❌ No period data extracted")
        return None

    except Exception as e:
        logger.error(f"[GISMETEO] ❌ Parse error: {type(e).__name__}: {str(e)[:200]}")
        return None


# ============ BBC WEATHER ============

async def _fetch_bbc_html(url: str) -> Optional[str]:
    """Fetch a BBC Weather city page with Playwright."""
    return await _fetch_rendered_html(url, "BBC", wait_selector="script[type='application/json']")


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
    url = "https://weather.xn--lodgobmh.com/Tbilisi"
    return await _fetch_rendered_html(url, "GEORGIAN", wait_selector="table.table", settle_ms=2000)


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

# ============ OPEN-METEO (universal reliable fallback) ============

async def _fetch_openmeteo(lat: float, lon: float) -> Optional[Dict[str, Dict]]:
    """Fetch weather from Open-Meteo (JSON API, no scraping) → period dict.

    Works for any city by lat/lon and is far more reliable than scraping, so it
    serves as the universal last-resort fallback (and the only source for cities
    without a verified Gismeteo/BBC scraper, e.g. precise non-Tbilisi locations).
    """
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,weather_code&forecast_days=1&timezone=auto"
        )
        logger.info(f"[OPEN-METEO] Fetching {lat},{lon}")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        codes = hourly.get("weather_code", [])
        if not times or not temps:
            logger.error("[OPEN-METEO] ❌ No hourly data")
            return None

        periods = {"night": (0, 6), "morning": (6, 12), "day": (12, 18), "evening": (18, 24)}
        buckets = {p: {"temps": [], "codes": []} for p in periods}

        for i, t in enumerate(times):
            try:
                hour = int(t[11:13])  # ISO "YYYY-MM-DDTHH:MM"
            except (ValueError, IndexError):
                continue
            for name, (start, end) in periods.items():
                if start <= hour < end:
                    if i < len(temps) and temps[i] is not None:
                        buckets[name]["temps"].append(temps[i])
                    if i < len(codes) and codes[i] is not None:
                        buckets[name]["codes"].append(codes[i])
                    break

        result: Dict[str, Dict] = {}
        for name in periods:
            tl = buckets[name]["temps"]
            if not tl:
                continue
            avg_temp = round(sum(tl) / len(tl), 1)
            cl = buckets[name]["codes"]
            # Use the WORST (max) code in the period so rain/storms aren't hidden by
            # an averaged "clear" — matters for the rain alert / clothing advice.
            code = max(cl) if cl else 0
            condition, emoji = WMO_CODES.get(code, ("облачно", "🌤️"))
            result[name] = {
                "temperature": avg_temp,
                "condition": condition,
                "emoji": emoji,
                "precipitation_mm": 0.0,
            }
            logger.info(f"[OPEN-METEO] {name}: {avg_temp}°C, {condition}")

        if result:
            logger.info(f"[OPEN-METEO] ✓ Parsed {len(result)} periods")
            return result

        logger.error("[OPEN-METEO] ❌ No period data extracted")
        return None

    except Exception as e:
        logger.error(f"[OPEN-METEO] ❌ {type(e).__name__}: {str(e)[:100]}")
        return None


# ============ MAIN FUNCTION ============

async def _fetch_aggregated_weather(location: str) -> Optional[Dict[str, Dict]]:
    """Fetch weather for a location via its configured source chain (uncached)."""
    cfg = LOCATIONS[location]
    label = cfg.get("label_prep", location)
    logger.info(f"🌤️ Fetching weather for {label} (Gismeteo → BBC → Georgian → Open-Meteo)...")

    # Gismeteo (primary, where a verified city slug exists)
    if cfg.get("gismeteo_url"):
        logger.info("[GISMETEO] Attempting (primary)...")
        gismeteo_html = await _fetch_gismeteo_html(cfg["gismeteo_url"])
        if gismeteo_html:
            gismeteo_weather = _parse_gismeteo(gismeteo_html)
            if gismeteo_weather:
                logger.info(f"✓ Using Gismeteo for {label}")
                return gismeteo_weather
        logger.warning(f"[GISMETEO] failed for {label}, trying BBC...")

    # BBC (JSON parsing - accurate hourly data)
    if cfg.get("bbc_url"):
        logger.info("[BBC] Attempting...")
        bbc_html = await _fetch_bbc_html(cfg["bbc_url"])
        if bbc_html:
            bbc_weather = _parse_bbc(bbc_html)
            if bbc_weather:
                logger.info(f"✓ Using BBC Weather for {label}")
                return bbc_weather
        logger.warning(f"[BBC] failed for {label}, trying next fallback...")

    # Georgian Weather (Tbilisi only)
    if cfg.get("georgian"):
        logger.info("[GEORGIAN] Attempting fallback...")
        georgian_html = await _fetch_georgian_weather_html()
        if georgian_html:
            georgian_weather = _parse_georgian_weather(georgian_html)
            if georgian_weather:
                logger.info(f"✓ Using Georgian Weather for {label}")
                return georgian_weather
        logger.warning(f"[GEORGIAN] failed for {label}, trying Open-Meteo...")

    # Open-Meteo (universal reliable fallback)
    if cfg.get("lat") is not None and cfg.get("lon") is not None:
        logger.info("[OPEN-METEO] Attempting fallback...")
        om_weather = await _fetch_openmeteo(cfg["lat"], cfg["lon"])
        if om_weather:
            logger.info(f"✓ Using Open-Meteo for {label}")
            return om_weather

    logger.error(f"❌ All weather sources failed for {label}")
    return None


async def get_aggregated_weather(location: str = "tbilisi") -> Optional[Dict[str, Dict]]:
    """Fetch weather for a location, fetched at most once per TTL and shared.

    The result is cached per location (lock-guarded) so that every user in the same
    city during a single morning run sees IDENTICAL weather, instead of each user
    independently re-fetching and possibly landing on a different source.
    """
    location = (location or "tbilisi").lower()
    if location not in LOCATIONS:
        logger.warning(f"Unknown weather location '{location}', falling back to tbilisi")
        location = "tbilisi"

    # Fast path: fresh cached value
    cached = _weather_cache.get(location)
    if cached and cached[1] and (time.time() - cached[0]) < _WEATHER_TTL_SECONDS:
        logger.info(f"✓ Using cached weather for {location} (age {int(time.time() - cached[0])}s)")
        return cached[1]

    # Slow path: only one coroutine fetches; others wait and reuse the cache
    lock = _weather_locks.setdefault(location, asyncio.Lock())
    async with lock:
        cached = _weather_cache.get(location)
        if cached and cached[1] and (time.time() - cached[0]) < _WEATHER_TTL_SECONDS:
            logger.info(f"✓ Using cached weather for {location} (age {int(time.time() - cached[0])}s)")
            return cached[1]

        result = await _fetch_aggregated_weather(location)
        if result:  # don't cache failures — let the next user retry
            _weather_cache[location] = (time.time(), result)
        return result


async def generate_clothing_recommendation(weather: Optional[Dict[str, Dict]], is_raining: bool = False, city: str = "Тбилиси") -> Optional[str]:
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
                {"role": "user", "content": f"Во что одеться в {city}? Температура {avg_temp:.1f}°C, {'с осадками' if has_precip else 'без осадков'}. Ответ: 2-3 вещи, без объяснений."},
            ],
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"Clothing recommendation failed: {e}")
        return None
