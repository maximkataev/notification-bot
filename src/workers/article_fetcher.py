"""Fetch the readable body text of a news article by URL.

RSS feeds only carry a lede paragraph, which is never enough to explain HOW a thing
works — the digest summaries end up restating the headline. This module pulls the
actual article page so the summarizer has real facts (mechanism, numbers, quotes) to
squeeze from.

Best-effort by design: paywalls, JS-only pages and 403s simply yield None and the
caller falls back to the RSS description. Nothing here is allowed to break a digest.
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Enough text for a summarizer to work with; anything shorter is almost certainly a
# paywall stub, a cookie wall or a JS shell rather than the article itself.
MIN_ARTICLE_CHARS = 400

# Cap what we hand to the model — the first few thousand characters of a news story
# hold the facts; the tail is related-links and boilerplate.
MAX_ARTICLE_CHARS = 6000

# Paragraphs shorter than this are navigation, bylines, captions and share prompts.
_MIN_PARAGRAPH_CHARS = 40

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Junk containers that would otherwise contribute <p> tags to the body text.
_STRIP_TAGS = [
    "script", "style", "noscript", "nav", "aside", "header", "footer",
    "form", "figure", "iframe", "svg",
]


def _extract_body_text(html: str) -> Optional[str]:
    """Pull the article body out of a rendered HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    container = (
        soup.find("article")
        or soup.find(attrs={"itemprop": "articleBody"})
        or soup.find("main")
        or soup.body
    )
    if container is None:
        return None

    paragraphs = [
        p.get_text(" ", strip=True) for p in container.find_all("p")
    ]
    text = " ".join(p for p in paragraphs if len(p) >= _MIN_PARAGRAPH_CHARS)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < MIN_ARTICLE_CHARS:
        return None
    return text[:MAX_ARTICLE_CHARS]


async def fetch_article_text(url: str, *, timeout: float = 10.0) -> Optional[str]:
    """Return the article body text at `url`, or None if it cannot be read."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=_HEADERS
        ) as client:
            response = await client.get(url)

        if response.status_code != 200:
            logger.debug(f"Article fetch {response.status_code}: {url}")
            return None
        if "html" not in response.headers.get("content-type", "").lower():
            return None

        return _extract_body_text(response.text)

    except Exception as e:
        logger.debug(f"Article fetch failed ({type(e).__name__}): {url}")
        return None


async def fetch_article_texts(
    urls: List[str], *, timeout: float = 10.0
) -> Dict[str, str]:
    """Fetch several articles concurrently.

    Returns:
        {url: body_text} containing only the URLs that yielded usable text.
    """
    unique = [u for u in dict.fromkeys(urls) if u]
    if not unique:
        return {}

    results = await asyncio.gather(
        *(fetch_article_text(u, timeout=timeout) for u in unique),
        return_exceptions=True,
    )

    texts = {
        url: text
        for url, text in zip(unique, results)
        if isinstance(text, str) and text
    }
    logger.info(f"Article bodies fetched: {len(texts)}/{len(unique)}")
    return texts
