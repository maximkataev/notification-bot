"""Parse real content sources: YouTube, podcasts RSS, Spotify, etc.

Returns actual video/podcast/music items with real working links.
No hardcoding - only real content from APIs and RSS feeds.
AI selects fresh content and writes review in Russian.
"""

import logging
import httpx
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import feedparser
import re
import json
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Real content sources (channels, playlists, podcasts)
# YouTube channels with both ID (for fetching) and channel URL (for display)
YOUTUBE_CHANNELS = {
    # English channels
    "videos_educational": [
        {"id": "UCsooa4yRKGN_zEE8iknghZA", "name": "TED-Ed", "url": "https://www.youtube.com/@TEDed"},
        {"id": "UCAuUUnT6oDeKwE6v1NGQxug", "name": "TED", "url": "https://www.youtube.com/@TED"},
        {"id": "UCHnyfMqiRRG1u-2MsSQLbXA", "name": "Veritasium", "url": "https://www.youtube.com/@veritasium"},
        {"id": "UCYO_jab_esuFRV4b17AJtAw", "name": "3Blue1Brown", "url": "https://www.youtube.com/@3blue1brown"},
        {"id": "UCX6b17PVsYBQ0ip5gyeme-Q", "name": "Crash Course", "url": "https://www.youtube.com/@crashcourse"},
        {"id": "UC9-y-6csu5mg-rbJ7_TcQAA", "name": "Computerphile", "url": "https://www.youtube.com/@Computerphile"},
        {"id": "UCsXVk37bltHxD1rDPwtNM8Q", "name": "Kurzgesagt", "url": "https://www.youtube.com/@kurzgesagt"},
        {"id": "UC2D2CMWXMOVWx7giW1n3LIg", "name": "Huberman Lab", "url": "https://www.youtube.com/@hubermanlab"},
        {"id": "UCSHZKyawb77ixDdsGog4iWA", "name": "Lex Fridman", "url": "https://www.youtube.com/@lexfridman"},
    ],
    "videos_productivity": [
        {"id": "UCoOae5nYA7VqaXzerajD0lg", "name": "Ali Abdaal", "url": "https://www.youtube.com/@aliabdaal"},
        {"id": "UCG-KntY7aVnIGXYEBQvmBAQ", "name": "Thomas Frank", "url": "https://www.youtube.com/@thomasfrank"},
        {"id": "UCJ24N4O0bP7LGLBDvye7oCA", "name": "Matt D'Avella", "url": "https://www.youtube.com/@mattdavella"},
        {"id": "UC9vLsnF6QPYuH51njmIooCQ", "name": "System Design Interview", "url": "https://www.youtube.com/@SystemDesignInterview"},
        {"id": "UC8butISFwT-Wl7EV0hUK0BQ", "name": "freeCodeCamp", "url": "https://www.youtube.com/@freecodecamp"},
    ],
    "videos_tech": [
        {"id": "UCbfYPyITQ-7l4upoX8nvctg", "name": "Fireship", "url": "https://www.youtube.com/@fireship"},
        {"id": "UCCezIgC97PvUuR4_gbFUs5g", "name": "Corey Schafer", "url": "https://www.youtube.com/@coreyms"},
        {"id": "UCW5YeuERMmlnqo4oq8vwUpg", "name": "The Net Ninja", "url": "https://www.youtube.com/@NetNinja"},
        {"id": "UCsBjURrPoezykLs9EqgamOA", "name": "Ben Awad", "url": "https://www.youtube.com/@benawad"},
    ],
    # Russian channels
    "videos_ru_documentary": [
        {"id": "UCpHYYe5wzme6XJfYQbM8-_Q", "name": "Простые мысли", "url": "https://www.youtube.com/@simple_thoughts"},
        {"id": "UC4q1jrIeAOLh7Jw7YazqPWQ", "name": "Файб", "url": "https://www.youtube.com/@pheeb_official"},
        {"id": "UC0oLxL8yFsI6KyXdDgnJi4g", "name": "SUREN", "url": "https://www.youtube.com/@surenart"},
    ],
    "videos_ru_science": [
        {"id": "UC5f5IV0Bf79YLp_p9nfInRA", "name": "SciOne", "url": "https://www.youtube.com/@scione"},
        {"id": "UC3Mss4t8lN4qUQ9-7Y0Q1nA", "name": "Мы и Они", "url": "https://www.youtube.com/@myandthey"},
        {"id": "UC6uFo0i20oRjv4jM6Vn0Y6A", "name": "Основа", "url": "https://www.youtube.com/@Osnova"},
    ],
    "videos_ru_society": [
        {"id": "UC3bbYb7N7o2dC6Fsl9M6m2Q", "name": "Жиза", "url": "https://www.youtube.com/@zhiza"},
        {"id": "UCW7sU3D8R8b8TnLq4v9P8bw", "name": "Черный кабинет", "url": "https://www.youtube.com/@blackcabinetyt"},
    ],
    "videos_ru_travel": [
        {"id": "UCm0x7wraT70xW4K8v3a3d7Q", "name": "Хочу домой", "url": "https://www.youtube.com/@khochudomoy"},
    ],
    "videos_ru_food": [
        {"id": "UC5m6D8V7kW9f8tY1j3n6kPQ", "name": "Покашеварим", "url": "https://www.youtube.com/@pokashevarim"},
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


async def _fetch_single_youtube_channel(channel: Dict) -> Optional[Dict[str, Any]]:
    """Fetch a single YouTube channel (for parallel execution)."""
    try:
        channel_id = channel["id"]
        channel_name = channel["name"]
        channel_url = channel["url"]
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.entries:
            entry = feed.entries[0]
            video = {
                "title": channel_name,
                "creator": channel_name,
                "url": channel_url,
                "description": entry.get("summary", "")[:150],
                "type": "video",
                "platform": "youtube",
                "published": entry.get("published", ""),
            }
            if video["title"] and video["url"]:
                return video
    except Exception as e:
        logger.debug(f"Failed to fetch YouTube channel {channel.get('name', 'unknown')}: {type(e).__name__}")
    return None


async def get_youtube_videos(max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch recent videos from English YouTube channels (parallel).
    Returns links to channel pages, not individual videos.

    Args:
        max_results: max videos to return

    Returns:
        List of video dicts with title, creator, channel_url, description
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
        tasks = [_fetch_single_youtube_channel(ch) for ch in all_channels]
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
        videos = [
            r for r in results
            if r and not isinstance(r, Exception)
        ]

        return videos[:max_results]

    except Exception as e:
        logger.warning(f"Failed to fetch YouTube videos: {type(e).__name__}: {e}")
        return []


async def _fetch_single_podcast(source: Dict) -> Optional[Dict[str, Any]]:
    """Fetch a single podcast source (for parallel execution)."""
    try:
        rss_url = source.get("rss_url") or source.get("url")
        channel_url = source.get("channel_url")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.entries:
            entry = feed.entries[0]
            podcast = {
                "title": source.get("title", feed.feed.get("title", "Podcast")),
                "creator": source.get("title", feed.feed.get("title", "Podcast")),
                "url": channel_url or entry.get("link", ""),
                "description": entry.get("summary", "")[:150],
                "type": "podcast",
                "platform": "podcast",
                "published": entry.get("published", ""),
            }
            if podcast["title"] and podcast["url"]:
                return podcast
    except Exception as e:
        logger.debug(f"Failed to fetch podcast {source.get('title', 'unknown')}: {type(e).__name__}")
    return None


async def get_podcasts(
    language: str = "en", max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Fetch recent podcast episodes from RSS feeds (parallel).

    Args:
        language: 'en', 'ru', or 'all'
        max_results: max episodes to return

    Returns:
        List of podcast dicts with title, creator, url, description
    """
    try:
        sources = [
            s
            for s in PODCAST_SOURCES
            if language == "all" or s.get("language") == language
        ]

        # Fetch all podcasts in parallel with timeout
        tasks = [_fetch_single_podcast(s) for s in sources]
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
        podcasts = [
            r for r in results
            if r and not isinstance(r, Exception)
        ]

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


async def _fetch_single_russian_youtube_channel(channel: Dict) -> Optional[Dict[str, Any]]:
    """Fetch a single Russian YouTube channel (for parallel execution)."""
    try:
        channel_id = channel["id"]
        channel_name = channel["name"]
        channel_url = channel["url"]
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.entries:
            entry = feed.entries[0]
            video = {
                "title": channel_name,
                "creator": channel_name,
                "url": channel_url,
                "description": entry.get("summary", "")[:150],
                "type": "video",
                "platform": "youtube",
                "language": "ru",
                "published": entry.get("published", ""),
            }
            if video["title"] and video["url"]:
                return video
    except Exception as e:
        logger.debug(f"Failed to fetch Russian YouTube {channel.get('name', 'unknown')}: {type(e).__name__}")
    return None


async def get_russian_youtube_videos(max_results: int = 3) -> List[Dict[str, Any]]:
    """Fetch recent videos from Russian YouTube channels (parallel).
    Returns links to channel pages, not individual videos."""
    try:
        # Filter Russian channels from unified YOUTUBE_CHANNELS
        ru_categories = {
            k: v for k, v in YOUTUBE_CHANNELS.items() if k.startswith("videos_ru")
        }
        all_channels = []
        for channels_list in ru_categories.values():
            all_channels.extend(channels_list)

        # Fetch all channels in parallel with timeout
        tasks = [_fetch_single_russian_youtube_channel(ch) for ch in all_channels]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(8.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=8.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Russian YouTube videos fetch timed out after 8s")
            results = []

        # Filter out None and Exception results
        videos = [
            r for r in results
            if r and not isinstance(r, Exception)
        ]

        return videos[:max_results]
    except Exception as e:
        logger.warning(
            f"Failed to fetch Russian YouTube videos: {type(e).__name__}: {e}"
        )
        return []


async def _fetch_single_russian_podcast(source: Dict) -> Optional[Dict[str, Any]]:
    """Fetch a single Russian podcast source (for parallel execution)."""
    try:
        rss_url = source.get("rss_url") or source.get("url")
        channel_url = source.get("channel_url")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(rss_url)
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        if feed.entries:
            entry = feed.entries[0]
            podcast = {
                "title": source.get("title", feed.feed.get("title", "Podcast")),
                "creator": source.get("title", "Podcast"),
                "url": channel_url or entry.get("link", ""),
                "description": entry.get("summary", "")[:150],
                "type": "podcast",
                "platform": "podcast",
                "language": "ru",
                "published": entry.get("published", ""),
            }
            if podcast["title"] and podcast["url"]:
                return podcast
    except Exception as e:
        logger.debug(f"Failed to fetch Russian podcast {source.get('title', 'unknown')}: {type(e).__name__}")
    return None


async def get_russian_podcasts(max_results: int = 3) -> List[Dict[str, Any]]:
    """Fetch recent episodes from Russian podcasts (parallel)."""
    try:
        ru_sources = [s for s in PODCAST_SOURCES if s.get("language") == "ru"]

        # Fetch all Russian podcasts in parallel with timeout
        tasks = [_fetch_single_russian_podcast(s) for s in ru_sources]
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(8.0):
                    results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=8.0
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Russian podcasts fetch timed out after 8s")
            results = []

        # Filter out None and Exception results
        podcasts = [
            r for r in results
            if r and not isinstance(r, Exception)
        ]

        return podcasts[:max_results]
    except Exception as e:
        logger.warning(f"Failed to fetch Russian podcasts: {type(e).__name__}: {e}")
        return []


async def get_all_content(max_per_type: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch ALL content sources (English + Russian) in parallel with timeout.
    Returns flat list with all items, prioritizing Russian.

    Returns:
        List of content dicts with title, creator, url, description, language
    """
    try:
        logger.info("Fetching all content sources (EN + RU) in parallel...")

        # Fetch all sources in parallel with 15-second timeout
        try:
            if hasattr(asyncio, "timeout"):
                async with asyncio.timeout(15.0):
                    en_videos, en_podcasts, music, ru_videos, ru_podcasts = await asyncio.gather(
                        get_youtube_videos(max_results=max_per_type),
                        get_podcasts(language="en", max_results=max_per_type),
                        get_music(max_results=max_per_type),
                        get_russian_youtube_videos(max_results=max_per_type),
                        get_russian_podcasts(max_results=max_per_type),
                        return_exceptions=True,
                    )
            else:
                en_videos, en_podcasts, music, ru_videos, ru_podcasts = await asyncio.wait_for(
                    asyncio.gather(
                        get_youtube_videos(max_results=max_per_type),
                        get_podcasts(language="en", max_results=max_per_type),
                        get_music(max_results=max_per_type),
                        get_russian_youtube_videos(max_results=max_per_type),
                        get_russian_podcasts(max_results=max_per_type),
                        return_exceptions=True,
                    ),
                    timeout=15.0,
                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("Content sources fetch timed out after 15s, returning partial results")
            en_videos = en_podcasts = music = ru_videos = ru_podcasts = []

        # Handle exceptions
        for var_name, var in [
            ("videos_en", en_videos),
            ("podcasts_en", en_podcasts),
            ("music", music),
            ("videos_ru", ru_videos),
            ("podcasts_ru", ru_podcasts),
        ]:
            if isinstance(var, Exception):
                logger.warning(f"Failed to fetch {var_name}: {var}")

        # Combine into flat list, prioritizing Russian content
        all_content = []

        # Add Russian first (priority)
        all_content.extend(ru_videos if isinstance(ru_videos, list) else [])
        all_content.extend(ru_podcasts if isinstance(ru_podcasts, list) else [])

        # Then English
        all_content.extend(en_videos if isinstance(en_videos, list) else [])
        all_content.extend(en_podcasts if isinstance(en_podcasts, list) else [])
        all_content.extend(music if isinstance(music, list) else [])

        # Add language tag if missing
        for item in all_content:
            if "language" not in item:
                item["language"] = "en"

        logger.info(
            f"✓ Fetched {len(all_content)} total items (RU: {len(ru_videos or [])} videos + {len(ru_podcasts or [])} podcasts)"
        )

        return all_content

    except Exception as e:
        logger.error(f"Failed to fetch all content: {type(e).__name__}: {e}")
        return []


async def get_content_recommendation_with_review() -> Optional[Dict[str, Any]]:
    """
    Fetch all content, use AI to select fresh item, write review in Russian.
    Prioritizes Russian content.

    Returns:
        {
            "type": "video|podcast|music",
            "title": str,
            "creator": str,
            "url": str,
            "description": str,
            "review": str (Russian review from AI),
            "language": "ru|en",
            "platform": str,
        }
        or None if no content available
    """
    try:
        # Fetch all available content
        all_content = await get_all_content(max_per_type=5)
        if not all_content:
            logger.warning("No content available for recommendation")
            return None

        # Prepare content list for AI (include key fields)
        content_list = []
        for idx, item in enumerate(all_content[:20], 1):  # Limit to 20 items
            content_list.append(
                {
                    "index": idx,
                    "type": item.get("type", "unknown"),
                    "title": item.get("title", ""),
                    "creator": item.get("creator", ""),
                    "description": item.get("description", ""),
                    "language": item.get("language", "en"),
                }
            )

        logger.debug(f"Prepared {len(content_list)} items for AI selection")

        # Send to GPT-4o for selection
        client = get_client()
        prompt = f"""У тебя есть список свежего контента. Выбери ОДИН наиболее интересный и полезный элемент, приоритет - русский контент.

Контент:
{json.dumps(content_list, ensure_ascii=False, indent=2)}

Ответь JSON (только валидный JSON без markdown):
{{
  "index": <номер выбранного элемента>,
  "review": "<твой краткий обзор на русском (1-3 предложения, макс 150 символов)>"
}}

Обзор должен быть:
- На русском языке
- Кратким и полезным
- Объяснять, почему это стоит смотреть/слушать"""

        response = await client.chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.choices[0].message.content.strip()
        logger.debug(f"AI selection response: {response_text}")

        # Parse JSON response
        selected = json.loads(response_text)
        selected_idx = selected.get("index", 1) - 1  # Convert to 0-indexed
        review = selected.get("review", "")

        if 0 <= selected_idx < len(all_content):
            item = all_content[selected_idx]
            result = {
                "type": item.get("type", "unknown"),
                "title": item.get("title", ""),
                "creator": item.get("creator", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "review": review,
                "language": item.get("language", "en"),
                "platform": item.get("platform", ""),
            }

            logger.info(f"✓ Selected: {result['type']} - {result['title'][:50]}")
            return result
        else:
            logger.warning(f"Invalid index from AI: {selected_idx}")
            return None

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to get content recommendation: {type(e).__name__}: {e}")
        return None
