"""Check for upcoming precipitation in Tbilisi via Open-Meteo hourly forecast.

Previous implementation reused the digest weather source (Gismeteo/BBC), which only
has 6-hour period granularity (night/morning/day/evening) — "rain sometime today"
became a false "rain in the next hour" alert. Open-Meteo gives a real HOURLY
precipitation forecast (mm + probability + weather code), free and keyless, so the
alert now fires only when a specific upcoming hour actually has rain in it.
"""

import logging
import math
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import httpx

try:
    from zoneinfo import ZoneInfo
    TBILISI_TZ = ZoneInfo("Asia/Tbilisi")
except Exception:  # pragma: no cover - fallback if tzdata unavailable
    TBILISI_TZ = None

from src.ai.weather_sources import LOCATIONS

logger = logging.getLogger(__name__)

# Alert thresholds: skip drizzle-level noise and low-confidence forecasts.
# The mm amount is the model's deterministic forecast and does the main filtering;
# the probability cut only drops long-shot ensemble outliers (live data shows real
# rain forecasts routinely carry ~30-40% stated probability).
MIN_PRECIP_MM_PER_HOUR = 0.2
MIN_PRECIP_PROBABILITY = 30  # %

# WMO weather codes → human-readable condition + emoji
# https://open-meteo.com/en/docs (WMO Weather interpretation codes)
_WMO_CONDITIONS = [
    (range(51, 58), ("морось", "🌦️")),
    (range(61, 66), ("дождь", "🌧️")),
    (range(66, 68), ("ледяной дождь", "🌧️")),
    (range(71, 78), ("снег", "❄️")),
    (range(80, 83), ("ливень", "🌧️")),
    (range(85, 87), ("снегопад", "❄️")),
    (range(95, 100), ("гроза", "⛈️")),
]


def _condition_from_wmo(code: Optional[int]) -> tuple:
    """Map a WMO weather code to (condition, emoji); generic rain if unknown."""
    if code is not None:
        for code_range, result in _WMO_CONDITIONS:
            if code in code_range:
                return result
    return ("осадки", "🌧️")


def _tbilisi_now() -> datetime:
    """Current time in Tbilisi (naive), independent of server timezone (UTC)."""
    if TBILISI_TZ is not None:
        return datetime.now(TBILISI_TZ).replace(tzinfo=None)
    # Fallback: Tbilisi is UTC+4 year-round
    return datetime.utcnow() + timedelta(hours=4)


async def get_upcoming_precipitation(hours: int = 3) -> Optional[Dict[str, Any]]:
    """Check Open-Meteo hourly forecast for precipitation in the next N hours.

    Returns dict with precipitation details if found, None otherwise:
    {
        "time": "15:00",        # onset hour (Tbilisi)
        "hours_from_now": 2,
        "condition": "дождь",
        "emoji": "🌧️",
        "probability": 70,      # % (None if API omitted it)
        "intensity_mm": 1.2,    # forecast mm for that hour
    }
    """
    try:
        cfg = LOCATIONS["tbilisi"]
        params = {
            "latitude": cfg["lat"],
            "longitude": cfg["lon"],
            "hourly": "precipitation,precipitation_probability,weather_code",
            "timezone": "Asia/Tbilisi",
            # current hour + lookahead window (a couple extra hours costs nothing)
            "forecast_hours": hours + 3,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            data = response.json()

        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        precip = hourly.get("precipitation") or []
        probs = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []

        if not times or not precip:
            logger.warning("[PRECIP] Open-Meteo returned no hourly data")
            return None

        now = _tbilisi_now()
        window_end = now + timedelta(hours=hours)

        for i, time_iso in enumerate(times):
            try:
                slot = datetime.fromisoformat(time_iso)
            except ValueError:
                continue

            # Keep slots overlapping [now, now + hours): the current (already started)
            # hour still counts — rain at :40 of this hour is an upcoming event.
            if slot + timedelta(hours=1) <= now or slot >= window_end:
                continue

            amount = precip[i] if i < len(precip) and precip[i] is not None else 0.0
            probability = probs[i] if i < len(probs) else None
            code = codes[i] if i < len(codes) else None

            if amount < MIN_PRECIP_MM_PER_HOUR:
                continue
            if probability is not None and probability < MIN_PRECIP_PROBABILITY:
                logger.info(
                    f"[PRECIP] {time_iso}: {amount} mm but probability {probability}% "
                    f"< {MIN_PRECIP_PROBABILITY}% — skipping"
                )
                continue

            condition, emoji = _condition_from_wmo(code)
            hours_from_now = max(0, math.ceil((slot - now).total_seconds() / 3600))

            result = {
                "time": slot.strftime("%H:%M"),
                "hours_from_now": hours_from_now,
                "condition": condition,
                "emoji": emoji,
                "probability": probability,
                "intensity_mm": round(float(amount), 1),
            }
            logger.info(
                f"[PRECIP] ✓ {condition} around {result['time']} "
                f"({amount} mm, prob={probability}%)"
            )
            return result

        logger.info(f"[PRECIP] No precipitation ≥{MIN_PRECIP_MM_PER_HOUR} mm in next {hours}h")
        return None

    except Exception as e:
        logger.warning(f"Precipitation check failed: {type(e).__name__}: {e}")
        return None
