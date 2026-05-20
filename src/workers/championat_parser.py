"""Parse match reports from championat.com for yesterdays matches."""

import logging
import httpx
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Team to championat.com URL mapping
TEAM_CHAMPIONAT_URLS = {
    "Манчестер": "https://www.championat.com/tags/602-manchester-siti/",
    "Арсенал": "https://www.championat.com/tags/548-arsenal/",
    "Барселона": "https://www.championat.com/tags/552-fk-barselona/",
    "Реал Мадрид": "https://www.championat.com/tags/551-fk-real-madrid/",
    "ПСЖ": "https://www.championat.com/tags/684-pszh/",
    "Атлетико": "https://www.championat.com/tags/597-atletiko-madrid/",
}

WORLD_CUP_URL = "https://www.championat.com/football/_worldcup.html"


async def _fetch_url_with_retry(url: str, max_retries: int = 3, timeout: float = 10.0) -> Optional[str]:
    """Fetch URL content with retries and redirects."""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            logger.warning(f"Timeout fetching {url}")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            logger.debug(f"Failed to fetch {url}: {type(e).__name__}")
            return None
    return None


