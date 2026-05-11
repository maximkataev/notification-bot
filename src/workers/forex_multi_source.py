"""Fetch EUR/USD from multiple sources for reliability."""
import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

# EUR/USD threshold for alerts
EUR_USD_THRESHOLD = 1.18


async def _fetch_from_exchangerate_api() -> Optional[float]:
    """Fetch EUR/USD from exchangerate-api.com (free tier available)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://v6.exchangerate-api.com/v6/latest/EUR",
                params={"apikey": "free"}  # Free tier doesn't need key for some endpoints
            )
            response.raise_for_status()
            data = response.json()

            # Success response structure
            if data.get("result") == "success":
                rates = data.get("conversion_rates", {})
                usd_rate = rates.get("USD")
                if usd_rate:
                    logger.debug(f"✓ exchangerate-api.com: EUR/USD = {usd_rate}")
                    return usd_rate
            else:
                logger.debug(f"API returned non-success: {data.get('result')}")
                return None

    except Exception as e:
        logger.debug(f"exchangerate-api.com failed: {type(e).__name__}")
        return None


async def _fetch_from_exchangerate_host() -> Optional[float]:
    """Fetch EUR/USD from exchangerate.host (open-source, always free)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.exchangerate.host/latest",
                params={"base": "EUR", "symbols": "USD"}
            )
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                rates = data.get("rates", {})
                usd_rate = rates.get("USD")
                if usd_rate:
                    logger.debug(f"✓ exchangerate.host: EUR/USD = {usd_rate}")
                    return usd_rate

    except Exception as e:
        logger.debug(f"exchangerate.host failed: {type(e).__name__}")
        return None


async def get_eur_usd_multi_source() -> Optional[Dict[str, Any]]:
    """
    Fetch EUR/USD from multiple sources.

    Returns:
        {
            "eur_usd_source1": float,           # exchangerate-api.com
            "eur_usd_source2": float,           # exchangerate.host
            "eur_usd_avg": float,               # Average of available sources
            "timestamp": ISO datetime string,
            "sources_available": int,           # How many sources succeeded
        }
        or None if all sources fail
    """
    try:
        logger.info("Fetching EUR/USD from multiple sources...")

        # Fetch from both sources in parallel
        source1, source2 = await asyncio.gather(
            _fetch_from_exchangerate_api(),
            _fetch_from_exchangerate_host(),
            return_exceptions=False
        )

        if source1 is None and source2 is None:
            logger.warning("All EUR/USD sources failed")
            return None

        # Calculate average from available sources
        available_rates = [r for r in [source1, source2] if r is not None]
        avg_rate = sum(available_rates) / len(available_rates) if available_rates else None

        result = {
            "eur_usd_source1": source1,  # exchangerate-api.com
            "eur_usd_source2": source2,  # exchangerate.host
            "eur_usd_avg": avg_rate,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sources_available": len(available_rates),
        }

        logger.info(
            f"✓ EUR/USD fetched: "
            f"source1={source1}, source2={source2}, avg={avg_rate:.5f}"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to fetch EUR/USD: {type(e).__name__}: {e}")
        return None


async def check_eur_usd_threshold(threshold: float = EUR_USD_THRESHOLD) -> Optional[Dict[str, Any]]:
    """
    Check if EUR/USD exceeds threshold.

    Returns:
        {
            "exceeded": bool,
            "eur_usd_avg": float,
            "sources": [source1, source2],
            "sources_exceeded": [list of sources that exceeded],
            "timestamp": datetime string,
        }
        or None if fetch failed
    """
    try:
        data = await get_eur_usd_multi_source()
        if not data:
            return None

        source1 = data.get("eur_usd_source1")
        source2 = data.get("eur_usd_source2")
        avg = data.get("eur_usd_avg")

        # Check which sources exceeded threshold
        sources_exceeded = []
        if source1 and source1 > threshold:
            sources_exceeded.append("exchangerate-api.com")
        if source2 and source2 > threshold:
            sources_exceeded.append("exchangerate.host")

        exceeded = len(sources_exceeded) > 0

        result = {
            "exceeded": exceeded,
            "eur_usd_avg": avg,
            "sources": [source1, source2],
            "sources_exceeded": sources_exceeded,
            "timestamp": data.get("timestamp"),
            "threshold": threshold,
        }

        if exceeded:
            logger.warning(
                f"⚠️  EUR/USD exceeded {threshold}: "
                f"avg={avg:.5f}, sources_exceeded={sources_exceeded}"
            )

        return result

    except Exception as e:
        logger.error(f"Failed to check threshold: {type(e).__name__}: {e}")
        return None


# Required import
import asyncio
