"""Fetch fresh memes and explanations from internet sources.

Sources:
- Мемепедия (Lurkmore)
- Know Your Meme
- Reddit (meme communities)

Fetches content from last 24 hours, summarizes with AI.
"""
import logging
import httpx
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import feedparser
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Meme sources (RSS + HTML scraping)
MEME_SOURCES = [
    {
        "title": "Reddit r/memes",
        "url": "https://www.reddit.com/r/memes/.rss",
        "type": "rss",
        "language": "en",
    },
    {
        "title": "Reddit r/InternetIsBeautiful",
        "url": "https://www.reddit.com/r/InternetIsBeautiful/.rss",
        "type": "rss",
        "language": "en",
    },
    {
        "title": "Reddit r/funny",
        "url": "https://www.reddit.com/r/funny/.rss",
        "type": "rss",
        "language": "en",
    },
    {
        "title": "Reddit r/CoolGuidesDaily",
        "url": "https://www.reddit.com/r/CoolGuidesDaily/.rss",
        "type": "rss",
        "language": "en",
    },
]

MEME_SOURCES_RU = [
    {
        "title": "Reddit r/Pikabu",
        "url": "https://www.reddit.com/r/Pikabu/.rss",
        "type": "rss",
        "language": "ru",
    },
    {
        "title": "Reddit r/Russian",
        "url": "https://www.reddit.com/r/Russian/.rss",
        "type": "rss",
        "language": "ru",
    },
]


async def _fetch_from_rss(url: str, source_title: str) -> List[Dict[str, Any]]:
    """Fetch items from RSS feed."""
    items = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)

        for entry in feed.entries[:5]:  # Last 5 entries per source
            # Check if published within last 24 hours
            try:
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                    if (datetime.now() - pub_time).total_seconds() > 86400:  # 24 hours
                        continue
            except (TypeError, AttributeError):
                pass  # No date, include it

            item = {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "description": entry.get("summary", "")[:300],
                "source": source_title,
                "language": "en",
                "published": entry.get("published", ""),
            }

            if item["title"] and item["url"]:
                items.append(item)

        logger.debug(f"✓ Fetched {len(items)} memes from {source_title}")
        return items

    except Exception as e:
        logger.debug(f"Failed to fetch from {source_title}: {type(e).__name__}")
        return []


async def get_fresh_memes(max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch fresh meme articles and explanations from multiple sources.

    Returns:
        List of meme dicts with title, url, description, source, language
    """
    try:
        logger.info("Fetching fresh memes from all sources...")

        tasks = []

        # Add RSS sources (EN + RU)
        for source in MEME_SOURCES + MEME_SOURCES_RU:
            if source["type"] == "rss":
                tasks.append(_fetch_from_rss(source["url"], source["title"]))

        # Fetch all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine results
        all_memes = []
        for result in results:
            if isinstance(result, Exception):
                logger.debug(f"Source fetch failed: {result}")
            elif isinstance(result, list):
                all_memes.extend(result)

        # Prioritize Russian content
        ru_memes = [m for m in all_memes if m.get("language") == "ru"]
        en_memes = [m for m in all_memes if m.get("language") == "en"]
        all_memes = ru_memes + en_memes

        total = len(all_memes)
        logger.info(f"✓ Fetched {total} fresh memes (RU: {len(ru_memes)}, EN: {len(en_memes)})")

        return all_memes[:max_results]

    except Exception as e:
        logger.error(f"Failed to fetch memes: {type(e).__name__}: {e}")
        return []


async def get_meme_summaries() -> Optional[List[Dict[str, Any]]]:
    """
    Fetch fresh memes and get AI summaries (2-3 sentences in Russian).

    Returns:
        [
            {
                "title": str,
                "url": str,
                "source": str,
                "summary": str (2-3 sentences in Russian),
                "language": "ru" | "en"
            },
            ...
        ]
        or None if no memes found
    """
    try:
        # Fetch fresh memes
        memes = await get_fresh_memes(max_results=5)

        if not memes:
            logger.warning("No fresh memes found")
            return None

        logger.info(f"Got {len(memes)} memes, generating summaries...")

        # Prepare list for AI
        meme_list = []
        for idx, meme in enumerate(memes, 1):
            meme_list.append({
                "index": idx,
                "title": meme.get("title", ""),
                "description": meme.get("description", ""),
                "url": meme.get("url", ""),
                "source": meme.get("source", ""),
            })

        # Send to GPT-4o for summaries
        client = get_client()
        prompt = f"""У тебя есть список свежих мемов/интернет-явлений.
Для каждого напиши краткий пересказ (2-3 предложения) на русском, объясняя что это такое и почему это мемом стало.

Мемы:
"""
        for item in meme_list:
            prompt += f"\n{item['index']}. {item['title']}\n   {item['description'][:200]}"

        prompt += f"""

Ответь ТОЛЬКО JSON (без markdown):
{{
  "summaries": [
    {{
      "index": 1,
      "summary": "краткое объяснение (2-3 предложения на русском)"
    }},
    ...
  ]
}}"""

        response = client.messages.create(
            model="gpt-5.4-mini",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()
        logger.debug(f"AI response length: {len(response_text)}")

        # Parse JSON response
        import json
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        result_data = json.loads(response_text)
        summaries_data = result_data.get("summaries", [])

        # Combine with original meme data
        result = []
        for summary_item in summaries_data:
            idx = summary_item.get("index", 1) - 1
            if 0 <= idx < len(memes):
                meme = memes[idx]
                result.append({
                    "title": meme.get("title", ""),
                    "url": meme.get("url", ""),
                    "source": meme.get("source", ""),
                    "summary": summary_item.get("summary", ""),
                    "language": meme.get("language", "en"),
                })

        logger.info(f"✓ Generated summaries for {len(result)} memes")
        return result if result else None
    except Exception as e:
        logger.error(f"Failed to get meme summaries: {type(e).__name__}: {e}")
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
