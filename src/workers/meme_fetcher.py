"""Fetch fresh memes and explanations from internet sources.

Sources (with fallbacks):
- Reddit (primary: r/memes, r/funny, r/CoolGuidesDaily, r/InternetIsBeautiful)
- Reddit (secondary: r/ProgrammerHumor for tech humor, r/Jokes for jokes)

Fetches content from last 24 hours. Fallback sources used if primary yields insufficient results.
"""

import logging
import httpx
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import feedparser
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Meme sources (primary: Reddit RSS)
MEME_SOURCES = [
    {
        "title": "Reddit r/memes",
        "url": "https://www.reddit.com/r/memes/.rss",
        "type": "rss",
        "language": "en",
        "priority": 1,
    },
    {
        "title": "Reddit r/funny",
        "url": "https://www.reddit.com/r/funny/.rss",
        "type": "rss",
        "language": "en",
        "priority": 1,
    },
    {
        "title": "Reddit r/InternetIsBeautiful",
        "url": "https://www.reddit.com/r/InternetIsBeautiful/.rss",
        "type": "rss",
        "language": "en",
        "priority": 1,
    },
    {
        "title": "Reddit r/CoolGuidesDaily",
        "url": "https://www.reddit.com/r/CoolGuidesDaily/.rss",
        "type": "rss",
        "language": "en",
        "priority": 1,
    },
    # Fallback sources (additional Reddit communities)
    {
        "title": "Reddit r/ProgrammerHumor",
        "url": "https://www.reddit.com/r/ProgrammerHumor/.rss",
        "type": "rss",
        "language": "en",
        "priority": 2,
    },
    {
        "title": "Reddit r/Jokes",
        "url": "https://www.reddit.com/r/Jokes/.rss",
        "type": "rss",
        "language": "en",
        "priority": 2,
    },
]

MEME_SOURCES_RU = [
    {
        "title": "Reddit r/Pikabu",
        "url": "https://www.reddit.com/r/Pikabu/.rss",
        "type": "rss",
        "language": "ru",
        "priority": 1,
    },
    {
        "title": "Reddit r/Russian",
        "url": "https://www.reddit.com/r/Russian/.rss",
        "type": "rss",
        "language": "ru",
        "priority": 1,
    },
    # Fallback for Russian (additional Reddit communities)
    {
        "title": "Reddit r/Anekdoty",
        "url": "https://www.reddit.com/r/Anekdoty/.rss",
        "type": "rss",
        "language": "ru",
        "priority": 2,
    },
]


async def _fetch_from_rss(url: str, source_title: str, timeout: float = 10.0, max_retries: int = 3) -> List[Dict[str, Any]]:
    """Fetch items from RSS feed with retries and redirect handling."""
    items = []

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.TimeoutException:
                    if attempt < max_retries - 1:
                        delay = 1.0 * (2 ** attempt)
                        logger.debug(f"⏱️  {source_title}: timeout (attempt {attempt + 1}/{max_retries}), retrying in {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(f"⏱️  {source_title}: timeout after {timeout}s (all retries exhausted)")
                        return []
                except httpx.ConnectError as e:
                    if attempt < max_retries - 1:
                        delay = 1.0 * (2 ** attempt)
                        logger.debug(f"🔗 {source_title}: connection error (attempt {attempt + 1}/{max_retries}), retrying...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(f"🔗 {source_title}: connection failed after {max_retries} attempts")
                        return []
                except httpx.HTTPStatusError as e:
                    # Retry on 502, 503, 504, 429
                    if e.response.status_code in [429, 502, 503, 504]:
                        if attempt < max_retries - 1:
                            delay = 1.0 * (2 ** attempt)
                            logger.debug(f"⚠️  {source_title}: HTTP {e.response.status_code} (attempt {attempt + 1}/{max_retries}), retrying in {delay}s...")
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.warning(f"❌ {source_title}: HTTP {e.response.status_code} (all {max_retries} retries exhausted)")
                            return []
                    else:
                        logger.warning(f"❌ {source_title}: HTTP {e.response.status_code}")
                        return []

            try:
                feed = feedparser.parse(response.content)
            except Exception as e:
                logger.warning(f"📄 {source_title}: parse error - {type(e).__name__}")
                return []

            entry_count = 0
            for entry in feed.entries[:10]:  # Check up to 10 entries
                entry_count += 1
                try:
                    # Check if published within last 24 hours
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            pub_time = datetime(*entry.published_parsed[:6])
                            if (datetime.now() - pub_time).total_seconds() > 86400:  # 24 hours
                                continue
                        except (TypeError, ValueError) as e:
                            logger.debug(f"Date parse error in {source_title}: {type(e).__name__}")
                            pass  # No valid date, include it

                    title = entry.get("title", "").strip()
                    url = entry.get("link", "").strip()

                    if not title or not url:
                        continue

                    item = {
                        "title": title,
                        "url": url,
                        "description": entry.get("summary", "")[:300],
                        "source": source_title,
                        "language": "en",
                        "published": entry.get("published", ""),
                    }
                    items.append(item)

                except Exception as e:
                    logger.debug(f"Entry parse error in {source_title}: {type(e).__name__}")
                    continue

            if items:
                logger.info(f"✓ {source_title}: {len(items)}/{entry_count} items")
            else:
                logger.debug(f"⊘ {source_title}: no valid items found")
            return items

        except Exception as e:
            logger.error(f"❌ {source_title}: unexpected error - {type(e).__name__}: {str(e)[:150]}")
            return []

    # If all retries exhausted
    return items


async def _fetch_from_meme_api(count: int = 10) -> List[Dict[str, Any]]:
    """Fetch memes via meme-api.com (D3vd Meme API).

    This proxies Reddit server-side, so it works even when Reddit IP-blocks us
    (HTTP 429 on the .rss endpoints). Returns SFW memes only.
    """
    items: List[Dict[str, Any]] = []
    try:
        # /gimme/{count} returns a mix from popular meme subreddits
        url = f"https://meme-api.com/gimme/{max(1, min(count, 50))}"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        for m in data.get("memes", []):
            if m.get("nsfw") or m.get("spoiler"):
                continue
            title = (m.get("title") or "").strip()
            link = (m.get("postLink") or m.get("url") or "").strip()
            if not title or not link:
                continue
            subreddit = m.get("subreddit", "memes")
            items.append({
                "title": title,
                "url": link,
                "description": "",
                "source": f"Reddit r/{subreddit} (meme-api)",
                "language": "en",
                "published": "",
            })

        if items:
            logger.info(f"✓ meme-api.com: {len(items)} memes")
        else:
            logger.debug("⊘ meme-api.com: no SFW memes returned")
    except Exception as e:
        logger.warning(f"❌ meme-api.com failed: {type(e).__name__}: {str(e)[:120]}")

    return items


async def get_fresh_memes(max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch fresh meme articles from multiple sources with fallback strategy.

    Strategy:
    1. Try primary sources (priority=1)
    2. If not enough results, add secondary sources (priority=2)
    3. Return what's available (partial results OK)

    Returns:
        List of meme dicts with title, url, description, source, language
    """
    try:
        logger.info("🎬 Fetching fresh memes (primary sources)...")

        all_sources = MEME_SOURCES + MEME_SOURCES_RU

        # Separate by priority
        primary_sources = [s for s in all_sources if s.get("priority", 1) == 1]
        fallback_sources = [s for s in all_sources if s.get("priority", 1) > 1]

        # Fetch primary sources in parallel. Include meme-api.com, which proxies
        # Reddit server-side and keeps working when Reddit IP-blocks us (429).
        primary_tasks = [_fetch_from_rss(s["url"], s["title"]) for s in primary_sources]
        primary_tasks.append(_fetch_from_meme_api(count=max_results * 2))
        primary_results = await asyncio.gather(*primary_tasks, return_exceptions=True)

        # Collect primary results
        all_memes = []
        for result in primary_results:
            if isinstance(result, list):
                all_memes.extend(result)

        primary_count = len(all_memes)

        # If not enough, fetch fallback sources
        if len(all_memes) < max_results and fallback_sources:
            logger.info(f"⚠️  Only {len(all_memes)} memes from primary, trying fallback sources...")
            fallback_tasks = [_fetch_from_rss(s["url"], s["title"]) for s in fallback_sources]
            fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)

            for result in fallback_results:
                if isinstance(result, Exception):
                    logger.debug(f"Fallback source error: {type(result).__name__}")
                elif isinstance(result, list):
                    all_memes.extend(result)

        # Deduplicate by URL
        seen_urls = set()
        unique_memes = []
        for meme in all_memes:
            url = meme.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_memes.append(meme)

        # Prioritize Russian content
        ru_memes = [m for m in unique_memes if m.get("language") == "ru"]
        en_memes = [m for m in unique_memes if m.get("language") == "en"]
        sorted_memes = ru_memes + en_memes

        total = len(sorted_memes)
        logger.info(
            f"✓ Memes: {total} total (RU: {len(ru_memes)}, EN: {len(en_memes)}) | primary: {primary_count}"
        )

        return sorted_memes[:max_results]

    except Exception as e:
        logger.error(f"💥 Meme fetch failed: {type(e).__name__}: {str(e)[:150]}")
        return []


async def get_fresh_memes_for_digest(
    max_results: int = 3,
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch fresh memes for digest (no AI, just title + url + source).

    Returns:
        [{"title": str, "url": str, "source": str, "language": "ru"|"en"}, ...]
        or None if no memes found
    """
    try:
        memes = await get_fresh_memes(max_results=max_results * 2)  # Fetch extra, in case of filtering

        if not memes:
            logger.warning("⊘ No fresh memes found after trying all sources")
            return None

        # Validate and format
        result = []
        for meme in memes:
            title = meme.get("title", "").strip()
            url = meme.get("url", "").strip()
            source = meme.get("source", "Unknown")

            if not title or not url:
                logger.debug(f"Skipping invalid meme from {source}")
                continue

            # Basic safety: skip if title looks like spam
            if any(x in title.lower() for x in ["buy now", "click here", "ad:"]):
                logger.debug(f"Skipping spam-like meme: {title[:50]}")
                continue

            result.append({
                "title": title,
                "url": url,
                "source": source,
                "language": meme.get("language", "en"),
            })

            if len(result) >= max_results:
                break

        if result:
            logger.info(f"✓ Digest memes: {len(result)} items")
            return result
        else:
            logger.warning("⊘ No valid memes after filtering")
            return None

    except Exception as e:
        logger.error(f"💥 Digest meme fetch error: {type(e).__name__}: {str(e)[:150]}")
        return None


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        summaries = await get_meme_summaries()
        if summaries:
            for s in summaries:
                print(f"📺 {s['title']}")
                print(f"   {s['summary']}")
                print(f"   🔗 {s['url']}\n")
        else:
            print("No memes found")

    asyncio.run(main())
