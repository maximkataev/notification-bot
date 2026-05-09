"""Recommend interesting content (video, podcast, music) based on user profile and time of day."""
import logging
import random
from typing import Optional, Dict, Any
import re
from datetime import datetime
import httpx
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)

# Try to import yt-dlp for YouTube validation (optional)
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False


async def _check_url_available(url: str, timeout: float = 5.0) -> bool:
    """
    Check if URL is accessible and not geo-restricted.
    For YouTube: uses yt-dlp (most reliable), falls back to httpx.
    For music services: more lenient validation.
    """
    try:
        # Special handling for YouTube videos
        if "youtube.com" in url or "youtu.be" in url:
            if YTDLP_AVAILABLE:
                return _check_youtube_available(url)
            else:
                # Fallback: try to get video info without downloading
                return await _check_youtube_http(url, timeout)

        # For Yandex Music: check that URL structure is valid
        if "music.yandex.ru" in url:
            # Yandex URLs with valid track/album structure
            if any(pattern in url for pattern in ["/track/", "/album/", "/playlist/"]):
                # URL structure looks valid, assume it's accessible
                logger.debug(f"Yandex Music URL structure valid: {url}")
                return True
            else:
                logger.debug(f"Yandex Music URL structure invalid: {url}")
                return False

        # For other URLs: use HTTP check
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.head(url, headers=headers, follow_redirects=True)
                if 200 <= response.status_code < 400:
                    return True
            except Exception:
                pass

            try:
                response = await client.get(url, headers=headers)
                if 200 <= response.status_code < 400:
                    return True
            except Exception:
                pass

        return False
    except Exception as e:
        logger.debug(f"URL check failed for {url}: {type(e).__name__}")
        return False


def _check_youtube_available(url: str) -> bool:
    """Check YouTube video availability using yt-dlp."""
    try:
        logger.debug(f"Checking YouTube video with yt-dlp: {url}")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': 5,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # If we got info, video is available
            return info is not None
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        logger.debug(f"YouTube video unavailable: {error_msg}")
        return False
    except Exception as e:
        logger.debug(f"yt-dlp check failed: {type(e).__name__}: {e}")
        return False


async def _check_youtube_http(url: str, timeout: float = 5.0) -> bool:
    """Fallback: check YouTube video using HTTP requests (less reliable)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)

            if 200 <= response.status_code < 400:
                content = response.text.lower()
                # Check for common YouTube error messages
                error_indicators = [
                    '"simpleText":"Video unavailable"',
                    'video unavailable',
                    'this video is not available',
                    'this video is private',
                    'this video is unavailable in your country',
                    'this video is restricted',
                    '"status":"unplayable"',
                ]

                for indicator in error_indicators:
                    if indicator in content:
                        logger.debug(f"YouTube error detected: {indicator}")
                        return False

                # Also check if we have basic video info (title, etc)
                if '"videoDetails"' in content or '"title"' in content:
                    return True

            return False
    except Exception as e:
        logger.debug(f"HTTP YouTube check failed: {type(e).__name__}")
        return False


# Curated niche content for systems engineer + business analyst + AI enthusiast
CONTENT_RECOMMENDATIONS = {
    "videos_ru": [
        {
            "title": "Как развить мышление роста",
            "creator": "TEDx на русском",
            "description": "Почему вера в свои возможности меняет жизнь и как развить рост вместо фиксированного мышления",
            "url": "https://www.youtube.com/watch?v=_X0mgOOSpLU",
            "type": "video",
        },
        {
            "title": "Привычки успешных людей",
            "creator": "Школа успеха",
            "description": "Истинные привычки инноваторов и успешных предпринимателей",
            "url": "https://www.youtube.com/watch?v=D1R-jKjrlNg",
            "type": "video",
        },
        {
            "title": "Start With Why - Начни с почему",
            "creator": "Simon Sinek (TED)",
            "description": "Почему вдохновляющие лидеры думают, действуют и говорят иначе",
            "url": "https://www.youtube.com/watch?v=sioZd3AxmnE",
            "type": "video",
        },
        {
            "title": "Как побороть прокрастинацию",
            "creator": "TED-Ed",
            "description": "Научный подход к решению проблемы откладывания дел на потом",
            "url": "https://www.youtube.com/watch?v=arj7oStGLkU",
            "type": "video",
        },
        {
            "title": "Продуктивность и тайм-менеджмент",
            "creator": "Лектор Павел",
            "description": "Как организовать свой день и работу с максимальной продуктивностью",
            "url": "https://www.youtube.com/watch?v=2tqk6j-lmlc",
            "type": "video",
        },
        {
            "title": "Как найти свою страсть в жизни",
            "creator": "Дарья Мильаева",
            "description": "Простой и мощный подход к поиску того, что тебя вдохновляет",
            "url": "https://www.youtube.com/watch?v=Ml0HlBxXEMQ",
            "type": "video",
        },
        {
            "title": "Утренние привычки успеха",
            "creator": "Школа жизни",
            "description": "Пошаговое руководство для здорового и продуктивного утра",
            "url": "https://www.youtube.com/watch?v=3cZGsK4E4WQ",
            "type": "video",
        },
        {
            "title": "Талант — это не дар, это навык",
            "creator": "Angela Duckworth (TED)",
            "description": "Почему таланты — это развиваемый навык, а не врождённый дар",
            "url": "https://www.youtube.com/watch?v=H14bBulsSB0",
            "type": "video",
        },
        {
            "title": "Эффект 1% улучшения каждый день",
            "creator": "Лидерство и развитие",
            "description": "Как маленькие изменения каждый день приводят к большим результатам",
            "url": "https://www.youtube.com/watch?v=OAbbIKwfDXA",
            "type": "video",
        },
        {
            "title": "Как вдохновить команду на результаты",
            "creator": "TED на русском",
            "description": "Психология лидерства: как мотивировать себя и других на достижение целей",
            "url": "https://www.youtube.com/watch?v=sioZd3AxmnE",
            "type": "video",
        },
    ],
    "podcasts_ru": [
        {
            "title": "Акценты: истории успеха",
            "creator": "Сергей Кочинов",
            "description": "Вдохновляющие истории предпринимателей, инноваторов и успешных людей",
            "url": "https://www.youtube.com/@accents_podcast",
            "type": "podcast",
        },
        {
            "title": "Как я создал это",
            "creator": "Артур Попов",
            "description": "Истории создателей российских и зарубежных компаний: как всё начиналось",
            "url": "https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf",
            "type": "podcast",
        },
        {
            "title": "Бизнес по Русски",
            "creator": "Олег Тиньков",
            "description": "Интервью с успешными предпринимателями и советы по развитию бизнеса",
            "url": "https://www.youtube.com/playlist?list=PLjDT8-r3SV0UHaKqGqRrk3DkklqXFfnNR",
            "type": "podcast",
        },
        {
            "title": "Мудрость каждый день",
            "creator": "Школа личного развития",
            "description": "Короткие истории про успех, мотивацию и личностный рост",
            "url": "https://www.youtube.com/@wisdomdaily",
            "type": "podcast",
        },
        {
            "title": "Стартапим!",
            "creator": "Александр Смыслов",
            "description": "Интервью со стартапами, инвесторами и лидерами tech-индустрии",
            "url": "https://www.youtube.com/@startupim",
            "type": "podcast",
        },
        {
            "title": "Наука продуктивности",
            "creator": "Лектор Екатерина Слободяник",
            "description": "Научные основы продуктивности: как работает мозг и как его оптимизировать",
            "url": "https://www.youtube.com/playlist?list=PLgXqD6fZF6gKV0TImLJ0yK8vYVVu-sBG4",
            "type": "podcast",
        },
        {
            "title": "Лидер изнутри",
            "creator": "Максим Батырев",
            "description": "О лидерстве, мотивации команды и личном развитии руководителя",
            "url": "https://www.youtube.com/@leaderfrom_inside",
            "type": "podcast",
        },
        {
            "title": "Думай по-новому",
            "creator": "Риккардо Форсалони",
            "description": "Стратегии мышления успешных людей и трансформация убеждений",
            "url": "https://www.youtube.com/@think_new",
            "type": "podcast",
        },
        {
            "title": "Инновация каждый день",
            "creator": "Центр инноваций",
            "description": "О новых идеях, технологиях и том, как они меняют мир",
            "url": "https://www.youtube.com/@innovation_daily",
            "type": "podcast",
        },
        {
            "title": "Успех в фокусе",
            "creator": "Клуб успешных людей",
            "description": "Истории успеха, лайфхаки и стратегии достижения целей",
            "url": "https://www.youtube.com/@successinfocus",
            "type": "podcast",
        },
    ],
    "music": [
        {
            "title": "Lo-Fi Hip Hop — Motivational Beats",
            "creator": "Chillhop Music",
            "description": "Расслабляющие биты для утренней мотивации и фокуса на день",
            "url": "https://www.youtube.com/watch?v=5qap5aO4i9A",
            "type": "music",
        },
        {
            "title": "Morning Energy Mix",
            "creator": "Positive Vibes Café",
            "description": "Легкая, позитивная музыка для бодрого начала дня",
            "url": "https://www.youtube.com/watch?v=W17TkS0Xp5A",
            "type": "music",
        },
        {
            "title": "Peaceful Piano — Deep Concentration",
            "creator": "Peder B. Helland",
            "description": "Классическая музыка на пианино для спокойствия и фокуса",
            "url": "https://www.youtube.com/watch?v=3cZGsK4E4WQ",
            "type": "music",
        },
        {
            "title": "The Cinematic Orchestra — In Motion",
            "creator": "The Cinematic Orchestra",
            "description": "Вдохновляющая инструментальная музыка с ощущением полета",
            "url": "https://www.youtube.com/watch?v=d8tNd0aA_7A",
            "type": "music",
        },
        {
            "title": "Jazz for Morning Motivation",
            "creator": "Smooth Jazz All Day",
            "description": "Легкий джаз для позитивного и энергичного утра",
            "url": "https://www.youtube.com/watch?v=D8G2E_fPqZo",
            "type": "music",
        },
        {
            "title": "Ambient Study Music - Focus",
            "creator": "Relaxing Music Lab",
            "description": "Минималистичная электронная музыка для глубокого погружения в работу",
            "url": "https://www.youtube.com/watch?v=jLhOzGrjDmQ",
            "type": "music",
        },
        {
            "title": "Classical Music for Brain Power",
            "creator": "Mozart & Chopin",
            "description": "Классические композиции для ясности ума и творческого мышления",
            "url": "https://www.youtube.com/watch?v=DXrVSi0Da-8",
            "type": "music",
        },
        {
            "title": "Indie/Alternative Morning Vibes",
            "creator": "Morning Playlist",
            "description": "Свежие инди-треки для вдохновляющего и энергичного утра",
            "url": "https://www.youtube.com/watch?v=wO0Dht1UFXQ",
            "type": "music",
        },
        {
            "title": "Downtempo Electronic - Focused Energy",
            "creator": "Monophonist",
            "description": "Электронная музыка среднего темпа для устойчивого фокуса и продуктивности",
            "url": "https://www.youtube.com/watch?v=DXrVSi0Da-8",
            "type": "music",
        },
        {
            "title": "Chill Hip Hop Beats - Study Mix",
            "creator": "Chillhop Essentials",
            "description": "Спокойный хип-хоп для концентрации и работы",
            "url": "https://www.youtube.com/watch?v=7NOSDKZj0Eg",
            "type": "music",
        },
    ],
}


async def get_content_recommendation() -> Optional[Dict[str, Any]]:
    """
    Get AI-personalized content recommendation based on user profile and time of day.
    GPT-4o recommends and finds actual content (video/podcast/music) from real sources.
    With retry if URL is not accessible.

    Returns:
        {
            "type": "video" | "podcast" | "music",
            "title": str,
            "creator": str,
            "description": str,
            "url": str,
            "emoji": str
        }
    """
    try:
        import json
        client = get_client()
        unavailable_urls = set()
        failed_video_attempts = 0

        # Try up to 3 times if URL check fails (initial + 2 retries)
        for attempt in range(3):
            logger.info(f"Asking GPT-4o to find and recommend content (attempt {attempt + 1}/3)")

            # If this is a retry, ask GPT to avoid previously tried URLs
            retry_instruction = ""
            content_type_hint = ""

            if attempt > 0:
                retry_instruction = f"\n\nВНИМАНИЕ: Предыдущие попытки дали недоступные ссылки:\n" + \
                                   "\n".join(f"- {url}" for url in list(unavailable_urls)[:3]) + \
                                   "\n\nВЫБЕРИ СОВСЕМ ДРУГОЙ контент, НЕ ТЕ ЖЕ ССЫЛКИ!"

            # After 2 failed video attempts, ask for non-YouTube content
            if failed_video_attempts >= 2:
                content_type_hint = "\n⚠️  ВАЖНО: видео с YouTube не работают. ОБЯЗАТЕЛЬНО ВЫБЕРИ подкаст или музыку (не YouTube)."
                logger.warning(f"Video links failed twice, requesting podcast or music instead")

            prompt = f"""Ты рекомендуешь контент для бизнес-аналитика и системного инженера на утро 08:00.

Профиль пользователя: бизнес-аналитик, системный инженер, AI энтузиаст. Интересы: аналитика, стартапы, инновации, системный дизайн, продуктивность, лидерство.

ВАЖНО: контент ТОЛЬКО НА РУССКОМ ЯЗЫКЕ или озвученный на русском.

КРИТИЧНО: ссылка ДОЛЖНА быть действительно доступна и работать без ограничений по регионам.

Найди ОДИН контент который будет полезен ПРЯМО СЕЙЧАС:

Верни ТОЛЬКО валидный JSON (без markdown, без комментариев):
{{
  "type": "video" OR "podcast" OR "music",
  "title": "точное название контента",
  "creator": "имя автора/создателя",
  "description": "краткое описание (1 строка)",
  "url": "прямая ссылка (YouTube, Яндекс.Музыка или другой легальный сервис)"
}}

Для видео: Ищи мотивирующие TED на русском, образовательные видео, лекции о бизнесе/инновациях/лидерстве на русском.
Для подкастов: Ищи русскоязычные подкасты о предпринимательстве, историях успеха, бизнес-инсайтах.
Для музыки: Ищи фокус-музыку - lo-fi hip hop, ambient, классическую музыку (YouTube или Яндекс.Музыка).

ОБЯЗАТЕЛЬНО: ссылка должна содержать реальный трек/видео/плейлист ID (не пустые и не плейсхолдер номера).

Примеры ПРАВИЛЬНЫХ ссылок:
- https://www.youtube.com/watch?v=5qap5aO4i9A (Lo-Fi на YouTube)
- https://www.youtube.com/@accents_podcast (подкаст на YouTube)
- https://music.yandex.ru/album/12345/track/67890 (Яндекс.Музыка с реальными ID)
- https://music.yandex.ru/playlist/123456 (плейлист Яндекс.Музыки)

НИКОГДА не используй плейсхолдеры вроде /888888 или /000000{content_type_hint}{retry_instruction}"""

            response = await client.chat.completions.create(
                model="gpt-5.4-mini",
                max_completion_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.choices[0].message.content.strip()
            logger.debug(f"GPT response (attempt {attempt + 1}): {response_text[:200]}")

            # Clean markdown if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            elif response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # Parse JSON
            content = json.loads(response_text)

            # Validate required fields
            if not all(k in content for k in ["type", "title", "creator", "url", "description"]):
                logger.warning(f"GPT response missing required fields (attempt {attempt + 1})")
                continue

            # Check if URL is accessible
            url = content.get("url", "")
            content_type = content.get("type", "")

            if url:
                logger.debug(f"Checking GPT-recommended URL: {url}")
                url_available = await _check_url_available(url)
                if not url_available:
                    logger.warning(f"GPT-recommended URL not accessible: {url} (attempt {attempt + 1})")
                    unavailable_urls.add(url)
                    # Track failed video attempts
                    if content_type == "video":
                        failed_video_attempts += 1
                        logger.warning(f"Video attempt failed ({failed_video_attempts}/2)")
                    continue  # Try again with different prompt
            else:
                logger.warning(f"GPT response missing URL (attempt {attempt + 1})")
                continue

            # URL is accessible - success!
            # Add emoji
            emojis = {"video": "🎥", "podcast": "🎙️", "music": "🎵"}
            content["emoji"] = emojis.get(content.get("type"), "📺")

            logger.info(f"✓ GPT recommended content: {content['title']} by {content['creator']}")
            return content

        # All retries exhausted - try fallback from static list
        logger.warning(f"⚠️  Failed to get accessible content recommendation after 3 attempts, using fallback")
        return await _get_random_content()

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️  Failed to parse GPT JSON response: {e}")
        return await _get_random_content()
    except Exception as e:
        logger.warning(f"⚠️  Failed to get GPT content recommendation: {type(e).__name__}: {e}")
        return await _get_random_content()


async def _get_random_content() -> Optional[Dict[str, Any]]:
    """Fallback: randomly select content type, deterministically select item based on day of week."""
    try:
        # Randomly choose content type (40% video, 40% podcast, 20% music)
        content_type = random.choices(
            ["videos_ru", "podcasts_ru", "music"],
            weights=[40, 40, 20],
            k=1,
        )[0]

        items = CONTENT_RECOMMENDATIONS.get(content_type, [])
        if not items:
            return None

        # Try to find content with available URL (up to 5 attempts)
        attempts = min(5, len(items))
        day_of_week = datetime.now().weekday()

        for offset in range(attempts):
            item_index = (day_of_week + offset) % len(items)
            item = items[item_index]

            # Check if URL is accessible
            logger.debug(f"Checking fallback URL: {item['url']}")
            url_available = await _check_url_available(item['url'])

            if url_available:
                emojis = {"video": "🎥", "podcast": "🎙️", "music": "🎵"}
                item["emoji"] = emojis.get(item["type"], "📺")
                logger.info(f"✓ Fallback content (type: {content_type}, item #{item_index}, URL verified): {item['title']}")
                return item
            else:
                logger.debug(f"Fallback URL unavailable: {item['url']}, trying another...")

        logger.warning(f"Could not find available fallback content after {attempts} attempts")
        return None

    except Exception as e:
        logger.error(f"⚠️  Fallback failed: {type(e).__name__}: {e}")
        return None
