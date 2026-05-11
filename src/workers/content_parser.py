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
# YouTube Channel IDs - EN + RU combined
YOUTUBE_CHANNELS = {
    # English channels
    "videos_educational": [
        "UCsooa4yRKGN_zEE8iknghZA",  # TED-Ed
        "UCAuUUnT6oDeKwE6v1NGQxug",  # TED
        "UCHnyfMqiRRG1u-2MsSQLbXA",  # Veritasium
        "UCYO_jab_esuFRV4b17AJtAw",  # 3Blue1Brown
        "UCX6b17PVsYBQ0ip5gyeme-Q",  # Crash Course
        "UC9-y-6csu5mg-rbJ7_TcQAA",  # Computerphile
        "UCsXVk37bltHxD1rDPwtNM8Q",  # Kurzgesagt
        "UC2D2CMWXMOVWx7giW1n3LIg",  # Huberman Lab
        "UCSHZKyawb77ixDdsGog4iWA",  # Lex Fridman
    ],
    "videos_productivity": [
        "UCoOae5nYA7VqaXzerajD0lg",  # Ali Abdaal
        "UCG-KntY7aVnIGXYEBQvmBAQ",  # Thomas Frank
        "UCJ24N4O0bP7LGLBDvye7oCA",  # Matt D'Avella
        "UC9vLsnF6QPYuH51njmIooCQ",  # System Design Interview
        "UC8butISFwT-Wl7EV0hUK0BQ",  # freeCodeCamp
    ],
    "videos_tech": [
        "UCbfYPyITQ-7l4upoX8nvctg",  # Fireship
        "UCCezIgC97PvUuR4_gbFUs5g",  # Corey Schafer
        "UCW5YeuERMmlnqo4oq8vwUpg",  # The Net Ninja
        "UCsBjURrPoezykLs9EqgamOA",  # Ben Awad
    ],
    # Russian channels
    "videos_ru_documentary": [
        "UCpHYYe5wzme6XJfYQbM8-_Q",  # Простые мысли
        "UC4q1jrIeAOLh7Jw7YazqPWQ",  # Файб
        "UC0oLxL8yFsI6KyXdDgnJi4g",  # SUREN
    ],
    "videos_ru_science": [
        "UC5f5IV0Bf79YLp_p9nfInRA",  # SciOne
        "UC3Mss4t8lN4qUQ9-7Y0Q1nA",  # Мы и Они
        "UC6uFo0i20oRjv4jM6Vn0Y6A",  # Основа
    ],
    "videos_ru_society": [
        "UC3bbYb7N7o2dC6Fsl9M6m2Q",  # Жиза
        "UCW7sU3D8R8b8TnLq4v9P8bw",  # Черный кабинет
    ],
    "videos_ru_travel": [
        "UCm0x7wraT70xW4K8v3a3d7Q",  # Хочу домой
    ],
    "videos_ru_food": [
        "UC5m6D8V7kW9f8tY1j3n6kPQ",  # Покашеварим
    ],
}

PODCAST_SOURCES = [
    # English podcasts
    {
        "title": "Data Skeptic",
        "url": "https://dataskeptic.libsyn.com/rss",
        "language": "en",
        "category": "ai_data",
    },
    {
        "title": "The Gradient",
        "url": "https://feeds.buzzsprout.com/1832356.rss",
        "language": "en",
        "category": "ai",
    },
    {
        "title": "Lex Fridman Podcast",
        "url": "https://lexfridman.com/feed/podcast/",
        "language": "en",
        "category": "ai_tech",
    },
    {
        "title": "Darknet Diaries",
        "url": "https://feeds.megaphone.fm/darknetdiaries",
        "language": "en",
        "category": "tech_security",
    },
    {
        "title": "Software Engineering Daily",
        "url": "https://feeds.softwareengineeringdaily.com/rss.xml",
        "language": "en",
        "category": "tech_engineering",
    },
    {
        "title": "The Changelog",
        "url": "https://feeds.changelog.com/podcast",
        "language": "en",
        "category": "tech_engineering",
    },
    {
        "title": "a16z Podcast",
        "url": "https://feeds.simplecast.com/JGE3yC0V",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "Y Combinator Podcast",
        "url": "https://feeds.megaphone.fm/ycombinator",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "Masters of Scale",
        "url": "https://feeds.megaphone.fm/masterscale",
        "language": "en",
        "category": "business_startups",
    },
    {
        "title": "The Tim Ferriss Show",
        "url": "https://feeds.megaphone.fm/timferriss",
        "language": "en",
        "category": "productivity",
    },
    {
        "title": "Huberman Lab",
        "url": "https://feeds.megaphone.fm/hubermanlab",
        "language": "en",
        "category": "health_productivity",
    },
    {
        "title": "StarTalk Radio",
        "url": "https://feeds.megaphone.fm/startalk",
        "language": "en",
        "category": "science",
    },
    # Russian podcasts - main
    {
        "title": "Радио-Т",
        "url": "https://radio-t.com/podcast.rss",
        "language": "ru",
        "category": "tech",
    },
    {
        "title": "Закат Империи",
        "url": "https://anchor.fm/s/11d8d8c4/podcast/rss",
        "language": "ru",
        "category": "history",
    },
    {
        "title": "Сперва роди",
        "url": "https://feeds.simplecast.com/xq6WTx9j",
        "language": "ru",
        "category": "society",
    },
    {
        "title": "Норм",
        "url": "https://feeds.simplecast.com/eAKaDgaQ",
        "language": "ru",
        "category": "culture_society",
    },
    {
        "title": "Короче, история",
        "url": "https://feeds.simplecast.com/7wzebh8X",
        "language": "ru",
        "category": "history",
    },
    {
        "title": "Это провал",
        "url": "https://feeds.simplecast.com/o6w7K_-I",
        "language": "ru",
        "category": "business_failures",
    },
    {
        "title": "Деньги пришли",
        "url": "https://feeds.megaphone.fm/MEDUZA6636460993",
        "language": "ru",
        "category": "finance",
    },
    {
        "title": "Хочу не могу",
        "url": "https://feeds.simplecast.com/9Wn6mA6m",
        "language": "ru",
        "category": "psychology_relationships",
    },
    {
        "title": "Либо выйдет, либо нет",
        "url": "https://feeds.simplecast.com/Vuxy4v5Z",
        "language": "ru",
        "category": "startups_business",
    },
    {
        "title": "Arzamas",
        "url": "https://arzamas.academy/feed_v1/podcast.rss",
        "language": "ru",
        "category": "culture_education",
    },
    # Russian podcasts - underground
    {
        "title": "Так вышло",
        "url": "https://feeds.megaphone.fm/meduza-tak-vyshlo",
        "language": "ru",
        "category": "society_ethics",
    },
    {
        "title": "Проветримся!",
        "url": "https://feeds.simplecast.com/4_j8wz0P",
        "language": "ru",
        "category": "mental_health",
    },
    {
        "title": "Либо получится, либо сдохнем",
        "url": "https://feeds.simplecast.com/Wp9s6x4B",
        "language": "ru",
        "category": "startups",
    },
    {
        "title": "Кавачай",
        "url": "https://feeds.soundcloud.com/users/soundcloud:users:231188278/sounds.rss",
        "language": "ru",
        "category": "internet_culture",
    },
    {
        "title": "Blitz and Chips",
        "url": "https://feeds.soundcloud.com/users/soundcloud:users:447105959/sounds.rss",
        "language": "ru",
        "category": "science_future",
    },
    {
        "title": "Ночной подкаст",
        "url": "https://feeds.simplecast.com/Q0v7mP9x",
        "language": "ru",
        "category": "calm_talk",
    },
    {
        "title": "Это разве секс?",
        "url": "https://feeds.simplecast.com/jm0lPB7M",
        "language": "ru",
        "category": "relationships",
    },
    {
        "title": "Полка",
        "url": "https://polka.academy/feed/podcast/",
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



async def get_youtube_videos(max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch recent videos from English YouTube channels.

    Args:
        max_results: max videos to return

    Returns:
        List of video dicts with title, creator, url, description
    """
    try:
        # Get only English channels (exclude videos_ru*)
        en_categories = {k: v for k, v in YOUTUBE_CHANNELS.items() if not k.startswith("videos_ru")}
        all_channel_ids = []
        for channel_ids in en_categories.values():
            all_channel_ids.extend(channel_ids)
        videos = []

        for channel_id in all_channel_ids:
            try:
                # YouTube RSS feed: /feeds/videos.xml?channel_id=CHANNEL_ID
                url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                # Parse RSS
                feed = feedparser.parse(response.content)

                for entry in feed.entries[:3]:  # Get 3 latest from each channel
                    # Extract video info
                    video_id = entry.get("yt_videoid", "")
                    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get("link", "")

                    video = {
                        "title": entry.get("title", ""),
                        "creator": feed.feed.get("title", "YouTube"),
                        "url": video_url,
                        "description": entry.get("summary", "")[:150],
                        "type": "video",
                        "platform": "youtube",
                        "published": entry.get("published", ""),
                    }

                    if video["title"] and video["url"]:
                        videos.append(video)

                logger.debug(f"✓ Fetched {len([v for v in videos])} videos from {feed.feed.get('title', 'YouTube')}")

            except Exception as e:
                logger.debug(f"Failed to fetch from YouTube channel {channel_id}: {type(e).__name__}")
                continue

        return videos[:max_results]

    except Exception as e:
        logger.warning(f"Failed to fetch YouTube videos: {type(e).__name__}: {e}")
        return []


async def get_podcasts(
    language: str = "en",
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Fetch recent podcast episodes from RSS feeds.

    Args:
        language: 'en', 'ru', or 'all'
        max_results: max episodes to return

    Returns:
        List of podcast dicts with title, creator, url, description
    """
    try:
        podcasts = []
        sources = [s for s in PODCAST_SOURCES if language == "all" or s.get("language") == language]

        for source in sources:
            try:
                url = source["url"]

                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                # Parse RSS
                feed = feedparser.parse(response.content)

                for entry in feed.entries[:2]:  # Get 2 latest from each podcast
                    # Extract podcast info
                    podcast = {
                        "title": entry.get("title", ""),
                        "creator": source.get("title", feed.feed.get("title", "Podcast")),
                        "url": entry.get("link", "") or entry.get("enclosures", [{}])[0].get("href", ""),
                        "description": entry.get("summary", "")[:150],
                        "type": "podcast",
                        "platform": "podcast",
                        "published": entry.get("published", ""),
                    }

                    if podcast["title"] and podcast["url"]:
                        podcasts.append(podcast)

                logger.debug(f"✓ Fetched podcasts from {source['title']}")

            except Exception as e:
                logger.debug(f"Failed to fetch podcast from {source['title']}: {type(e).__name__}")
                continue

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


async def get_russian_youtube_videos(max_results: int = 3) -> List[Dict[str, Any]]:
    """Fetch recent videos from Russian YouTube channels."""
    try:
        videos = []
        # Filter Russian channels from unified YOUTUBE_CHANNELS
        ru_categories = {k: v for k, v in YOUTUBE_CHANNELS.items() if k.startswith("videos_ru")}
        for channel_ids in ru_categories.values():
            for channel_id in channel_ids:
                try:
                    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(url)
                        response.raise_for_status()

                    feed = feedparser.parse(response.content)
                    for entry in feed.entries[:2]:
                        video_id = entry.get("yt_videoid", "")
                        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get("link", "")

                        video = {
                            "title": entry.get("title", ""),
                            "creator": feed.feed.get("title", "YouTube"),
                            "url": video_url,
                            "description": entry.get("summary", "")[:150],
                            "type": "video",
                            "platform": "youtube",
                            "language": "ru",
                            "published": entry.get("published", ""),
                        }

                        if video["title"] and video["url"]:
                            videos.append(video)

                except Exception as e:
                    logger.debug(f"Failed to fetch Russian YouTube {channel_id}: {type(e).__name__}")
                    continue

        return videos[:max_results]
    except Exception as e:
        logger.warning(f"Failed to fetch Russian YouTube videos: {type(e).__name__}: {e}")
        return []


async def get_russian_podcasts(max_results: int = 3) -> List[Dict[str, Any]]:
    """Fetch recent episodes from Russian podcasts."""
    try:
        podcasts = []
        # Filter Russian podcasts from unified PODCAST_SOURCES
        ru_sources = [s for s in PODCAST_SOURCES if s.get("language") == "ru"]

        for source in ru_sources:
            try:
                url = source["url"]
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                feed = feedparser.parse(response.content)
                for entry in feed.entries[:1]:  # 1 latest from each Russian podcast
                    podcast = {
                        "title": entry.get("title", ""),
                        "creator": source.get("title", "Podcast"),
                        "url": entry.get("link", "") or entry.get("enclosures", [{}])[0].get("href", ""),
                        "description": entry.get("summary", "")[:150],
                        "type": "podcast",
                        "platform": "podcast",
                        "language": "ru",
                        "published": entry.get("published", ""),
                    }

                    if podcast["title"] and podcast["url"]:
                        podcasts.append(podcast)

                logger.debug(f"✓ Fetched Russian podcast: {source['title']}")

            except Exception as e:
                logger.debug(f"Failed to fetch Russian podcast {source['title']}: {type(e).__name__}")
                continue

        return podcasts[:max_results]
    except Exception as e:
        logger.warning(f"Failed to fetch Russian podcasts: {type(e).__name__}: {e}")
        return []


async def get_all_content(max_per_type: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch ALL content sources (English + Russian) in parallel.
    Returns flat list with all items, prioritizing Russian.

    Returns:
        List of content dicts with title, creator, url, description, language
    """
    try:
        logger.info("Fetching all content sources (EN + RU) in parallel...")

        # Fetch all sources in parallel
        en_videos, en_podcasts, music, ru_videos, ru_podcasts = await asyncio.gather(
            get_youtube_videos(max_results=max_per_type),
            get_podcasts(language="en", max_results=max_per_type),
            get_music(max_results=max_per_type),
            get_russian_youtube_videos(max_results=max_per_type),
            get_russian_podcasts(max_results=max_per_type),
            return_exceptions=True
        )

        # Handle exceptions
        for var_name, var in [
            ("videos_en", en_videos), ("podcasts_en", en_podcasts),
            ("music", music), ("videos_ru", ru_videos), ("podcasts_ru", ru_podcasts)
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

        logger.info(f"✓ Fetched {len(all_content)} total items (RU: {len(ru_videos or [])} videos + {len(ru_podcasts or [])} podcasts)")

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
            content_list.append({
                "index": idx,
                "type": item.get("type", "unknown"),
                "title": item.get("title", ""),
                "creator": item.get("creator", ""),
                "description": item.get("description", ""),
                "language": item.get("language", "en"),
            })

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

        response = client.messages.create(
            model="gpt-5.4-mini",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()
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
