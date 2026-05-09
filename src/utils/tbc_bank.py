"""Exchange rate fetching from multiple open APIs."""
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def get_eur_usd_rate() -> Optional[float]:
    """
    Fetch EUR to USD exchange rate from multiple open APIs.
    Tries APIs in order, returns rate from first successful response.
    """
    apis = [
        ("exchangerate-api.com", _fetch_from_exchangerate_api),
        ("fixer.io", _fetch_from_fixer),
        ("open-exchange-rates", _fetch_from_open_exchange),
    ]

    for api_name, fetch_fn in apis:
        try:
            rate = await fetch_fn()
            if rate:
                logger.info(f"EUR/USD rate from {api_name}: {rate:.4f}")
                return rate
        except Exception as e:
            logger.warning(f"{api_name} failed: {e}")
            continue

    logger.error("All exchange rate APIs failed")
    return None


async def _fetch_from_exchangerate_api() -> Optional[float]:
    """Fetch from exchangerate-api.com (free tier, no key required)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get("https://api.exchangerate-api.com/v4/latest/EUR")
        response.raise_for_status()
        return response.json()["rates"]["USD"]


async def _fetch_from_fixer() -> Optional[float]:
    """Fetch from fixer.io (free tier available)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get("https://api.fixer.io/latest?base=EUR&symbols=USD")
        response.raise_for_status()
        return response.json()["rates"]["USD"]


async def _fetch_from_open_exchange() -> Optional[float]:
    """Fetch from open-exchange-rates.com (free tier available)."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            "https://openexchangerates.org/api/latest.json?base=EUR&symbols=USD"
        )
        response.raise_for_status()
        return response.json()["rates"]["USD"]
