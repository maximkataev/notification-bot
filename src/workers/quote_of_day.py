"""Get wisdom/quote of the day to inspire the user.

RULE: NO HARDCODED FALLBACKS
If all API sources fail, return None (no quote section in digest).
Better to skip the block than show fake data.
"""
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


async def _try_quotable_io() -> Optional[Dict[str, Any]]:
    """Try quotable.io API with 10s timeout."""
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            url = "https://api.quotable.io/random?tags=inspirational|wisdom|success"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return {
                "text": data.get("content", ""),
                "author": data.get("author", "Unknown"),
            }
    except Exception as e:
        logger.debug(f"quotable.io failed ({type(e).__name__}): {str(e)[:100]}")
        return None


async def _try_zenquotes() -> Optional[Dict[str, Any]]:
    """Try zenquotes.io API with 10s timeout."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = "https://api.zenquotes.io/random"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if data and len(data) > 0:
                quote = data[0]
                return {
                    "text": quote.get("q", ""),
                    "author": quote.get("a", "Unknown").replace(" ", ""),
                }
    except Exception as e:
        logger.debug(f"zenquotes.io failed ({type(e).__name__}): {str(e)[:100]}")
        return None


async def _try_advice_slip() -> Optional[Dict[str, Any]]:
    """Try advice-slip.com API with 10s timeout."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = "https://api.adviceslip.com/advice"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if data and data.get("slip"):
                slip = data["slip"]
                text = slip.get("advice", "")
                if text:
                    return {
                        "text": text,
                        "author": "Advice Slip",
                    }
    except Exception as e:
        logger.debug(f"advice-slip.com failed ({type(e).__name__}): {str(e)[:100]}")
        return None


async def _try_forismatic() -> Optional[Dict[str, Any]]:
    """Try forismatic.com API with 10s timeout."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = "https://api.forismatic.com/api/1.0/?method=getQuote&format=json&lang=en"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if data:
                return {
                    "text": data.get("quoteText", ""),
                    "author": data.get("quoteAuthor", "Unknown") or "Unknown",
                }
    except Exception as e:
        logger.debug(f"forismatic.com failed ({type(e).__name__}): {str(e)[:100]}")
        return None


async def get_quote_of_day() -> Optional[Dict[str, Any]]:
    """
    Fetch a random inspirational quote from real API sources.

    Tries multiple APIs in order (prioritized by reliability):
    1. zenquotes.io (most reliable, no auth needed)
    2. quotable.io (very reliable, filters inspirational)
    3. forismatic.com (general quotes)
    4. advice-slip.com (practical advice)

    Returns:
        Dict with "text" and "author", or None if all sources fail.
        NO HARDCODED FALLBACK: better to skip the block than show fake data.
    """
    # Try API sources in order of reliability
    sources = [
        ("zenquotes.io", _try_zenquotes),
        ("quotable.io", _try_quotable_io),
        ("forismatic.com", _try_forismatic),
        ("advice-slip.com", _try_advice_slip),
    ]

    for source_name, source_func in sources:
        try:
            logger.debug(f"Trying quote source: {source_name}")
            quote = await source_func()
            if quote and quote.get("text") and len(quote["text"]) > 10:
                logger.info(f"✓ Quote fetched from {source_name}: {quote['text'][:50]}...")
                return quote
        except Exception as e:
            logger.debug(f"Failed to fetch from {source_name}: {type(e).__name__}")
            continue

    # All API sources exhausted - return None (no quote block in digest)
    logger.warning("All quote APIs unavailable, skipping quote block (no hardcoded fallback)")
    return None
