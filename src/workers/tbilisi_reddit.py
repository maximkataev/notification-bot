"""Pick one interesting/educational/funny highlight from r/tbilisi (last day) via GPT.

Fetches recent posts from the r/tbilisi subreddit, asks ChatGPT to choose the single
most fun, curious or useful post (e.g. "a new secret coffee shop opened in Tbilisi")
and write a short Russian description. Mundane/negative posts (lost wallet, help
requests, complaints, bureaucracy) are rejected. If nothing fits, GPT returns "❌"
and the section is skipped (function returns None).
"""

import logging
import json
import re
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx
import feedparser
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

REDDIT_RSS_URL = "https://www.reddit.com/r/tbilisi/new/.rss"
# Reddit blocks the default httpx UA; use a browser-like one.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _strip_html(text: str) -> str:
    """Remove HTML tags / collapse whitespace from an RSS summary."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", no_tags).strip()


async def _fetch_recent_posts(hours: int = 36, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Fetch r/tbilisi posts published within the last `hours` hours."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=HEADERS) as client:
            response = await client.get(REDDIT_RSS_URL)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"r/tbilisi fetch failed: {type(e).__name__}: {str(e)[:120]}")
        return []

    try:
        feed = feedparser.parse(response.content)
    except Exception as e:
        logger.warning(f"r/tbilisi parse error: {type(e).__name__}")
        return []

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    posts: List[Dict[str, Any]] = []

    for entry in feed.entries[:40]:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue

        # Filter by publish/update time when available
        ts = entry.get("published_parsed") or entry.get("updated_parsed")
        if ts:
            try:
                pub_time = datetime(*ts[:6])
                if pub_time < cutoff:
                    continue
            except (TypeError, ValueError):
                pass

        body = _strip_html(entry.get("summary", ""))[:500]
        posts.append({"title": title, "url": url, "body": body})

    logger.info(f"✓ r/tbilisi: {len(posts)} posts in last {hours}h")
    return posts


async def get_tbilisi_reddit_highlight() -> Optional[Dict[str, str]]:
    """Return one curated r/tbilisi highlight or None if nothing suitable.

    Returns:
        {"title": str, "url": str, "description": str} or None
    """
    posts = await _fetch_recent_posts(hours=36)
    if not posts:
        return None

    # Build a numbered list for GPT (1-based indexing)
    listing = "\n".join(
        f"{i}. {p['title']}" + (f" — {p['body'][:200]}" if p["body"] else "")
        for i, p in enumerate(posts, 1)
    )

    prompt = f"""Вот посты из сабреддита r/tbilisi за последний день. Выбери ОДИН самый интересный, познавательный или смешной — такой, что приятно прочитать за утренним кофе.

Хорошие примеры: «в Тбилиси открылась секретная кофейня», любопытный факт о городе, забавная история, красивое место, полезная находка.

НЕ выбирай: жалобы, просьбы о помощи, «потерял/нашёл кошелёк/кота», вопросы про визы/документы/жильё/работу, политику, негатив, рекламу, объявления о продаже.

Посты:
{listing}

Если НИ ОДИН пост не подходит под критерии — ответь РОВНО одним символом: ❌

Если подходящий пост есть — ответь СТРОГО в JSON без пояснений:
{{"index": <номер поста>, "description": "<живое описание на русском, до 280 символов: что это и почему стоит глянуть>"}}"""

    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=300,
            messages=[
                {"role": "system", "content": "You are a witty Tbilisi city curator writing in Russian."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"r/tbilisi GPT selection failed: {type(e).__name__}: {str(e)[:120]}")
        return None

    if not raw or "❌" in raw:
        logger.info("r/tbilisi: GPT found no suitable post (skipping section)")
        return None

    # Extract JSON (may be wrapped in markdown code fences)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        logger.info("r/tbilisi: no JSON in GPT response (skipping section)")
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("r/tbilisi: failed to parse GPT JSON")
        return None

    index = data.get("index")
    description = (data.get("description") or "").strip()
    if not isinstance(index, int) or not (1 <= index <= len(posts)) or not description:
        logger.info("r/tbilisi: invalid index/description from GPT (skipping)")
        return None

    post = posts[index - 1]
    logger.info(f"✓ r/tbilisi highlight: {post['title'][:60]}")
    return {
        "title": post["title"],
        "url": post["url"],
        "description": description[:280],
    }
