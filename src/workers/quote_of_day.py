"""Get wisdom/quote of the day to inspire the user."""
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


async def get_quote_of_day() -> Optional[Dict[str, Any]]:
    """
    Fetch a random inspirational quote from quotable.io API.

    Returns None if API fails (no fallback).

    Returns:
        {
            "text": str,      # The quote
            "author": str,    # Who said it
        }
    """
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            # Use quotable.io free API (verify=False due to expired cert)
            url = "https://api.quotable.io/random?tags=inspirational|wisdom|success"
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            quote = {
                "text": data.get("content", ""),
                "author": data.get("author", "Unknown"),
            }

            logger.info(f"✓ Quote fetched: {quote['text'][:50]}...")
            return quote

    except Exception as e:
        logger.error(f"❌ Failed to fetch quote: {type(e).__name__}: {e}")
        return None
