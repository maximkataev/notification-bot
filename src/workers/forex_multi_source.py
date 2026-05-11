"""Fetch EUR/USD from multiple sources for reliability."""

import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

# EUR/USD threshold for alerts
EUR_USD_THRESHOLD = 1.18


async def _fetch_from_exchangerate_api_v4() -> Optional[float]:
    """Fetch EUR/USD from exchangerate-api.com v4 (free, no auth)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
            )
            response.raise_for_status()
            data = response.json()

            rates = data.get("rates", {})
            eur_rate = rates.get("EUR")
            if eur_rate and eur_rate > 0:
                # Convert USD→EUR to EUR→USD
                eur_usd = 1.0 / eur_rate
                logger.debug(f"✓ exchangerate-api.com v4: EUR/USD = {eur_usd}")
                return eur_usd
            else:
                logger.debug(f"API returned invalid EUR rate: {eur_rate}")
                return None

    except httpx.TimeoutException:
        logger.debug(f"exchangerate-api.com v4: timeout (10s)")
        return None
    except Exception as e:
        logger.debug(f"exchangerate-api.com v4 failed: {type(e).__name__}: {str(e)[:100]}")
        return None


async def _fetch_from_ecb_api() -> Optional[float]:
    """Fetch EUR/USD from ECB (European Central Bank - official daily rates)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
            )
            response.raise_for_status()

            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)

            # ECB uses namespace in XML
            namespace = {
                'default': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'
            }

            for cube in root.iter('{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube'):
                currency = cube.get('currency')
                rate = cube.get('rate')
                if currency == 'USD' and rate:
                    try:
                        # ECB gives "1 USD = X EUR" directly (same as exchangerate-api)
                        usd_eur = float(rate)
                        logger.debug(f"✓ ECB API: USD/EUR = {usd_eur:.5f}")
                        return usd_eur
                    except ValueError:
                        pass

            logger.debug(f"ECB API: USD rate not found in response")
            return None

    except httpx.TimeoutException:
        logger.debug(f"ECB API: timeout (10s)")
        return None
    except Exception as e:
        logger.debug(f"ECB API failed: {type(e).__name__}: {str(e)[:100]}")
        return None


async def get_eur_usd_multi_source() -> Optional[Dict[str, Any]]:
    """
    Fetch EUR/USD from multiple sources for redundancy.

    Returns:
        {
            "eur_usd_source1": float,           # exchangerate-api.com v4
            "eur_usd_source2": float,           # ECB API (European Central Bank)
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
            _fetch_from_exchangerate_api_v4(),
            _fetch_from_ecb_api(),
            return_exceptions=False,
        )

        logger.debug(f"Fetch results: source1={source1}, source2={source2}")

        if source1 is None and source2 is None:
            logger.warning("⚠️  All EUR/USD sources failed (source1=None, source2=None)")
            return None

        # Calculate average from available sources
        available_rates = [r for r in [source1, source2] if r is not None]
        avg_rate = (
            sum(available_rates) / len(available_rates) if available_rates else None
        )

        result = {
            "eur_usd_source1": source1,  # exchangerate-api.com v4
            "eur_usd_source2": source2,  # CBR API
            "eur_usd_avg": avg_rate,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sources_available": len(available_rates),
        }

        if avg_rate:
            logger.info(
                f"✓ EUR/USD fetched from exchangerate-api + ECB: "
                f"api={source1:.5f}, ecb={source2:.5f}, avg={avg_rate:.5f}"
            )

        return result

    except Exception as e:
        logger.error(f"Failed to fetch EUR/USD: {type(e).__name__}: {e}")
        return None


async def check_eur_usd_threshold(
    threshold: float = EUR_USD_THRESHOLD,
) -> Optional[Dict[str, Any]]:
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
            sources_exceeded.append("ECB API")

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
