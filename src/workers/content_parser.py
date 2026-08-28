"""Parse real content sources: YouTube, podcasts RSS, Spotify, etc.

Returns actual video/podcast/music items with real working links.
No hardcoding - only real content from APIs and RSS feeds.
AI selects fresh content and writes review in Russian.
"""

import logging
import httpx
import asyncio
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import feedparser
import base64
from src.utils.openai_client import get_client
from src.utils.doppler import get_secret
from src.db.database import (
    get_shown_creators,
    get_shown_keys,
    record_shown_content,
    record_shown_item,
)

logger = logging.getLogger(__name__)

# Per-user content tuning for the "Для вас" recommendation.
# Users listed here get a THEMED PODCAST matching their interests; everyone else
# (incl. the main user 71488343) keeps the default analyst-oriented mixed content.
CONTENT_PROFILES = {
    184010236: {  # Маша
        "podcast_only": True,
        "interests": "что-нибудь доброе, хорошее, тёплое или творческое: искусство, креатив, вдохновляющие и душевные истории, рукоделие, культура",
    },
    498233237: {  # Юля
        "podcast_only": True,
        "interests": "художественное и культурное: искусство, скульптура, архитектура, культура и искусство Европы, Азии и арабских стран",
    },
}
DEFAULT_CONTENT_INTERESTS = "интересный и полезный для бизнес- и системного аналитика (AI, технологии, наука, бизнес)"

# Anti-repeat memory (SQLite, data/tasks.db — survives restarts/redeploys):
#   - "video_item" / "podcast_item": exact video/episode URLs sent to a user. Nothing
#     is ever sent twice within the 90-day history window.
#   - "podcast": podcast creators sent to a user. GPT otherwise keeps picking the
#     single best thematic match (e.g. Arzamas) every day, so already-shown creators
#     are dropped from the pool as long as other options remain.
#   - "album": albums recommended to a user.
_ITEM_HISTORY_TYPES = {"video": "video_item", "podcast": "podcast_item"}


async def _shown_item_urls(user_id: Optional[int]) -> set:
    """URLs of videos/episodes already sent to this user in the history window."""
    if not user_id:
        return set()
    try:
        urls: set = set()
        for content_type in _ITEM_HISTORY_TYPES.values():
            urls.update(await get_shown_keys(user_id, content_type))
        return urls
    except Exception as e:
        logger.warning(f"Could not load shown content history: {type(e).__name__}: {e}")
        return set()


async def _record_shown_recommendation(user_id: Optional[int], result: Dict[str, Any]) -> None:
    """Remember a recommended video/episode so it never repeats within the window."""
    content_type = _ITEM_HISTORY_TYPES.get(result.get("type", ""))
    url = (result.get("url") or "").strip()
    if not user_id or not content_type or not url:
        return
    try:
        await record_shown_item(
            user_id,
            content_type,
            url,
            creator=result.get("creator") or url,
            title=result.get("title"),
            url=url,
        )
    except Exception as e:
        logger.warning(f"Could not record shown content: {type(e).__name__}: {e}")


# The review is written for content that is ALREADY being sent, so a hedging
# "this probably isn't for you" line makes no sense in the digest. If the model
# produces one anyway, drop it and fall back to the item's own description.
_DISMISSIVE_MARKERS = (
    "не подойд",
    "не совсем подойд",
    "вряд ли подойд",
    "вряд ли заинтерес",
    "не очень подходит",
    "не совсем то",
    "не соответствует интерес",
    "не совпадает с интерес",
    "не по теме",
    "не релевант",
    "мало связан",
    "не самый подходящий",
    "не идеально подходит",
    "не лучший выбор",
    "может не понравиться",
    "не входит в интерес",
    "к сожалению",
    "ничего подходящего",
)


def _sanitize_review(review: str, item: Dict[str, Any]) -> str:
    """Drop a dismissive review, falling back to the item's real description."""
    text = (review or "").strip()
    if text and not any(marker in text.lower() for marker in _DISMISSIVE_MARKERS):
        return text

    if text:
        logger.warning(f"Dismissive review discarded: {text[:80]}")

    fallback = (item.get("description") or "").strip()
    return fallback[:150] if fallback else ""

# Real content sources (channels, playlists, podcasts)
# YouTube channels with both ID (for fetching) and channel URL (for display)
YOUTUBE_CHANNELS = {
    # English channels
    "videos_educational": [
        {
            "id": "UCsooa4yRKGN_zEE8iknghZA",
            "name": "TED-Ed",
            "url": "https://www.youtube.com/@TEDed",
        },
        {
            "id": "UCAuUUnT6oDeKwE6v1NGQxug",
            "name": "TED",
            "url": "https://www.youtube.com/@TED",
        },
        {
            "id": "UCHnyfMqiRRG1u-2MsSQLbXA",
            "name": "Veritasium",
            "url": "https://www.youtube.com/@veritasium",
        },
        {
            "id": "UCYO_jab_esuFRV4b17AJtAw",
            "name": "3Blue1Brown",
            "url": "https://www.youtube.com/@3blue1brown",
        },
        {
            "id": "UCX6b17PVsYBQ0ip5gyeme-Q",
            "name": "Crash Course",
            "url": "https://www.youtube.com/@crashcourse",
        },
        {
            "id": "UC9-y-6csu5mg-rbJ7_TcQAA",
            "name": "Computerphile",
            "url": "https://www.youtube.com/@Computerphile",
        },
        {
            "id": "UCsXVk37bltHxD1rDPwtNM8Q",
            "name": "Kurzgesagt",
            "url": "https://www.youtube.com/@kurzgesagt",
        },
        {
            "id": "UC2D2CMWXMOVWx7giW1n3LIg",
            "name": "Huberman Lab",
            "url": "https://www.youtube.com/@hubermanlab",
        },
        {
            "id": "UCSHZKyawb77ixDdsGog4iWA",
            "name": "Lex Fridman",
            "url": "https://www.youtube.com/@lexfridman",
        },
    ],
    "videos_productivity": [
        {
            "id": "UCoOae5nYA7VqaXzerajD0lg",
            "name": "Ali Abdaal",
            "url": "https://www.youtube.com/@aliabdaal",
        },
        {
            "id": "UCG-KntY7aVnIGXYEBQvmBAQ",
            "name": "Thomas Frank",
            "url": "https://www.youtube.com/@thomasfrank",
        },
        {
            "id": "UCJ24N4O0bP7LGLBDvye7oCA",
            "name": "Matt D'Avella",
            "url": "https://www.youtube.com/@mattdavella",
        },
        {
            "id": "UC9vLsnF6QPYuH51njmIooCQ",
            "name": "System Design Interview",
            "url": "https://www.youtube.com/@SystemDesignInterview",
        },
        {
            "id": "UC8butISFwT-Wl7EV0hUK0BQ",
            "name": "freeCodeCamp",
            "url": "https://www.youtube.com/@freecodecamp",
        },
    ],
    "videos_tech": [
        {
            "id": "UCbfYPyITQ-7l4upoX8nvctg",
            "name": "Fireship",
            "url": "https://www.youtube.com/@fireship",
        },
        {
            "id": "UCCezIgC97PvUuR4_gbFUs5g",
            "name": "Corey Schafer",
            "url": "https://www.youtube.com/@coreyms",
        },
        {
            "id": "UCW5YeuERMmlnqo4oq8vwUpg",
            "name": "The Net Ninja",
            "url": "https://www.youtube.com/@NetNinja",
        },
        {
            "id": "UCsBjURrPoezykLs9EqgamOA",
            "name": "Ben Awad",
            "url": "https://www.youtube.com/@benawad",
        },
    ],
    # Russian channels
    "videos_ru_documentary": [
        {
            "id": "UCpHYYe5wzme6XJfYQbM8-_Q",
            "name": "Простые мысли",
            "url": "https://www.youtube.com/@simple_thoughts",
        },
        {
            "id": "UC4q1jrIeAOLh7Jw7YazqPWQ",
            "name": "Файб",
            "url": "https://www.youtube.com/@pheeb_official",
        },
        {
            "id": "UC0oLxL8yFsI6KyXdDgnJi4g",
            "name": "SUREN",
            "url": "https://www.youtube.com/@surenart",
        },
    ],
    "videos_ru_science": [
        {
            "id": "UC5f5IV0Bf79YLp_p9nfInRA",
            "name": "SciOne",
            "url": "https://www.youtube.com/@scione",
        },
        {
            "id": "UC3Mss4t8lN4qUQ9-7Y0Q1nA",
            "name": "Мы и Они",
            "url": "https://www.youtube.com/@myandthey",
        },
        {
            "id": "UC6uFo0i20oRjv4jM6Vn0Y6A",
            "name": "Основа",
            "url": "https://www.youtube.com/@Osnova",
        },
    ],
    "videos_ru_society": [
        {
            "id": "UC3bbYb7N7o2dC6Fsl9M6m2Q",
            "name": "Жиза",
            "url": "https://www.youtube.com/@zhiza",
        },
        {
            "id": "UCW7sU3D8R8b8TnLq4v9P8bw",
            "name": "Черный кабинет",
            "url": "https://www.youtube.com/@blackcabinetyt",
        },
    ],
    "videos_ru_travel": [
        {
            "id": "UCm0x7wraT70xW4K8v3a3d7Q",
            "name": "Хочу домой",
            "url": "https://www.youtube.com/@khochudomoy",
        },
    ],
    "videos_ru_food": [
        {
            "id": "UC5m6D8V7kW9f8tY1j3n6kPQ",
            "name": "Покашеварим",
            "url": "https://www.youtube.com/@pokashevarim",
        },
    ],
}

PODCAST_SOURCES = [
    # English podcasts
    {
        "title": "Data Skeptic",
        "rss_url": "https://dataskeptic.libsyn.com/rss",
        "channel_url": "https://dataskeptic.com/",
        "language": "en",
        "category": "ai_data",
    },
    {
        "title": "The Gradient",
        "rss_url": "https://feeds.buzzsprout.com/1832356.rss",
        "channel_url": "https://thegradient.pub/",
        "language": "en",
        "category": "ai",
    },
    {
        "title": "Lex Fridman Podcast",
        "rss_url": "https://lexfridman.com/feed/podcast/",
        "channel_url": "https://lexfridman.com/",
        "language": "en",
        "category": "ai_tech",
    },
    {
        "title": "Darknet Diaries",
        "rss_url": "https://feeds.megaphone.fm/darknetdiaries",
        "channel_url": "https://darknetdiaries.com/",
        "language": "en",
        "category": "tech_security",
    },
    {
        "title": "Software Engineering Daily",
        "rss_url": "https://feeds.softwareengineeringdaily.com/rss.xml",
        "channel_url": "https://softwareengineeringdaily.com/",
        "language": "en",
        "category": "tech_engineering",
    },
    {
        "title": "The Changelog",
        "rss_url": "https://feeds.changelog.com/podcast",
        "channel_url": "https://changelog.com/podcast",
        "language": "en",
        "category": "tech_engineering",
    },
    {
        "title": "a16z Podcast",
        "rss_url": "https://feeds.simplecast.com/JGE3yC0V",
        "channel_url": "https://a16z.com/podcast/",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "Y Combinator Podcast",
        "rss_url": "https://feeds.megaphone.fm/ycombinator",
        "channel_url": "https://www.ycombinator.com/podcast/",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "Masters of Scale",
        "rss_url": "https://feeds.megaphone.fm/masterscale",
        "channel_url": "https://mastersofscale.com/",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "The Tim Ferriss Show",
        "rss_url": "https://feeds.megaphone.fm/timferriss",
        "channel_url": "https://tim.blog/podcast/",
        "language": "en",
        "category": "productivity",
    },
    {
        "title": "Huberman Lab",
        "rss_url": "https://feeds.megaphone.fm/hubermanlab",
        "channel_url": "https://hubermanlab.com/",
        "language": "en",
        "category": "health_productivity",
    },
    {
        "title": "StarTalk Radio",
        "rss_url": "https://feeds.megaphone.fm/startalk",
        "channel_url": "https://www.startalkradio.net/",
        "language": "en",
        "category": "science",
    },
    # Russian podcasts - main
    {
        "title": "Радио-Т",
        "rss_url": "https://radio-t.com/podcast.rss",
        "channel_url": "https://radio-t.com/",
        "language": "ru",
        "category": "tech",
    },
    {
        "title": "Закат Империи",
        "rss_url": "https://anchor.fm/s/11d8d8c4/podcast/rss",
        "channel_url": "https://anchor.fm/zakatimperii",
        "language": "ru",
        "category": "history",
    },
    {
        "title": "Сперва роди",
        "rss_url": "https://feeds.simplecast.com/xq6WTx9j",
        "channel_url": "https://spervarodi.simplecast.com/",
        "language": "ru",
        "category": "society",
    },
    {
        "title": "Норм",
        "rss_url": "https://feeds.simplecast.com/eAKaDgaQ",
        "channel_url": "https://norm.simplecast.com/",
        "language": "ru",
        "category": "culture_society",
    },
    {
        "title": "Короче, история",
        "rss_url": "https://feeds.simplecast.com/7wzebh8X",
        "channel_url": "https://koroche-historia.simplecast.com/",
        "language": "ru",
        "category": "history",
    },
    {
        "title": "Это провал",
        "rss_url": "https://feeds.simplecast.com/o6w7K_-I",
        "channel_url": "https://etoprovalnow.simplecast.com/",
        "language": "ru",
        "category": "business_failures",
    },
    {
        "title": "Деньги пришли",
        "rss_url": "https://feeds.megaphone.fm/MEDUZA6636460993",
        "channel_url": "https://meduza.io/",
        "language": "ru",
        "category": "finance",
    },
    {
        "title": "Хочу не могу",
        "rss_url": "https://feeds.simplecast.com/9Wn6mA6m",
        "channel_url": "https://khochunemogou.simplecast.com/",
        "language": "ru",
        "category": "psychology_relationships",
    },
    {
        "title": "Либо выйдет, либо нет",
        "rss_url": "https://feeds.simplecast.com/Vuxy4v5Z",
        "channel_url": "https://libo-vydet.simplecast.com/",
        "language": "ru",
        "category": "startups_business",
    },
    {
        "title": "Arzamas",
        "rss_url": "https://arzamas.academy/feed_v1/podcast.rss",
        "channel_url": "https://arzamas.academy/",
        "language": "ru",
        "category": "culture_education",
    },
    # Russian podcasts - underground
    {
        "title": "Так вышло",
        "rss_url": "https://feeds.megaphone.fm/meduza-tak-vyshlo",
        "channel_url": "https://meduza.io/",
        "language": "ru",
        "category": "society_ethics",
    },
    {
        "title": "Проветримся!",
        "rss_url": "https://feeds.simplecast.com/4_j8wz0P",
        "channel_url": "https://provetrimsia.simplecast.com/",
        "language": "ru",
        "category": "mental_health",
    },
    {
        "title": "Либо получится, либо сдохнем",
        "rss_url": "https://feeds.simplecast.com/Wp9s6x4B",
        "channel_url": "https://libo-poluchitsia.simplecast.com/",
        "language": "ru",
        "category": "startups",
    },
    {
        "title": "Кавачай",
        "rss_url": "https://feeds.soundcloud.com/users/soundcloud:users:231188278/sounds.rss",
        "channel_url": "https://soundcloud.com/kavachay",
        "language": "ru",
        "category": "internet_culture",
    },
    {
        "title": "Blitz and Chips",
        "rss_url": "https://feeds.soundcloud.com/users/soundcloud:users:447105959/sounds.rss",
        "channel_url": "https://soundcloud.com/blitz-and-chips",
        "language": "ru",
        "category": "science_future",
    },
    {
        "title": "Ночной подкаст",
        "rss_url": "https://feeds.simplecast.com/Q0v7mP9x",
        "channel_url": "https://nochnoj-podkast.simplecast.com/",
        "language": "ru",
        "category": "calm_talk",
    },
    {
        "title": "Это разве секс?",
        "rss_url": "https://feeds.simplecast.com/jm0lPB7M",
        "channel_url": "https://etoraves-sex.simplecast.com/",
        "language": "ru",
        "category": "relationships",
    },
    {
        "title": "Полка",
        "rss_url": "https://polka.academy/feed/podcast/",
        "channel_url": "https://polka.academy/",
        "language": "ru",
        "category": "books_culture",
    },
]

MUSIC_PLAYLISTS = [
    # Neutral (language-agnostic) music
    {
        "title": "Lofi Girl - beats to relax/study to",
        "platform": "youtube",
        "url": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
        "description": "lo-fi для работы и фонового фокуса",
        "language": "en",
    },
    {
        "title": "Peaceful Piano",
        "platform": "spotify",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DX4sWSpwq3LiO",
        "description": "спокойное пианино без вокала",
        "language": "en",
    },
    {
        "title": "Deep Focus",
        "platform": "spotify",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DWZeKCadgRdKQ",
        "description": "ambient/electronic для глубокой концентрации",
        "language": "en",
    },
    {
        "title": "lofi beats",
        "platform": "spotify",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DWWQRwui0ExPn",
        "description": "lo-fi beats для фокуса",
        "language": "en",
    },
    {
        "title": "Jazz in the Background",
        "platform": "spotify",
        "url": "https://open.spotify.com/playlist/37i9dQZF1DX0SM0LYsmbMT",
        "description": "легкий джаз на фоне",
        "language": "en",
    },
]


async def _fetch_single_youtube_channel(
    channel: Dict, hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Fetch a single YouTube channel's recent video (for parallel execution).

    Returns only videos published within the last `hours` hours.
    Links to specific videos, not channel pages.
    """
    try:
        channel_id = channel["id"]
        channel_name = channel["name"]
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        ) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)

        # Find first video published within time window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        for entry in feed.entries[:5]:  # Check first 5 entries
            try:
                pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if pub_time < cutoff:
                    continue  # Too old

                video_url = entry.get("link", "")
                if not video_url:
                    continue

                # Get video title from entry
                video_title = entry.get("title", channel_name)

                video = {
                    "title": video_title,
                    "creator": channel_name,
                    "url": video_url,
                    "description": entry.get("summary", "")[:150],
                    "type": "video",
                    "platform": "youtube",
                    "published": entry.get("published", ""),
                }
                return video
            except (TypeError, AttributeError):
                continue

    except Exception as e:
        logger.debug(
            f"Failed to fetch YouTube channel {channel.get('name', 'unknown')}: {type(e).__name__}: {str(e)[:100]}"
        )
    return None


async def get_youtube_videos(
    max_results: int = 5, hours: int = 24
) -> List[Dict[str, Any]]:
    """
    Fetch recent videos from English YouTube channels (parallel).
    Only returns videos published within the last `hours` hours.

    Args:
        max_results: max videos to return
        hours: time window in hours (default 24)

    Returns:
        List of video dicts with title, creator, specific video URL, description
    """
    try:
        # Get only English channels (exclude videos_ru*)
        en_categories = {
            k: v for k, v in YOUTUBE_CHANNELS.items() if not k.startswith("videos_ru")
        }
        all_channels = []
        for channels_list in en_categories.values():
            all_channels.extend(channels_list)

        # Fetch all channels in parallel with timeout
        tasks = [_fetch_single_youtube_channel(ch, hours=hours) for ch in all_channels]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(8.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=8.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"YouTube videos fetch timed out after 8s")
            results = []

        # Filter out None and Exception results
        videos = [r for r in results if r and not isinstance(r, Exception)]

        # Log successes and failures
        failures = sum(1 for r in results if not r or isinstance(r, Exception))
        logger.debug(
            f"YouTube videos: {len(videos)} success, {failures} failures from {len(all_channels)} channels"
        )

        return videos[:max_results]

    except Exception as e:
        logger.warning(f"Failed to fetch YouTube videos: {type(e).__name__}: {e}")
        return []


def _best_episode_url(entry: Any, source: Dict) -> str:
    """Pick the best usable absolute URL for a podcast episode.

    Some feeds (e.g. Arzamas) put a non-URL slug in <link> ("podcast-other-149")
    and the real address only in the <enclosure> audio href — the old code used the
    slug verbatim, so the digest podcast had a broken/relative link. We now require
    an absolute http(s) URL, trying in order: <link> → enclosure → links → channel page.
    """
    def _abs(u: str) -> bool:
        return u.startswith("http://") or u.startswith("https://")

    candidates = [(entry.get("link") or "").strip()]
    candidates += [(enc.get("href") or "").strip() for enc in (entry.get("enclosures") or [])]
    candidates += [(link.get("href") or "").strip() for link in (entry.get("links") or [])]

    for url in candidates:
        if _abs(url):
            return url
    return (source.get("channel_url") or "").strip()


async def _fetch_single_podcast(
    source: Dict, hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Fetch a single podcast's recent episode (for parallel execution).

    Returns only episodes published within the last `hours` hours.
    Links to specific episodes, not channel pages.
    """
    try:
        rss_url = source.get("rss_url") or source.get("url")
        source_title = source.get("title", "Podcast")

        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        ) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)

        # Find first episode published within time window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        for entry in feed.entries[:5]:  # Check first 5 entries
            try:
                pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if pub_time < cutoff:
                    continue  # Too old

                episode_url = _best_episode_url(entry, source)
                if not episode_url:
                    continue

                # Get episode title
                episode_title = entry.get("title", source_title)

                podcast = {
                    "title": episode_title,
                    "creator": source_title,
                    "url": episode_url,
                    "description": entry.get("summary", "")[:150],
                    "type": "podcast",
                    "platform": "podcast",
                    "published": entry.get("published", ""),
                }
                return podcast
            except (TypeError, AttributeError):
                continue

    except Exception as e:
        logger.debug(
            f"Failed to fetch podcast {source.get('title', 'unknown')}: {type(e).__name__}: {str(e)[:100]}"
        )
    return None


async def get_podcasts(
    language: str = "en", max_results: int = 5, hours: int = 24
) -> List[Dict[str, Any]]:
    """
    Fetch recent podcast episodes from RSS feeds (parallel).
    Only returns episodes published within the last `hours` hours.

    Args:
        language: 'en', 'ru', or 'all'
        max_results: max episodes to return
        hours: time window in hours (default 24)

    Returns:
        List of podcast dicts with title, creator, specific episode URL, description
    """
    try:
        sources = [
            s
            for s in PODCAST_SOURCES
            if language == "all" or s.get("language") == language
        ]

        # Fetch all podcasts in parallel with timeout
        tasks = [_fetch_single_podcast(s, hours=hours) for s in sources]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(8.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=8.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Podcast fetch timed out after 8s")
            results = []

        # Filter out None and Exception results
        podcasts = [r for r in results if r and not isinstance(r, Exception)]

        # Log successes and failures
        failures = sum(1 for r in results if not r or isinstance(r, Exception))
        logger.debug(
            f"Podcasts ({language}): {len(podcasts)} success, {failures} failures from {len(sources)} sources"
        )

        return podcasts[:max_results]

    except Exception as e:
        logger.warning(f"Failed to fetch podcasts: {type(e).__name__}: {e}")
        return []


async def get_music(max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Get music playlists/recommendations.

    Returns:
        List of music dicts with title, creator, url, description
    """
    try:
        music = []

        for playlist in MUSIC_PLAYLISTS:
            music_item = {
                "title": playlist.get("title", ""),
                "creator": "Music",
                "url": playlist.get("url", ""),
                "description": playlist.get("description", ""),
                "type": "music",
                "platform": playlist.get("platform", "youtube"),
            }

            if music_item["title"] and music_item["url"]:
                music.append(music_item)

        logger.debug(f"✓ Loaded {len(music)} music items")
        return music[:max_results]

    except Exception as e:
        logger.warning(f"Failed to get music: {type(e).__name__}: {e}")
        return []


async def _fetch_single_russian_youtube_channel(
    channel: Dict, hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Fetch a single Russian YouTube channel's recent video (for parallel execution).

    Returns only videos published within the last `hours` hours.
    Links to specific videos, not channel pages.
    """
    try:
        channel_id = channel["id"]
        channel_name = channel["name"]
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        try:
            async with httpx.AsyncClient(
                timeout=6.0,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            ) as client:
                response = await client.get(rss_url)
                response.raise_for_status()

            feed = feedparser.parse(response.content)

            # Find first video published within time window
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            for entry in feed.entries[:5]:  # Check first 5 entries
                try:
                    pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if pub_time < cutoff:
                        continue  # Too old

                    video_url = entry.get("link", "")
                    if not video_url:
                        continue

                    # Get video title from entry
                    video_title = entry.get("title", channel_name)

                    video = {
                        "title": video_title,
                        "creator": channel_name,
                        "url": video_url,
                        "description": entry.get("summary", "")[:150],
                        "type": "video",
                        "platform": "youtube",
                        "language": "ru",
                        "published": entry.get("published", ""),
                    }
                    return video
                except (TypeError, AttributeError):
                    continue
        except asyncio.CancelledError:
            logger.debug(f"Russian YouTube fetch cancelled: {channel_name}")
            raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug(
            f"Failed to fetch Russian YouTube {channel.get('name', 'unknown')}: {type(e).__name__}: {str(e)[:100]}"
        )
    return None


async def get_russian_youtube_videos(
    max_results: int = 3, hours: int = 24
) -> List[Dict[str, Any]]:
    """Fetch recent videos from Russian YouTube channels (parallel).
    Only returns videos published within the last `hours` hours.
    Links to specific videos, not channel pages.
    """
    try:
        # Filter Russian channels from unified YOUTUBE_CHANNELS
        ru_categories = {
            k: v for k, v in YOUTUBE_CHANNELS.items() if k.startswith("videos_ru")
        }
        all_channels = []
        for channels_list in ru_categories.values():
            all_channels.extend(channels_list)

        # Fetch all channels in parallel with timeout
        tasks = [
            _fetch_single_russian_youtube_channel(ch, hours=hours)
            for ch in all_channels
        ]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(15.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=15.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Russian YouTube videos fetch timed out after 15s")
            results = []

        # Filter out None and Exception results
        videos = [r for r in results if r and not isinstance(r, Exception)]

        # Log successes and failures
        failures = sum(1 for r in results if not r or isinstance(r, Exception))
        logger.debug(
            f"Russian YouTube videos: {len(videos)} success, {failures} failures from {len(all_channels)} channels"
        )

        return videos[:max_results]
    except Exception as e:
        logger.warning(
            f"Failed to fetch Russian YouTube videos: {type(e).__name__}: {e}"
        )
        return []


async def _fetch_single_russian_podcast(
    source: Dict, hours: int = 24
) -> Optional[Dict[str, Any]]:
    """Fetch a single Russian podcast's recent episode (for parallel execution).

    Returns only episodes published within the last `hours` hours.
    Links to specific episodes, not channel pages.
    """
    try:
        rss_url = source.get("rss_url") or source.get("url")
        source_title = source.get("title", "Podcast")

        try:
            async with httpx.AsyncClient(
                timeout=6.0,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            ) as client:
                response = await client.get(rss_url)
                response.raise_for_status()

            feed = feedparser.parse(response.content)

            # Find first episode published within time window
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            for entry in feed.entries[:5]:  # Check first 5 entries
                try:
                    pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    if pub_time < cutoff:
                        continue  # Too old

                    # Some Russian feeds (e.g. Arzamas) put a non-URL slug in <link>
                    # ("podcast-other-149"); _best_episode_url falls back to the
                    # enclosure href, then the channel page, so we always get a real link.
                    episode_url = _best_episode_url(entry, source)
                    if not episode_url:
                        continue

                    # Get episode title
                    episode_title = entry.get("title", source_title)

                    podcast = {
                        "title": episode_title,
                        "creator": source_title,
                        "url": episode_url,
                        "description": entry.get("summary", "")[:150],
                        "type": "podcast",
                        "platform": "podcast",
                        "language": "ru",
                        "published": entry.get("published", ""),
                    }
                    return podcast
                except (TypeError, AttributeError):
                    continue
        except asyncio.CancelledError:
            logger.debug(f"Russian podcast fetch cancelled: {source_title}")
            raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug(
            f"Failed to fetch Russian podcast {source.get('title', 'unknown')}: {type(e).__name__}: {str(e)[:100]}"
        )
    return None


async def get_russian_podcasts(
    max_results: int = 3, hours: int = 24
) -> List[Dict[str, Any]]:
    """Fetch recent episodes from Russian podcasts (parallel).
    Only returns episodes published within the last `hours` hours.
    """
    try:
        ru_sources = [s for s in PODCAST_SOURCES if s.get("language") == "ru"]

        # Fetch all Russian podcasts in parallel with timeout
        tasks = [_fetch_single_russian_podcast(s, hours=hours) for s in ru_sources]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(15.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=15.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Russian podcasts fetch timed out after 15s")
            results = []

        # Filter out None and Exception results
        podcasts = [r for r in results if r and not isinstance(r, Exception)]

        # Log successes and failures
        failures = sum(1 for r in results if not r or isinstance(r, Exception))
        logger.debug(
            f"Russian podcasts: {len(podcasts)} success, {failures} failures from {len(ru_sources)} sources"
        )

        return podcasts[:max_results]
    except Exception as e:
        logger.warning(f"Failed to fetch Russian podcasts: {type(e).__name__}: {e}")
        return []


async def fetch_fresh_content(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Fetch fresh content from YouTube and podcasts (EN + RU) published within last N hours.

    Returns:
        List of content items with title, creator, specific video/episode URL, type, language
    """
    try:
        logger.debug(f"Fetching fresh content from last {hours} hours...")

        # Fetch all sources in parallel with timeout
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(25.0):
                    en_videos, en_podcasts, ru_videos, ru_podcasts = (
                        await asyncio.gather(
                            get_youtube_videos(max_results=10, hours=hours),
                            get_podcasts(language="en", max_results=10, hours=hours),
                            get_russian_youtube_videos(max_results=10, hours=hours),
                            get_russian_podcasts(max_results=10, hours=hours),
                            return_exceptions=True,
                        )
                    )
            else:
                en_videos, en_podcasts, ru_videos, ru_podcasts = await asyncio.wait_for(
                    asyncio.gather(
                        get_youtube_videos(max_results=10, hours=hours),
                        get_podcasts(language="en", max_results=10, hours=hours),
                        get_russian_youtube_videos(max_results=10, hours=hours),
                        get_russian_podcasts(max_results=10, hours=hours),
                        return_exceptions=True,
                    ),
                    timeout=25.0,
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(f"Content fetch timed out after 25s")
            en_videos = en_podcasts = ru_videos = ru_podcasts = []

        # Handle exceptions
        en_videos = en_videos if isinstance(en_videos, list) else []
        en_podcasts = en_podcasts if isinstance(en_podcasts, list) else []
        ru_videos = ru_videos if isinstance(ru_videos, list) else []
        ru_podcasts = ru_podcasts if isinstance(ru_podcasts, list) else []

        # Log detailed source status
        logger.debug(
            f"EN videos: {len(en_videos)}, EN podcasts: {len(en_podcasts)}, RU videos: {len(ru_videos)}, RU podcasts: {len(ru_podcasts)}"
        )

        # Combine: Russian first (priority), then English
        all_content = []
        all_content.extend(ru_videos)
        all_content.extend(ru_podcasts)
        all_content.extend(en_videos)
        all_content.extend(en_podcasts)

        logger.info(
            f"✓ Fetched {len(all_content)} fresh items in {hours}h window (RU: {len(ru_videos)+len(ru_podcasts)} EN: {len(en_videos)+len(en_podcasts)})"
        )

        return all_content

    except Exception as e:
        logger.error(f"Failed to fetch fresh content: {type(e).__name__}: {e}")
        return []


async def _select_and_describe(
    items: List[Dict[str, Any]],
    interests: str = DEFAULT_CONTENT_INTERESTS,
) -> Optional[Dict[str, Any]]:
    """Use GPT to select the best item matching `interests` and write a description."""
    if not items:
        return None

    # Prepare for AI
    content_list = []
    for idx, item in enumerate(items[:20], 1):
        content_list.append(
            {
                "index": idx,
                "type": item.get("type", ""),
                "title": item.get("title", ""),
                "creator": item.get("creator", ""),
                "snippet": item.get("description", "")[:100],
                "language": item.get("language", "en"),
            }
        )

    try:
        client = get_client()
        prompt = f"""У тебя есть список свежего контента. Выбери ОДИН, наиболее подходящий под интересы: {interests}.

Контент:
{json.dumps(content_list, ensure_ascii=False, indent=2)}

Обзор пиши как рекомендацию к выбранному элементу: о чём он и чем интересен.
ЗАПРЕЩЕНО писать, что контент не подходит, не по теме, не соответствует интересам,
извиняться или оценивать степень соответствия — выбранное уже отправляется человеку.
Если идеального совпадения нет, всё равно выбери лучший вариант и опиши его по сути.

Ответь только JSON без markdown:
{{
  "index": <номер выбранного элемента (1-{len(content_list)})>,
  "review": "<краткий обзор на русском, 1-3 предложения, макс 150 символов>"
}}"""

        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content.strip()
        selected = json.loads(response_text)
        selected_idx = selected.get("index", 1) - 1
        review = selected.get("review", "")

        if 0 <= selected_idx < len(items):
            item = items[selected_idx]
            result = {
                "type": item.get("type", ""),
                "title": item.get("title", ""),
                "creator": item.get("creator", ""),
                "url": item.get("url", ""),
                "review": _sanitize_review(review, item),
                "language": item.get("language", "en"),
                "platform": item.get("platform", ""),
            }
            logger.info(f"✓ Selected: {result['type']} - {result['title'][:50]}")
            return result

    except Exception as e:
        logger.warning(f"Failed to select content: {type(e).__name__}: {e}")
    return None


async def _spotify_get_access_token() -> Optional[str]:
    """Get Spotify API access token. Returns token or None if failed."""
    try:
        client_id = get_secret("SPOTIFY_CLIENT_ID")
        client_secret = get_secret("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.warning("⚠️  Spotify credentials missing (SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET)")
            return None

        # Get access token
        auth_str = f"{client_id}:{client_secret}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                token_response = await client.post(
                    "https://accounts.spotify.com/api/token",
                    headers={"Authorization": f"Basic {auth_b64}"},
                    data={"grant_type": "client_credentials"},
                )
                token_response.raise_for_status()
        except httpx.TimeoutException:
            logger.error("🔐 Spotify auth: timeout (10s)")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"🔐 Spotify auth: HTTP {e.response.status_code}")
            return None

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            logger.error("🔐 Spotify auth: no access token in response")
            return None

        logger.debug(f"✓ Spotify token obtained ({len(access_token)} chars)")
        return access_token

    except Exception as e:
        logger.error(f"💥 Spotify auth error: {type(e).__name__}: {str(e)[:150]}")
        return None


# GPT sometimes attributes a real album to the wrong artist ("The Wake" is IQ's,
# not Marillion's). The strict Spotify query then finds nothing, so we ask GPT for
# a different album instead of dropping the whole section.
ALBUM_MAX_ATTEMPTS = 3


def _norm_music_name(value: str) -> str:
    """Lowercase alphanumeric form for fuzzy album/artist comparison."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


async def _spotify_search(query: str, access_token: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Run one Spotify album search. Returns raw album items ([] on any failure)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "type": "album", "limit": limit},
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        logger.warning(f"🎵 Spotify search: timeout for {query!r}")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"🎵 Spotify search: HTTP {e.response.status_code} for {query!r}")
        return []
    except Exception as e:
        logger.error(f"💥 Spotify search error: {type(e).__name__}: {str(e)[:150]}")
        return []

    return response.json().get("albums", {}).get("items", []) or []


async def _spotify_search_album(
    album: str, artist: str, access_token: str
) -> Optional[Dict[str, str]]:
    """Find an album on Spotify. Returns {"url", "album", "artist"} or None.

    Every query keeps the artist, so a hallucinated artist still fails here (the
    caller then asks GPT for another album). What this does recover is GPT packing
    "Artist — Album" into the album field, which the strict field query can't match.
    """
    if not access_token or not album:
        return None

    bare_album = re.split(r"\s+[—–-]\s+", album)[-1].strip() or album

    queries = [f"album:{album} artist:{artist}"]
    if _norm_music_name(bare_album) != _norm_music_name(album):
        queries.append(f"album:{bare_album} artist:{artist}")
    queries.append(f"{bare_album} {artist}".strip())

    wanted = _norm_music_name(bare_album)

    for query in queries:
        for item in await _spotify_search(query, access_token):
            url = item.get("external_urls", {}).get("spotify", "")
            found_album = item.get("name", "")
            if not url or not found_album:
                continue

            # Free-text queries match loosely — keep only same-title albums.
            found = _norm_music_name(found_album)
            if wanted and found != wanted and wanted not in found and found not in wanted:
                continue

            found_artist = ", ".join(
                a.get("name", "") for a in item.get("artists", []) if a.get("name")
            ) or artist
            logger.info(f"✓ Found Spotify album: '{found_album}' by {found_artist}")
            return {"url": url, "album": found_album, "artist": found_artist}

    logger.debug(f"⊘ Album not found on Spotify: '{album}' by {artist}")
    return None


async def _spotify_validate_credentials() -> bool:
    """Test if Spotify credentials are valid. Returns True if OK."""
    try:
        token = await _spotify_get_access_token()
        if token:
            logger.info("✓ Spotify credentials validated successfully")
            return True
        else:
            logger.warning("⚠️  Spotify credentials invalid or missing")
            return False
    except Exception as e:
        logger.error(f"💥 Spotify validation error: {type(e).__name__}")
        return False


async def _recommend_music_album(
    user_id: int = 71488343, access_token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Recommend a morning album via GPT, retrying when Spotify has no match.

    Each attempt rolls a fresh genre/period and tells GPT which picks already
    failed, so a hallucinated album/artist pair costs one retry instead of the
    whole section.
    """
    if not access_token:
        access_token = await _spotify_get_access_token()
    if not access_token:
        return None

    failed: List[str] = []

    for attempt in range(1, ALBUM_MAX_ATTEMPTS + 1):
        result = await _recommend_music_album_once(
            user_id=user_id, access_token=access_token, failed=failed, attempt=attempt
        )
        if result:
            return result

    logger.warning(f"⊘ No album found on Spotify after {ALBUM_MAX_ATTEMPTS} attempts")
    return None


async def _recommend_music_album_once(
    user_id: int,
    access_token: str,
    failed: List[str],
    attempt: int,
) -> Optional[Dict[str, Any]]:
    """One GPT pick + Spotify lookup. Appends a rejected pick to `failed`."""
    import random

    try:
        client = get_client()

        # Рандомизация: жанр + период
        genres = [
            "ambient", "lo-fi", "jazz", "post-rock", "classical",
            "synthwave", "drone", "deep house", "neo-classical",
            "folk", "indie", "progressive rock"
        ]
        periods = [
            "70х годов", "80х годов", "90х годов",
            "2000х годов", "2010х годов", "современные"
        ]

        random_genre = random.choice(genres)
        random_period = random.choice(periods)

        logger.debug(f"🎲 Random selection (attempt {attempt}): {random_genre} из {random_period}")

        # Exclude albums sent to this user in the last 90 days so nothing repeats.
        # A history read failure must not cost us the recommendation (and with
        # retries it would otherwise burn every attempt on the same error).
        try:
            shown_albums = await get_shown_keys(user_id, "album")
        except Exception as e:
            logger.warning(f"Could not read album history: {type(e).__name__}: {e}")
            shown_albums = []
        avoid_block = ""
        if shown_albums:
            joined = "\n".join(f"- {a}" for a in shown_albums)
            avoid_block = (
                "\n\nНЕ рекомендуй эти альбомы (они уже были за последние 90 дней) "
                "и ничего из этого списка:\n" + joined
            )
        if failed:
            joined = "\n".join(f"- {a}" for a in failed)
            avoid_block += (
                "\n\nЭтих альбомов нет на Spotify под указанным исполнителем — "
                "не предлагай их снова и внимательно проверь авторство:\n" + joined
            )

        prompt = f"""Посоветуй один реальный и известный музыкальный альбом жанра {random_genre} из {random_period} для утренней концентрации.
Не генерируй новые альбомы, рекомендуй только существующие произведения.
Убедись, что альбом действительно выпущен указанным исполнителем и есть на Spotify.{avoid_block}

Описание пиши как рекомендацию: чем альбом хорош. Не пиши, что он не подходит, и не извиняйся.

Ответь только JSON без markdown:
{{
  "album": "<название альбома>",
  "artist": "<имя исполнителя>",
  "description": "<краткое описание, 1-2 предложения, макс 150 символов>"
}}"""

        try:
            response = await client.chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.error(f"💥 GPT album recommendation error: {type(e).__name__}: {str(e)[:100]}")
            return None

        try:
            response_text = response.choices[0].message.content.strip()
            recommendation = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"💥 Invalid JSON from GPT: {str(e)[:100]}")
            logger.debug(f"Response was: {response_text[:200]}")
            return None

        album = recommendation.get("album", "").strip()
        artist = recommendation.get("artist", "").strip()
        description = recommendation.get("description", "").strip()

        if not album or not artist:
            logger.warning(f"⚠️  Incomplete album recommendation: album='{album}', artist='{artist}'")
            return None

        logger.info(f"🎶 GPT recommended (attempt {attempt}): '{album}' by {artist}")

        found = await _spotify_search_album(album, artist, access_token)

        if not found:
            logger.warning(
                f"⊘ Album not found on Spotify (attempt {attempt}/{ALBUM_MAX_ATTEMPTS}): "
                f"'{album}' by {artist}"
            )
            failed.append(f"{artist} — {album}")
            return None

        # Prefer Spotify's own spelling — that's what the link actually opens.
        album, artist = found["album"], found["artist"]

        result = {
            "type": "music",
            "title": album,
            "creator": artist,
            "url": found["url"],
            "review": _sanitize_review(description, {}),
            "language": "ru",
            "platform": "spotify",
        }

        # Record so this exact album is excluded from future recommendations.
        try:
            await record_shown_content(user_id, f"{artist} — {album}", "album")
        except Exception as e:
            logger.warning(f"Could not record shown album: {type(e).__name__}: {e}")

        logger.info(f"✓ Album of day: {album} by {artist} ({random_genre} из {random_period})")
        return result

    except Exception as e:
        logger.error(f"💥 Music recommendation error: {type(e).__name__}: {str(e)[:150]}")
        return None


async def get_themed_podcast(
    interests: str, hours: int = 168, user_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Pick a podcast episode matching `interests` (EN + RU, last `hours`).

    Used for users with a themed content profile (Маша/Юля). Uses a wider time
    window than the default 24h since podcasts don't publish daily. Returns None
    if no episodes are available so the caller can fall back to a music album.

    To avoid always recommending the same best-matching podcast (e.g. Arzamas),
    podcasts shown to this user in the last few runs are excluded from the pool
    when other options exist.
    """
    try:
        en, ru = await asyncio.gather(
            get_podcasts(language="en", max_results=15, hours=hours),
            get_russian_podcasts(max_results=15, hours=hours),
            return_exceptions=True,
        )
        items: List[Dict[str, Any]] = []
        if isinstance(ru, list):
            items.extend(ru)
        if isinstance(en, list):
            items.extend(en)

        if not items:
            logger.info("No fresh podcasts available for themed selection")
            return None

        # Hard rule: an episode already sent to this user is never sent again
        # within the history window (90 days).
        shown_urls = await _shown_item_urls(user_id)
        if shown_urls:
            fresh = [it for it in items if (it.get("url") or "") not in shown_urls]
            if len(fresh) < len(items):
                logger.info(f"Themed podcast: dropped {len(items) - len(fresh)} already-sent episodes")
            items = fresh
        if not items:
            logger.info("All podcast episodes already sent to this user, skipping")
            return None

        # Prefer creators the user hasn't heard yet; fall back to the full pool
        # if that would leave nothing (a new episode of a known podcast is fine).
        shown = await get_shown_creators(user_id, "podcast") if user_id else []
        pool = [it for it in items if it.get("creator") not in shown] or items
        if shown and len(pool) < len(items):
            logger.info(f"Themed podcast: excluded {len(items) - len(pool)} already-shown creators")

        logger.info(f"Themed podcast pool: {len(pool)} episodes; selecting for interests")
        result = await _select_and_describe(pool, interests=interests)

        # Remember the episode (90 days) and its creator so nothing repeats.
        if result and user_id:
            await _record_shown_recommendation(user_id, result)
            creator = result.get("creator", "")
            if creator:
                await record_shown_content(user_id, creator, "podcast")

        return result

    except Exception as e:
        logger.warning(f"Themed podcast selection failed: {type(e).__name__}: {e}")
        return None


async def get_content_recommendation_with_review(user_id: int = 71488343) -> Optional[Dict[str, Any]]:
    """
    Main function: fetch fresh content (last 24h), have GPT select it.
    Fallback to music album recommendation if no fresh content found.

    Users with a themed content profile (CONTENT_PROFILES, e.g. Маша/Юля) get a
    podcast matching their interests instead of the default analyst mix.

    Returns:
        {
            "type": "video|podcast|music",
            "title": str,
            "creator": str,
            "url": str,
            "review": str (Russian review from AI),
            "language": "ru|en",
            "platform": str,
        }
        or None if unavailable
    """
    try:
        # Themed-podcast users (e.g. Маша/Юля): pick a podcast on their topics
        profile = CONTENT_PROFILES.get(user_id)
        if profile and profile.get("podcast_only"):
            logger.info(f"User {user_id}: themed podcast recommendation")
            themed = await get_themed_podcast(profile["interests"], user_id=user_id)
            if themed:
                return themed
            logger.info("No themed podcast found, falling back to music album")
            return await _recommend_music_album(user_id=user_id)

        # Everything already sent to this user in the last 90 days is excluded.
        shown_urls = await _shown_item_urls(user_id)

        def _unseen(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            fresh = [it for it in items if (it.get("url") or "") not in shown_urls]
            if len(fresh) < len(items):
                logger.info(f"Dropped {len(items) - len(fresh)} already-sent items")
            return fresh

        # Default: fetch fresh content (last 24 hours)
        fresh_items = _unseen(await fetch_fresh_content(hours=24))

        if fresh_items:
            logger.info(f"✓ Found {len(fresh_items)} fresh items, selecting best...")
            result = await _select_and_describe(fresh_items)
            if result:
                await _record_shown_recommendation(user_id, result)
                return result
            else:
                logger.debug("No item selected by GPT")

        # Nothing fresh in 24h: podcasts/channels rarely publish daily, so widen the
        # window to a week and prefer a real podcast/video before dropping to a music
        # album (the themed-podcast path already uses 168h for the same reason).
        logger.info("No content in 24h window, widening to last 7 days for podcasts/videos...")
        weekly_items = _unseen(await fetch_fresh_content(hours=168))
        if weekly_items:
            logger.info(f"✓ Found {len(weekly_items)} items in 7-day window, selecting best...")
            result = await _select_and_describe(weekly_items)
            if result:
                await _record_shown_recommendation(user_id, result)
                return result

        # Fallback: recommend music album
        logger.info("⚠️  No fresh content found, recommending music album...")
        result = await _recommend_music_album(user_id=user_id)
        return result

    except Exception as e:
        logger.error(f"💥 Content recommendation error: {type(e).__name__}: {str(e)[:150]}")
        return None


async def get_album_of_day(user_id: int = 71488343) -> Optional[Dict[str, Any]]:
    """
    Get today's music album recommendation via GPT + Spotify.

    Returns:
        {
            "type": "music",
            "title": str (album name),
            "creator": str (artist),
            "url": str (Spotify link),
            "review": str (Russian description),
            "platform": "spotify",
        }
        or None if unavailable
    """
    try:
        logger.info("🎵 Getting album of the day...")

        # Get Spotify token once
        access_token = await _spotify_get_access_token()

        # Get album recommendation
        result = await _recommend_music_album(user_id=user_id, access_token=access_token)

        if result and result.get('title') and result.get('creator'):
            logger.info(f"✓ Album of day: {result.get('title')} by {result.get('creator')}")
            return result
        else:
            logger.warning("⊘ Could not get album of the day")
            return None

    except Exception as e:
        logger.error(f"💥 Album of day error: {type(e).__name__}: {str(e)[:150]}")
        return None
