"""APScheduler setup for morning digest."""

import asyncio
import html
import logging
import json
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from aiogram import Bot
from src.utils.doppler import get_secret
from src.utils.openai_client import get_client
from src.db.database import get_user_profile, get_news_prompt
from src.workers.todoist_client import get_todoist_tasks
from src.ai.weather_sources import get_aggregated_weather, generate_clothing_recommendation, LOCATIONS
from src.workers.news_fetcher import (
    get_politics_economy_news,
    get_sports_news,
    get_technology_news,
    get_culture_science_news,
    get_good_news,
    get_crypto_news,
    get_business_news,
    get_art_news,
    get_fashion_news,
)
from src.ai.news_processor import (
    select_and_summarize_news_with_gpt,
    select_good_news_with_summaries,
    select_themed_news_with_summaries,
    select_crypto_news_with_summaries,
)
from src.workers.gwp_checker import check_gwp_works, check_water_cuts
from src.workers.subscriptions_checker import check_expiring_subscriptions
from src.workers.rates_fetcher import (
    get_crypto_and_forex_rates,
    _update_historical_forex_cache,
)
from src.workers.holidays import get_today_holidays, get_today_events
from src.workers.air_quality import get_air_quality
from src.workers.product_hunt import get_top_product
from src.workers.content_recommender import get_content_recommendation
from src.workers.content_parser import get_album_of_day
from src.workers.quote_of_day import get_quote_of_day
from src.workers.idiom_of_day import get_idiom_of_day
from src.workers.football_matches import get_today_matches, get_formatted_matches, get_yesterday_results, get_formatted_results
from src.workers.forex_multi_source import get_eur_usd_multi_source
from src.workers.meme_fetcher import get_fresh_memes_for_digest
from src.workers.precipitation_checker import get_upcoming_precipitation
from src.workers.tbilisi_reddit import get_tbilisi_reddit_highlight
from src.workers.place_recommender import get_place_of_day
from src.workers.joke_of_day import get_joke_of_day

logger = logging.getLogger(__name__)

# Constants
MORNING_DIGEST_TIMEOUT_SECONDS = 300
TELEGRAM_MESSAGE_CHAR_LIMIT = 4000
WEATHER_JACKET_THRESHOLD_C = 10
PRECIPITATION_ALERT_COOLDOWN_HOURS = 3

# Per-user digest tuning
# Users who receive ONLY good news (5-6 items) — no politics/economics/sports/tech
GOOD_NEWS_ONLY_USERS = {184010236}
# Users who receive THEMED news only: business / art / fashion / good news (Юля)
THEMED_NEWS_USERS = {498233237}
# Users for whom the GWP water-cut section (Vazha Iverieli) is suppressed
SKIP_WATER_CUTS_USERS = {498233237}
# Users who get the server/VPS-and-domain expiry section (main user only)
SERVER_SUBSCRIPTIONS_USERS = {71488343}
# Users who get the r/tbilisi city highlight section
TBILISI_REDDIT_USERS = {71488343, 184010236}
# Users who get an extra crypto news item (main user only)
CRYPTO_NEWS_USERS = {71488343}
# Users who get the English idiom/euphemism of the day (Маша и Максим)
IDIOM_OF_DAY_USERS = {184010236, 71488343}
# Users who get the place-of-the-day recommendation and their city:
# Маша и Максим — Тбилиси, Юля — Вена
PLACE_OF_DAY_CITIES = {
    184010236: ("tbilisi", "Тбилиси"),
    71488343: ("tbilisi", "Тбилиси"),
    498233237: ("vienna", "Вене"),
}

def _esc(text) -> str:
    """Escape text destined for a parse_mode=HTML message.

    The whole digest is sent as HTML, so any raw <, >, & from GPT output or RSS
    titles (e.g. "AT&T", "a < b") breaks entity parsing and Telegram drops the
    ENTIRE message. Escape every dynamic text fragment we interpolate; do NOT run
    this over markup we add ourselves (tags) or over href values (use _esc_attr).
    """
    return html.escape(str(text or ""), quote=False)


def _esc_attr(url) -> str:
    """Escape a URL for use inside an HTML attribute (href).

    RSS links routinely carry & in query strings (?a=1&b=2); unescaped they break
    HTML entity parsing the same way. quote=True also escapes any stray quotes.
    """
    return html.escape(str(url or ""), quote=True)


# Per-user weather location: (location key for get_aggregated_weather, prepositional label).
# Everyone defaults to Tbilisi; user 498233237 (Юля) gets Vienna.
WEATHER_LOCATIONS = {498233237: ("vienna", "Вене")}
DEFAULT_WEATHER_LOCATION = ("tbilisi", "Тбилиси")

# Display names + grammatical gender for the personalized morning greeting
USER_NAMES = {184010236: "Маша", 498233237: "Юля", 71488343: "Максим"}
USER_GENDER = {184010236: "женского", 498233237: "женского", 71488343: "мужского"}

# Russian weekday names (Monday=0 .. Sunday=6)
WEEKDAYS_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]

# Global scheduler instance
scheduler: AsyncIOScheduler = None

# Track last precipitation alert to avoid spam
_last_precipitation_alert: Optional[datetime] = None


def _is_task_urgent_by_keywords(task) -> bool:
    """Check if task text contains urgency keywords (срочно, asap, etc)."""
    urgency_keywords = [
        "срочно",
        "важно",
        "asap",
        "асап",
        "быстро",
        "немедленно",
        "срочная",
        "срочной",
        "неотложн",
        "критичн",
        "экстренно",
        "urgent",
        "emergency",
        "immediately",
        "right now",
        "now",
    ]

    text = f"{task.what or ''} {task.raw_text or ''}".lower()
    return any(keyword in text for keyword in urgency_keywords)


def _handle_gather_exception(result, name: str):
    """Log and handle exception from asyncio.gather, return None if exception."""
    if isinstance(result, Exception):
        exc_type = type(result).__name__
        exc_msg = str(result)[:150] if str(result) else "unknown error"

        if isinstance(result, TimeoutError):
            logger.warning(f"⏱️  {name}: timeout")
        elif isinstance(result, ConnectionError):
            logger.warning(f"🔗 {name}: connection error - {exc_msg}")
        elif isinstance(result, ValueError):
            logger.warning(f"⚠️  {name}: validation error - {exc_msg}")
        else:
            logger.error(f"💥 {name}: {exc_type} - {exc_msg}")

        return None
    return result


async def morning_digest(
    bot: Bot,
    user_id: int,
    chat_id: int = None,
    skip_sports: bool = False,
    skip_tasks: bool = False,
):
    """Send morning digest: intro + news + task list with timeout and error handling.

    Args:
        bot: Telegram Bot instance
        user_id: User ID to send digest to
        chat_id: Chat ID (optional, uses user_id if not provided)
        skip_sports: Skip football/sports section
        skip_tasks: Skip tasks section
    """
    skip_str = ""
    if skip_sports or skip_tasks:
        parts = []
        if skip_sports:
            parts.append("спорт")
        if skip_tasks:
            parts.append("дела")
        skip_str = f" (without {', '.join(parts)})"
    logger.info(f"🌅 Starting morning digest for user {user_id}{skip_str}")

    try:
        # Set global timeout for entire digest (120 seconds = 2 minutes for all API calls)
        try:
            if hasattr(asyncio, "timeout"):  # Python 3.11+
                async with asyncio.timeout(120):
                    await _morning_digest_impl(
                        bot, user_id, chat_id,
                        skip_sports=skip_sports,
                        skip_tasks=skip_tasks,
                    )
            else:  # Python 3.10 and earlier
                await asyncio.wait_for(
                    _morning_digest_impl(
                        bot, user_id, chat_id,
                        skip_sports=skip_sports,
                        skip_tasks=skip_tasks,
                    ),
                    timeout=MORNING_DIGEST_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            logger.error(f"⏱️  Morning digest exceeded {MORNING_DIGEST_TIMEOUT_SECONDS}s timeout for user {user_id}")
            try:
                if chat_id is None:
                    chat_id = get_secret("TELEGRAM_CHAT_ID")
                await bot.send_message(
                    chat_id=chat_id,
                    text="🌅 Доброе утро! (дайджест не готов - превышен timeout 120с)",
                    disable_web_page_preview=True,
                )
            except Exception as fallback_err:
                logger.error(f"Failed to send timeout fallback message: {type(fallback_err).__name__}: {str(fallback_err)[:100]}")

    except Exception as e:
        exc_type = type(e).__name__
        exc_msg = str(e)[:200] if str(e) else "unknown error"
        logger.error(f"💥 Morning digest failed for user {user_id}: {exc_type}")
        logger.error(f"  Details: {exc_msg}")

        try:
            if chat_id is None:
                chat_id = get_secret("TELEGRAM_CHAT_ID")
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Дайджест не отправлен: {exc_type}",
                disable_web_page_preview=True,
            )
        except Exception as fallback_err:
            logger.error(f"Failed to send error fallback message: {type(fallback_err).__name__}")


async def _morning_digest_impl(
    bot: Bot,
    user_id: int,
    chat_id: int = None,
    include_tasks: bool = True,
    skip_sports: bool = False,
    skip_tasks: bool = False,
):
    """Implementation of morning digest (called with timeout).

    Args:
        skip_sports: Skip football/sports section
        skip_tasks: Skip tasks section (overrides include_tasks)
    """
    if skip_tasks:
        include_tasks = False

    # Weather location per user (default Tbilisi; user 498233237 → Vienna)
    weather_location, city_prep = WEATHER_LOCATIONS.get(user_id, DEFAULT_WEATHER_LOCATION)

    logger.info(f"Loading tasks, profile, weather ({weather_location}) for user {user_id} (include_tasks={include_tasks})")

    # Parallel API calls - much faster than sequential
    # Only load tasks if include_tasks=True
    gather_tasks = [
        get_user_profile(user_id),
        get_aggregated_weather(weather_location),
    ]
    if include_tasks:
        gather_tasks.insert(0, get_todoist_tasks())

    results = await asyncio.gather(*gather_tasks, return_exceptions=True)

    if include_tasks:
        tasks = _handle_gather_exception(results[0], "tasks") or []
        user_profile = _handle_gather_exception(results[1], "profile")
        weather = _handle_gather_exception(results[2], "weather")
    else:
        user_profile = _handle_gather_exception(results[0], "profile")
        weather = _handle_gather_exception(results[1], "weather")
        tasks = []

    if user_profile is None:
        from src.db.models import UserProfile

        user_profile = UserProfile(user_id=user_id)

    logger.info(
        f"✓ Loaded: {len(tasks)} tasks | profile: {user_profile.wake_time}-{user_profile.sleep_time} | weather: {'OK' if weather else 'FAILED'}"
    )

    # Generate intro context via AI
    weather_desc = _format_weather(weather, city_prep) if weather else "неизвестная погода"
    logger.info(f"Weather condition: {weather_desc}")

    # Extract weather data for clothing recommendations
    weather_details = ""
    is_raining = False  # Default to False if weather unavailable
    if weather and isinstance(weather, dict):
        # Get temperature from any period (morning/day/evening/night)
        temp = None
        for period in ["morning", "day", "evening", "night"]:
            if isinstance(weather.get(period), dict):
                temp = weather[period].get("temperature")
                if temp:
                    break

        # Check for precipitation from weather condition keywords
        # (Yandex/Gismeteo HTML parsers return precipitation_mm=0.0, use condition keywords instead)
        RAIN_KEYWORDS = ["дождь", "снег", "гроза", "морось", "ливень", "ледяной дождь", "град"]
        is_raining = any(
            isinstance(weather.get(period), dict)
            and any(kw in weather[period].get("condition", "").lower() for kw in RAIN_KEYWORDS)
            for period in ["morning", "day", "evening"]
        )

        weather_details = f"Температура: {temp}°C" if temp else ""
        if is_raining:
            weather_details += (
                " (ожидаются осадки)" if weather_details else "Ожидаются осадки"
            )

    # Personalize the greeting: name, grammatical gender, weekday
    user_name = USER_NAMES.get(user_id, "")
    user_gender = USER_GENDER.get(user_id, "мужского")
    weekday_ru = WEEKDAYS_RU[datetime.now(timezone("Asia/Tbilisi")).weekday()]
    name_part = f", {user_name}" if user_name else ""

    intro_prompt = f"""Напиши КОРОТКОЕ (1-2 предложения) тёплое и обаятельное утреннее приветствие для человека по имени {user_name or 'друг'} ({user_gender} рода).

Сегодня {weekday_ru}. {weather_desc}. {weather_details}

Требования:
- Обязательно обратись по имени: {user_name or 'друг'}
- Дружелюбно, живо, с лёгкой искрой — как сообщение от хорошего друга
- Естественно упомяни день недели и/или погоду
- Заверши короткой подводкой к дайджесту по смыслу «вот что я для тебя собрал на сегодня» — но обязательно СВОИМИ словами, каждый раз формулируй по-новому. НЕ копируй эту фразу дословно.
- Без клише («начни день с улыбки», «ты можешь всё», «заряд энергии») и без официоза

Пример ТОЛЬКО для тона (не повторяй его дословно, придумай свой вариант подводки): "Доброе утро{name_part}! Наконец-то начинается этот солнечный (должно соответствовать реальной погоде, солнечный необязательно) {weekday_ru} день."

Ответ — только текст приветствия, строго 1-2 предложения."""  # noqa: E501

    logger.info("🔄 Calling AI to generate morning greeting and weather advice")

    response = await get_client().chat.completions.create(
        model="gpt-5.4-mini",
        max_completion_tokens=150,
        messages=[
            {
                "role": "system",
                "content": "You are a friendly morning assistant in Russian.",
            },
            {"role": "user", "content": intro_prompt},
        ],
    )

    logger.info(f"✓ OpenAI response received:")
    logger.info(f"  Model: {response.model}")
    logger.info(
        f"  Tokens: {response.usage.prompt_tokens}→{response.usage.completion_tokens}"
    )

    response_text = response.choices[0].message.content
    logger.info(f"  Content length: {len(response_text) if response_text else 0} chars")

    # Use the entire response as the greeting
    simple_greeting = response_text.strip() if response_text else f"Доброе утро{name_part}! Лови утреннюю сводку:"

    if not simple_greeting or len(simple_greeting) < 10:
        logger.error("❌ AI returned incomplete response, using fallback")
        simple_greeting = f"Доброе утро{name_part}! Лови утреннюю сводку:"

    # AI-based clothing recommendation with jacket validation
    # (Replaces old rule-based logic that didn't account for temperature < 10°C)
    outfit_advice = await generate_clothing_recommendation(weather, is_raining=is_raining, city=city_prep)

    if not outfit_advice:
        # Fallback: rule-based with correct jacket threshold (< 10°C OR is_raining)
        logger.warning("⚠️ AI clothing recommendation failed, using fallback")
        morning_temp = None
        day_temp = None
        if weather and isinstance(weather.get("morning"), dict):
            morning_temp = weather["morning"].get("temperature")
        if weather and isinstance(weather.get("day"), dict):
            day_temp = weather["day"].get("temperature")

        needs_jacket = is_raining or (
            (morning_temp is not None and morning_temp < 10) or
            (day_temp is not None and day_temp < 10)
        )
        outer_layer = "куртка" if needs_jacket else ("худи" if day_temp is not None and day_temp < 15 else None)
        outfit_advice = f"Штаны, кофта, {outer_layer}, кроссовки" if outer_layer else "Штаны, кофта, кроссовки"

    logger.info(
        f"✓ Generated - greeting: {simple_greeting[:70]}... | outfit: {outfit_advice}"
    )

    # Build full message: greeting + quote + weather advice + weather + news + gwp + task list
    if chat_id is None:
        chat_id = get_secret("TELEGRAM_CHAT_ID")

    message_lines = [simple_greeting, ""]

    # Add quote of the day
    logger.info("Fetching quote of the day")
    quote = await get_quote_of_day()
    if quote:
        message_lines.append(f"✨ <i>\"{_esc(quote['text'])}\"</i>")
        message_lines.append(f"<i>— {_esc(quote['author'])}</i>")
        message_lines.append("")
    else:
        logger.warning("Quote fetch failed")

    # Add outfit recommendation
    message_lines.append(f"👕 {outfit_advice}")
    message_lines.append("")

    # Add weather by periods
    logger.info("Formatting weather by periods")
    if weather:
        weather_str = _format_weather(weather, city_prep)
        message_lines.append(weather_str)
        message_lines.append("")
    else:
        message_lines.append("Погода недоступна")
        message_lines.append("")

    # Add air quality for the user's city (Tbilisi by default, Vienna for Юля)
    _loc_cfg = LOCATIONS.get(weather_location, LOCATIONS["tbilisi"])
    logger.info(f"Fetching air quality for {weather_location}")
    air_quality = await get_air_quality(_loc_cfg["lat"], _loc_cfg["lon"])
    if air_quality:
        aqi = air_quality.get("aqi", "?")
        desc = air_quality.get("description", "")
        pm25 = air_quality.get("pm25")
        # Add PM2.5 with quality assessment
        if pm25:
            # PM2.5 quality: 0-12 Good, 12-35 Moderate, 35-55 Unhealthy for Sensitive, 55+ Unhealthy
            if pm25 <= 12:
                pm25_quality = "отлично"
            elif pm25 <= 35:
                pm25_quality = "хорошо"
            elif pm25 <= 55:
                pm25_quality = "умеренно"
            elif pm25 <= 150:
                pm25_quality = "вредно"
            else:
                pm25_quality = "опасно"
            pm25_str = f", PM2.5: {pm25:.1f}µg/m³ ({pm25_quality})"
        else:
            pm25_str = ""
        message_lines.append(f"💨 Качество воздуха: AQI {aqi} {desc}{pm25_str}")
        message_lines.append("")
    else:
        logger.warning("Air quality fetch failed")
        message_lines.append("💨 Качество воздуха: недоступно")
        message_lines.append("")

    # Check for today's holidays and events
    logger.info("Checking for holidays and events")
    today_holidays, today_events = await asyncio.gather(
        get_today_holidays(),
        get_today_events(),
        return_exceptions=True,
    )

    if not isinstance(today_holidays, Exception) and today_holidays:
        for holiday_text, emoji in today_holidays:
            message_lines.append(f"{holiday_text}")
    if not isinstance(today_events, Exception) and today_events:
        for event_text in today_events:
            message_lines.append(f"{event_text}")
    if (not isinstance(today_holidays, Exception) and today_holidays) or (
        not isinstance(today_events, Exception) and today_events
    ):
        message_lines.append("")

    # Check GWP for works on Vazha Iverievi
    logger.info("Checking GWP for works on Vazha Iverievi street")
    gwp_works = await check_gwp_works()
    if gwp_works:
        message_lines.append("Планируются работы на Важа Ивериели:")
        for work in gwp_works:
            message_lines.append(f"  {work}")
        message_lines.append("")
    else:
        logger.info("No scheduled works on Vazha Iverievi")

    # Check Google Sheet for expiring VPS / domains (within 7 days) — main user only
    if user_id in SERVER_SUBSCRIPTIONS_USERS:
        logger.info("Checking Google Sheet for expiring VPS / domains")
        subs = await check_expiring_subscriptions()
        if not subs["ok"]:
            message_lines.append(
                f"⚠️ Не удалось проверить VPS/домены: {subs['error']}"
            )
            message_lines.append("")
        if subs["warnings"]:
            message_lines.append("🔔 Скоро истекает оплата (продли!):")
            message_lines.extend(subs["warnings"])
            message_lines.append("")
        elif subs["ok"]:
            logger.info("No expiring VPS / domains in the next 7 days")
    else:
        logger.info(f"Skipping VPS/domain expiry section for user {user_id}")

    # Fetch news from 5 specialized pools in parallel
    logger.info(
        "Fetching news from 5 specialized pools (politics, sports, tech, culture, good news)"
    )
    (politics_news, sports_news, technology_news, culture_news, goodness_news) = (
        await asyncio.gather(
            get_politics_economy_news(hours=24),
            get_sports_news(hours=24),
            get_technology_news(hours=24),
            get_culture_science_news(hours=24),
            get_good_news(hours=24),
            return_exceptions=True,
        )
    )

    # Handle exceptions from gather
    if isinstance(politics_news, Exception):
        logger.warning(f"Failed to fetch politics news: {politics_news}")
        politics_news = []
    if isinstance(sports_news, Exception):
        logger.warning(f"Failed to fetch sports news: {sports_news}")
        sports_news = []
    if isinstance(technology_news, Exception):
        logger.warning(f"Failed to fetch technology news: {technology_news}")
        technology_news = []
    if isinstance(culture_news, Exception):
        logger.warning(f"Failed to fetch culture news: {culture_news}")
        culture_news = []
    if isinstance(goodness_news, Exception):
        logger.warning(f"Failed to fetch good news: {goodness_news}")
        goodness_news = []

    total_news = (
        len(politics_news)
        + len(sports_news)
        + len(technology_news)
        + len(culture_news)
        + len(goodness_news)
    )
    logger.info(
        f"✓ News fetched: {total_news} items total | politics: {len(politics_news)}, sports: {len(sports_news)}, tech: {len(technology_news)}, culture: {len(culture_news)}, good: {len(goodness_news)}"
    )

    # Extra crypto news pool — main user only
    crypto_news = []
    if user_id in CRYPTO_NEWS_USERS:
        try:
            crypto_news = await get_crypto_news(hours=24)
            logger.info(f"✓ Crypto news fetched: {len(crypto_news)} items")
        except Exception as e:
            logger.warning(f"Failed to fetch crypto news: {type(e).__name__}: {str(e)[:100]}")
            crypto_news = []

    # Users who get ONLY good news (5-6 items), no politics/economics/sports/tech
    use_good_news_only = user_id in GOOD_NEWS_ONLY_USERS
    # User who gets THEMED news only: business / art / fashion / good news (Юля)
    use_themed_news = user_id in THEMED_NEWS_USERS

    # Lookup list used to resolve selected indices back to source/url. For the
    # themed user it becomes her own combined pool (set below); otherwise the
    # standard 5 pools concatenated further down.
    themed_all = None

    if total_news > 0 or use_themed_news:
        if use_themed_news:
            # Юля: business / art / fashion / good news. Fetch her dedicated pools
            # (good news reuses the already-fetched goodness_news pool).
            logger.info(f"User {user_id}: themed news selection (business/art/fashion/good)")
            business_news, art_news, fashion_news = await asyncio.gather(
                get_business_news(hours=24),
                get_art_news(hours=24),
                get_fashion_news(hours=24),
                return_exceptions=True,
            )
            business_news = business_news if isinstance(business_news, list) else []
            art_news = art_news if isinstance(art_news, list) else []
            fashion_news = fashion_news if isinstance(fashion_news, list) else []
            logger.info(
                f"✓ Themed pools: business {len(business_news)}, art {len(art_news)}, "
                f"fashion {len(fashion_news)}, good {len(goodness_news)}"
            )
            # MUST match the concatenation order inside select_themed_news_with_summaries.
            themed_all = business_news + art_news + fashion_news + goodness_news
            selected_with_indices = await select_themed_news_with_summaries(
                business_news, art_news, fashion_news, goodness_news
            )
        elif use_good_news_only:
            # Good-news-only users: show up to 6 good news with summaries
            if goodness_news:
                logger.info(f"User {user_id}: good-news-only selection ({len(goodness_news)} items)")
                selected_with_indices = await select_good_news_with_summaries(goodness_news)
            else:
                logger.warning(f"User {user_id}: no good news available, fallback to standard selection")
                selected_with_indices = await select_and_summarize_news_with_gpt(
                    politics_news,
                    sports_news,
                    technology_news,
                    culture_news,
                    goodness_news,
                    user_id,
                )
        else:
            # Standard full mix (politics/economics/sports/tech + good) for everyone else
            logger.info("Sending news pools to ChatGPT for selection and summarization")
            selected_with_indices = await select_and_summarize_news_with_gpt(
                politics_news,
                sports_news,
                technology_news,
                culture_news,
                goodness_news,
                user_id,
            )

        if selected_with_indices:
            logger.info(f"✓ ChatGPT selected {len(selected_with_indices)} news items")

            # Build combined news list for index matching. The themed user (Юля)
            # uses her own pool (business+art+fashion+good) with GLOBAL indices, so
            # no offset is applied for her.
            if use_themed_news and themed_all is not None:
                all_news = themed_all
            else:
                all_news = (
                    politics_news
                    + sports_news
                    + technology_news
                    + culture_news
                    + goodness_news
                )

            # Calculate offset for good news indices (only used in good news selection)
            goodness_offset = len(politics_news) + len(sports_news) + len(technology_news) + len(culture_news)

            # Match indices back to original news items and format with URLs
            message_lines.append("Новости:")
            message_lines.append("")

            # Running counter so skipped items don't leave gaps, and so the extra
            # crypto item (if any) continues the same numbering.
            news_num = 0
            for item in selected_with_indices:
                idx = item["index"]
                category = item["category"]
                description_ru = item.get("description_ru", "")

                # For good news selection, adjust index to combined array offset
                if use_good_news_only and category == "goodness":
                    combined_idx = idx + goodness_offset
                else:
                    combined_idx = idx

                # Get original news item by index (with safety check)
                if 0 <= combined_idx < len(all_news):
                    original_news = all_news[combined_idx]
                    source = original_news.get("source", "Unknown")
                    url = original_news.get("url", "")

                    news_num += 1

                    # Format: <a href="url">Source</a>: description_ru (full, complete text)
                    news_text = (
                        f'{news_num}. <a href="{_esc_attr(url)}">{_esc(source)}</a>: {_esc(description_ru)}'
                        if url
                        else f"{news_num}. {_esc(source)}: {_esc(description_ru)}"
                    )

                    message_lines.append(news_text)
                    message_lines.append("")

                    logger.info(
                        f"  [{news_num}] {category}: {description_ru[:60]}... | {source}"
                    )
                else:
                    logger.warning(f"Invalid index {combined_idx} for news selection, skipping")

            # Extra crypto news item (main user only). Skipped if nothing suitable
            # or ChatGPT returns ❌.
            if user_id in CRYPTO_NEWS_USERS and crypto_news:
                logger.info("Selecting crypto news item via ChatGPT")
                crypto_selected = await select_crypto_news_with_summaries(crypto_news)
                if crypto_selected:
                    citem = crypto_selected[0]
                    cidx = citem.get("index", -1)
                    cdesc = citem.get("description_ru", "")
                    if 0 <= cidx < len(crypto_news):
                        c_news = crypto_news[cidx]
                        c_source = c_news.get("source", "Crypto")
                        c_url = c_news.get("url", "")
                        news_num += 1
                        crypto_text = (
                            f'{news_num}. 🪙 <a href="{_esc_attr(c_url)}">{_esc(c_source)}</a>: {_esc(cdesc)}'
                            if c_url
                            else f"{news_num}. 🪙 {_esc(c_source)}: {_esc(cdesc)}"
                        )
                        message_lines.append(crypto_text)
                        message_lines.append("")
                        logger.info(f"  [{news_num}] crypto: {cdesc[:60]}... | {c_source}")
                else:
                    logger.info("No crypto news item to show (skipped)")

        else:
            logger.warning("⚠️  ChatGPT news selection failed, showing placeholder")
            message_lines.append("Новости:")
            message_lines.append("(новости недоступны)")
            message_lines.append("")
    else:
        logger.warning("No news items fetched from any pool")
        message_lines.append("Новости:")
        message_lines.append("(новости недоступны)")
        message_lines.append("")

    # r/tbilisi city highlight (selected users only)
    if user_id in TBILISI_REDDIT_USERS:
        logger.info("Fetching r/tbilisi city highlight")
        try:
            highlight = await get_tbilisi_reddit_highlight()
        except Exception as e:
            logger.warning(f"r/tbilisi highlight failed: {type(e).__name__}: {str(e)[:100]}")
            highlight = None

        if highlight:
            message_lines.append("🏙️ <b>Тбилиси на Reddit:</b>")
            title = highlight.get("title", "")
            url = highlight.get("url", "")
            desc = highlight.get("description", "")
            if url:
                message_lines.append(f'<a href="{url}">{title}</a>')
            else:
                message_lines.append(title)
            if desc:
                message_lines.append(desc)
            message_lines.append("")
        else:
            logger.info("No r/tbilisi highlight (section skipped)")

    # Idiom / euphemism of the day — English + Spanish (Маша и Максим)
    if user_id in IDIOM_OF_DAY_USERS:
        for lang_code, flag in (("en", "🇬🇧"), ("es", "🇪🇸")):
            logger.info(f"Fetching idiom of the day [{lang_code}]")
            try:
                idiom = await get_idiom_of_day(language=lang_code)
            except Exception as e:
                logger.warning(f"Idiom of day [{lang_code}] failed: {type(e).__name__}: {str(e)[:100]}")
                idiom = None

            if idiom:
                kind_label = "Эвфемизм дня" if "эвфемизм" in idiom.get("kind", "").lower() else "Идиома дня"
                message_lines.append(f"{flag} <b>{kind_label}:</b>")
                message_lines.append(f'<b>«{_esc(idiom["phrase"])}»</b> — {_esc(idiom["meaning_ru"])}')
                example_text = idiom.get("example") or idiom.get("example_en")
                if example_text:
                    example = f'<i>{_esc(example_text)}</i>'
                    if idiom.get("example_ru"):
                        example += f' — {_esc(idiom["example_ru"])}'
                    message_lines.append(example)
                message_lines.append("")
            else:
                logger.info(f"No idiom of day [{lang_code}] (section skipped)")

    # Place of the day — one place to visit, no repeats within 28 days
    # (Маша и Максим — Тбилиси, Юля — Вена)
    if user_id in PLACE_OF_DAY_CITIES:
        place_city, place_city_prep = PLACE_OF_DAY_CITIES[user_id]
        logger.info(f"Fetching place of the day [{place_city}]")
        try:
            place = await get_place_of_day(place_city)
        except Exception as e:
            logger.warning(f"Place of day failed: {type(e).__name__}: {str(e)[:100]}")
            place = None

        if place:
            message_lines.append(f"📍 <b>Место дня в {place_city_prep}:</b>")
            area_str = f" ({_esc(place['area'])})" if place.get("area") else ""
            message_lines.append(f'<b>{_esc(place["name"])}</b>{area_str}')
            message_lines.append(_esc(place["description"]))
            message_lines.append("")
        else:
            logger.info("No place of day (section skipped)")

    # Joke of the day, «категория Б» — from real sources, no repeats within 28 days.
    # Sent to ALL digest recipients.
    logger.info("Fetching joke of the day")
    try:
        joke = await get_joke_of_day()
    except Exception as e:
        logger.warning(f"Joke of day failed: {type(e).__name__}: {str(e)[:100]}")
        joke = None

    if joke:
        message_lines.append("😄 <b>Анекдот дня:</b>")
        message_lines.append(_esc(joke["text"]))
        if joke.get("url"):
            message_lines.append(f'<i><a href="{_esc_attr(joke["url"])}">{_esc(joke["source"])}</a></i>')
        else:
            message_lines.append(f'<i>{_esc(joke["source"])}</i>')
        message_lines.append("")
    else:
        logger.info("No joke of day (section skipped)")

    # Tasks section (only if include_tasks=True)
    if include_tasks:
        # Tasks are already filtered by database to when_date <= today or NULL
        # Just use them as-is (no additional date filtering needed)
        today_tasks = tasks
        logger.info(f"Tasks loaded: {len(today_tasks)} tasks ready for today")

        # NOTE: tasks are NOT sent to ChatGPT. They are shown as-is from Todoist
        # (no AI explanations, no AI priority ranking) — per user requirement.
        def _format_task_simple(task, is_urgent=False):
            """Format a task for the digest using only Todoist data (no ChatGPT)."""
            name = task.what or (task.raw_text or "")[:80]
            line = f"• {name}"
            if getattr(task, "when_time", None):
                line += f" — {task.when_time}"
            if getattr(task, "place", None):
                line += f" ({task.place})"
            if is_urgent:
                line += " ⚠️"
            return line

        def _task_sort_key(task):
            # Deterministic, no-GPT ordering: timed tasks first (by time), then untimed by id
            return (task.when_time is None, task.when_time or "", task.id or 0)

        if today_tasks:
            # Separate urgent and non-urgent tasks (is_urgent flag or keyword match)
            urgent_tasks = sorted(
                [t for t in today_tasks if t.is_urgent or _is_task_urgent_by_keywords(t)],
                key=_task_sort_key,
            )
            non_urgent_tasks = sorted(
                [t for t in today_tasks if not t.is_urgent and not _is_task_urgent_by_keywords(t)],
                key=_task_sort_key,
            )

            # Show urgent tasks
            if urgent_tasks:
                message_lines.append("СРОЧНЫЕ:")
                for task in urgent_tasks:
                    message_lines.append(_format_task_simple(task, is_urgent=True))
                    logger.info(f"  Urgent: {task.what or task.raw_text[:30]}")
                message_lines.append("")

            # Show all non-urgent tasks if available
            if non_urgent_tasks:
                message_lines.append("НЕСРОЧНЫЕ ЗАДАЧИ:")
                for task in non_urgent_tasks:
                    message_lines.append(_format_task_simple(task, is_urgent=False))
                    logger.info(f"  Non-urgent: {task.what or task.raw_text[:30]}")
                message_lines.append("")
        else:
            message_lines.append("Дел на сегодня нет.")
            logger.info("No tasks for today")
            message_lines.append("")
    else:
        logger.info("Skipping tasks section (include_tasks=False)")

    # Add exchange rates with % changes
    logger.info("Fetching exchange rates with changes")
    rates = await get_crypto_and_forex_rates()
    if rates:
        def format_currency(value: float, decimals: int = 2) -> str:
            """Format number with space as thousands separator."""
            if value is None:
                return "N/A"
            if decimals == 5:
                formatted = f"{value:,.5f}".rstrip("0").rstrip(".")
            else:
                formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
            return formatted.replace(",", " ")

        def format_change(change_24h, change_30d) -> str:
            """Format percentage changes with arrow emojis."""
            if change_24h is None or change_30d is None:
                return ""
            arrow_24h = "↑" if change_24h >= 0 else "↓"
            arrow_30d = "↑" if change_30d >= 0 else "↓"
            return f" ({arrow_24h} {abs(change_24h):.1f}% for 24h, {arrow_30d} {abs(change_30d):.1f} % for 30d)"

        # Build rate lines into a buffer; only emit the section if something succeeded,
        # so we never print an empty "Курсы валют:" header.
        rate_lines = []

        # BTC
        if rates.get("btc_usd"):
            btc_str = format_currency(rates["btc_usd"], decimals=5)
            change_str = format_change(
                rates.get("btc_change_24h"), rates.get("btc_change_30d")
            )
            rate_lines.append(f"BTC: {btc_str} USD{change_str}")

        # ETH
        if rates.get("eth_usd"):
            eth_str = format_currency(rates["eth_usd"], decimals=5)
            change_str = format_change(
                rates.get("eth_change_24h"), rates.get("eth_change_30d")
            )
            rate_lines.append(f"ETH: {eth_str} USD{change_str}")

        # EUR (multi-source preferred; fall back to the value already fetched in `rates`)
        eur_multi = await get_eur_usd_multi_source()
        if eur_multi:
            source1 = eur_multi.get("eur_usd_source1")
            source2 = eur_multi.get("eur_usd_source2")
            avg = eur_multi.get("eur_usd_avg")

            if source1:
                rate_lines.append(f"EUR (ExchangeRate): {format_currency(source1, decimals=5)} USD")
            if source2:
                rate_lines.append(f"EUR (ECB): {format_currency(source2, decimals=5)} USD")
            if avg and rates.get("eur_change_24h") is not None:
                change_str = format_change(
                    rates.get("eur_change_24h"), rates.get("eur_change_30d")
                )
                rate_lines.append(f"EUR (avg): {format_currency(avg, decimals=5)} USD{change_str}")
        elif rates.get("usd_eur"):
            # Multi-source EUR unavailable — use the rate from get_crypto_and_forex_rates
            change_str = format_change(
                rates.get("eur_change_24h"), rates.get("eur_change_30d")
            )
            rate_lines.append(f"EUR: {format_currency(rates['usd_eur'], decimals=5)} USD{change_str}")

        # RUB
        if rates.get("usd_rub"):
            rub_str = format_currency(rates["usd_rub"], decimals=2)
            change_str = format_change(
                rates.get("rub_change_24h"), rates.get("rub_change_30d")
            )
            rate_lines.append(f"USD: {rub_str} RUB{change_str}")

        if rate_lines:
            message_lines.append("Курсы валют:")
            message_lines.extend(rate_lines)
            message_lines.append("")
        else:
            logger.info("Rates dict present but no renderable values — skipping section")
    else:
        logger.info("Failed to fetch rates")

    # Check for water cuts on Vazha Ivereli street (suppressed for some users)
    if user_id in SKIP_WATER_CUTS_USERS:
        logger.info(f"Skipping water-cut section for user {user_id}")
    else:
        logger.info("Checking for water cuts on Vazha Ivereli street")
        water_cuts = await check_water_cuts()
        message_lines.append("💧 Отключение воды:")
        if water_cuts:
            message_lines.append(water_cuts)
        else:
            message_lines.append("Отключений воды на Важа Ивериели не запланировано")
            logger.info("No water cuts found on Vazha Ivereli street")
        message_lines.append("")

    # Check yesterday's football results (Barcelona/Real Madrid/Arsenal/PSG/Atletico/Man City priority)
    if not skip_sports:
        logger.info("Checking yesterday's football results")
        yesterday_results = await get_yesterday_results()
    else:
        logger.info("⏭️  Skipping sports section")
        yesterday_results = None

    if yesterday_results and not skip_sports:
        # Show yesterday's results
        logger.info(f"✓ Found {len(yesterday_results)} yesterday result(s)")
        formatted_results = await get_formatted_results(yesterday_results)
        if formatted_results:
            message_lines.append(formatted_results)
            message_lines.append("")
    else:
        logger.info("No yesterday results found")

    # Check for football matches (Barcelona/Real Madrid/Arsenal/PSG/Atletico/Man City priority)
    if not skip_sports:
        logger.info("Checking for football matches today")
        matches = await get_today_matches()
    else:
        matches = None

    if matches and not skip_sports:
        # Show football matches
        logger.info(f"✓ Found {len(matches)} football match(es)")
        formatted_matches = await get_formatted_matches(matches)
        if formatted_matches:
            message_lines.append(formatted_matches)
            message_lines.append("")
    elif not skip_sports:
        # No matches - show sports news from middle of list + Product Hunt
        logger.info("No football matches found, showing sports news + Product Hunt")
        logger.debug(f"sports_news type: {type(sports_news)}, len: {len(sports_news) if sports_news else 0}")

        if sports_news and len(sports_news) > 0:
            # Take news from middle (not first or last) to avoid top/bottom stories
            mid_idx = len(sports_news) // 2
            news = sports_news[mid_idx]
            logger.debug(f"Selected sports news at index {mid_idx}: {news.get('title', '')[:50]}")

            title = news.get("title", "")
            url = news.get("url", "")
            source = news.get("source", "")
            description = news.get("description", "")

            # Rewrite news via GPT
            rewrite_prompt = f"""Переписать спортивную новость в формате дайджеста (одно предложение, максимум 20 слов). Должна быть информативной и интересной.

Оригинальная новость:
Заголовок: {title}
Источник: {source}
Описание: {description[:300]}

Ответ - только одно переписанное предложение на русском:"""

            logger.info(f"Rewriting sports news: {title[:50]}...")
            try:
                response = await get_client().chat.completions.create(
                    model="gpt-5.4-mini",
                    max_completion_tokens=50,
                    messages=[
                        {"role": "system", "content": "You are a sports news editor in Russian."},
                        {"role": "user", "content": rewrite_prompt},
                    ],
                )

                rewritten = response.choices[0].message.content.strip()
                logger.info(f"✓ Sports news rewritten: {rewritten[:50]}...")
            except Exception as e:
                logger.warning(f"Failed to rewrite sports news: {e}")
                rewritten = title

            message_lines.append("📰 <b>Спортивные новости:</b>")
            if url:
                message_lines.append(f'<a href="{url}">{rewritten}</a>')
            else:
                message_lines.append(rewritten)
            message_lines.append(f"<i>{source}</i>")
            message_lines.append("")
            logger.debug("✓ Sports news section added to digest")
        else:
            logger.debug("No sports news available for fallback")

    # Product Hunt — primary user only. Secondary users (skip_tasks=True) don't get
    # this section. Shown regardless of sports for the primary user.
    if skip_tasks:
        logger.info("Skipping Product Hunt for secondary user")
    else:
        logger.info("Fetching Product Hunt")
        try:
            product = await get_top_product()

            if product:
                message_lines.append("🚀 Product Hunt (новое на рынке):")
                message_lines.append(
                    f"<a href=\"{product['url']}\">{product['name']}</a>"
                )
                message_lines.append(product["description"][:150])
                message_lines.append("")
                logger.info(f"✓ Product Hunt shown: {product['name']}")
            else:
                logger.warning("Product Hunt fetch returned None")
        except Exception as e:
            logger.error(f"Failed to fetch Product Hunt: {e}")

    # Add Content recommendation (with timeout to prevent digest delays)
    logger.info("Fetching content recommendation (max 10s)")
    content = None
    try:
        if hasattr(asyncio, "timeout"):  # Python 3.11+
            async with asyncio.timeout(20):
                content = await get_content_recommendation(user_id=user_id)
        else:  # Python 3.10 and earlier
            content = await asyncio.wait_for(get_content_recommendation(user_id=user_id), timeout=20.0)
    except asyncio.TimeoutError:
        logger.warning("Content recommendation timed out (20s), skipping this section")
    except Exception as e:
        logger.warning(f"Failed to get content recommendation: {e}")

    content_type = None
    if not isinstance(content, Exception) and content:
        content_type = content.get("type")
        emoji = content.get("emoji", "📺")
        title = content.get("title", "")
        creator = content.get("creator", "")
        review = content.get("review", "")
        url = content.get("url", "")
        message_lines.append(f"<b>{emoji} Для вас</b> ({content['type']}):")
        message_lines.append(
            f'<a href="{url}"><b>{title}</b></a>' if url else f"<b>{title}</b>"
        )
        message_lines.append(f"<i>{creator}</i>")
        message_lines.append(review)
        message_lines.append("")

    # Add Album of the day (Spotify with AI recommendations)
    # Skip if content is already music (avoid duplicate music sections)
    album = None
    if content_type != "music":
        logger.info("Fetching album of the day")
        try:
            if hasattr(asyncio, "timeout"):  # Python 3.11+
                async with asyncio.timeout(15):
                    album = await get_album_of_day(user_id=user_id)
            else:  # Python 3.10 and earlier
                album = await asyncio.wait_for(get_album_of_day(user_id=user_id), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Album of the day timed out (15s), skipping")
        except Exception as e:
            logger.warning(f"Failed to get album of the day: {type(e).__name__}")
    else:
        logger.info("Skipping album of the day (content is already music)")

    if album and not isinstance(album, Exception):
        title = album.get("title", "")
        creator = album.get("creator", "")
        review = album.get("review", "")
        url = album.get("url", "")
        message_lines.append(f"<b>🎵 Альбом дня</b>:")
        message_lines.append(
            f'<a href="{url}"><b>{title}</b></a>' if url else f"<b>{title}</b>"
        )
        message_lines.append(f"<i>{creator}</i>")
        if review:
            message_lines.append(f"<i>{review}</i>")
        message_lines.append("")

    # Add fresh memes (1 per day, no AI summaries)
    logger.info("Fetching fresh memes")
    memes = await get_fresh_memes_for_digest(max_results=1)

    if memes:
        message_lines.append("<b>🎭 Мемы дня:</b>")
        for meme in memes:
            title = meme.get("title", "").strip()
            url = meme.get("url", "").strip()
            source = meme.get("source", "").strip()

            # Format: "Title (link) — Source"
            if url:
                message_lines.append(f'<a href="{url}">{title}</a> — {source}')
            else:
                message_lines.append(f"{title} — {source}")

        message_lines.append("")

    # Closing farewell line — AI-generated so it varies day to day (pairs with the greeting).
    # A random style is injected so the line doesn't converge to one template.
    logger.info("Generating farewell line")
    farewell = None
    try:
        import random as _random

        farewell_style = _random.choice([
            "с лёгким юмором или самоиронией",
            "с неожиданной метафорой (день как путешествие, кофе, плейлист, уровень в игре...)",
            "в духе напутствия из фильма или песни, но без прямых цитат",
            "как мини-афоризм, который хочется переслать другу",
            "с игривой отсылкой к сегодняшнему дню недели",
            "как будто прощается капитан корабля / пилот / бармен / диджей (выбери сам)",
        ])

        farewell_prompt = f"""Напиши ОДНО короткое, яркое и креативное прощальное предложение в конец утреннего дайджеста для человека по имени {user_name or 'друг'} ({user_gender} рода).

Сегодня {weekday_ru}. Стиль на сегодня: {farewell_style}.

Требования:
- Пожелай хорошего дня нестандартно — так, чтобы вызвать улыбку, а не вежливый кивок
- Можно обратиться по имени
- Никаких клише («заряд энергии», «ты можешь всё», «пусть день принесёт») и никакого официоза
- Не будь слащавым — лучше остроумно, чем умилительно
- Можно добавить один подходящий эмодзи в конце

Ответ — только текст прощания, строго одно предложение."""

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=90,
            temperature=1.0,
            messages=[
                {
                    "role": "system",
                    "content": "You are a witty, warm morning assistant in Russian.",
                },
                {"role": "user", "content": farewell_prompt},
            ],
        )
        farewell = (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning(f"Farewell generation failed: {type(e).__name__}: {str(e)[:100]}")

    if not farewell or len(farewell) < 5:
        farewell = f"Хорошего дня{name_part}! ✨"

    message_lines.append(farewell)
    message_lines.append("")

    final_message = "\n".join(message_lines)
    logger.info(
        f"Sending digest: {len(message_lines)} lines, {len(final_message)} chars to chat {chat_id}"
    )

    # Check Telegram message length limit
    if len(final_message) > TELEGRAM_MESSAGE_CHAR_LIMIT:
        logger.warning(
            f"⚠️  Digest message exceeds limit ({len(final_message)}/{TELEGRAM_MESSAGE_CHAR_LIMIT}), splitting..."
        )
        # Split by major sections - ensure each part <= 4000 chars
        parts = []
        current_part = []
        current_length = 0

        for line in message_lines:
            # Actual length when joined: line + newline (except for last line in part)
            # Conservative estimate: add newline for each line
            line_with_newline = len(line) + 1

            # If adding this line would exceed limit and we have content, save current part
            if current_length + line_with_newline > TELEGRAM_MESSAGE_CHAR_LIMIT and current_part:
                joined = "\n".join(current_part)
                actual_len = len(joined)

                # Safety check: ensure part doesn't exceed limit
                if actual_len > TELEGRAM_MESSAGE_CHAR_LIMIT:
                    logger.error(f"⚠️  Part exceeds limit: {actual_len}/{TELEGRAM_MESSAGE_CHAR_LIMIT}")

                parts.append(joined)
                current_part = [line]
                # Recalculate for new part
                current_length = line_with_newline
            else:
                current_part.append(line)
                current_length += line_with_newline

        # Save final part
        if current_part:
            joined = "\n".join(current_part)
            actual_len = len(joined)

            # Safety check
            if actual_len > TELEGRAM_MESSAGE_CHAR_LIMIT:
                logger.error(f"⚠️  Final part exceeds limit: {actual_len}/{TELEGRAM_MESSAGE_CHAR_LIMIT}")

            parts.append(joined)

        logger.info(f"Split into {len(parts)} messages")
        for i, part in enumerate(parts, 1):
            actual_len = len(part)
            logger.info(f"Sending part {i}/{len(parts)} ({actual_len}/{TELEGRAM_MESSAGE_CHAR_LIMIT} chars)")

            await bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info(f"✓ Sent part {i}/{len(parts)}")
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=final_message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info(f"✓ Digest sent in single message")

    logger.info(f"✓✓ Morning digest sent successfully for user {user_id}")


def _format_weather(weather: dict, city_prep: str = "Тбилиси") -> str:
    """Format weather data by periods (morning/day/evening/night) with emojis."""
    if not weather:
        return "неизвестная погода"

    if not isinstance(weather, dict):
        return "неизвестная погода"

    # If it's old format (single dict with temperature), convert to string
    if "temperature" in weather and not isinstance(weather.get("morning"), dict):
        temp = weather.get("temperature", "?")
        conditions = []
        if weather.get("is_raining"):
            conditions.append("дождь")
        if weather.get("is_very_cold"):
            conditions.append("холодно")
        if weather.get("is_very_hot"):
            conditions.append("жарко")
        condition_str = ", ".join(conditions) if conditions else "переменная облачность"
        return f"{condition_str}, {temp}°C"

    # New format: by periods (with emojis)
    lines = [f"Погода в {city_prep}:"]

    periods = {
        "morning": "Утро",
        "day": "День",
        "evening": "Вечер",
        "night": "Ночь",
    }

    for period_key, period_label in periods.items():
        if period_key in weather:
            p = weather[period_key]
            emoji = p.get("emoji", "🌤️")
            condition = p.get("condition", "переменная облачность")
            temp = p.get("temperature", "?")
            lines.append(f"{emoji} {period_label}: {condition}, {temp}°C")

    return "\n".join(lines)


async def check_precipitation_alert(bot: Bot, chat_id: int):
    """Check for upcoming precipitation in next 3 hours and send alert if found."""
    global _last_precipitation_alert

    # Cooldown: don't send more than once per 3 hours
    if _last_precipitation_alert and (
        datetime.now() - _last_precipitation_alert
    ) < timedelta(hours=3):
        return

    try:
        precip = await get_upcoming_precipitation(hours=3)
        if not precip:
            return

        # Precipitation detected
        condition = precip.get("condition", "осадки")
        emoji = precip.get("emoji", "🌧️")
        hours_from_now = precip.get("hours_from_now", 0)
        time_str = precip.get("time", "")

        # Build message
        message = f"{emoji} Через ~{hours_from_now} ч. ожидается {condition}"
        if time_str:
            message += f" (около {time_str})"

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            disable_web_page_preview=True,
        )

        _last_precipitation_alert = datetime.now()
        logger.info(f"✓ Precipitation alert sent: {condition} in ~{hours_from_now}h")

    except Exception as e:
        logger.warning(f"Precipitation alert failed: {e}")




def _get_secondary_users() -> list:
    """
    Get list of secondary users from TELEGRAM_SECONDARY_USERS env var (JSON format).

    Format: TELEGRAM_SECONDARY_USERS=[user_id1, user_id2, ...]
    Example: [184010236, 498233237]

    Default: [184010236, 498233237] (hardcoded digest recipients without tasks)
    """
    # Hardcoded default secondary users
    DEFAULT_SECONDARY_USERS = [184010236, 498233237]

    try:
        users_json = get_secret("TELEGRAM_SECONDARY_USERS")

        # Default: if not configured, return hardcoded list
        if not users_json or users_json.strip() in ("", "[]", "null", "None"):
            logger.info(f"TELEGRAM_SECONDARY_USERS not configured, using hardcoded default: {DEFAULT_SECONDARY_USERS}")
            return DEFAULT_SECONDARY_USERS

        # Parse JSON
        users = json.loads(users_json)

        # Ensure it's a list
        if not isinstance(users, list):
            logger.warning(f"TELEGRAM_SECONDARY_USERS is not a list, got {type(users).__name__}, using default: {DEFAULT_SECONDARY_USERS}")
            return DEFAULT_SECONDARY_USERS

        logger.info(f"✓ Loaded {len(users)} secondary users for digest: {users}")
        return users

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse TELEGRAM_SECONDARY_USERS as JSON: {e}, using default: {DEFAULT_SECONDARY_USERS}")
        return DEFAULT_SECONDARY_USERS
    except Exception as e:
        logger.debug(f"Failed to load secondary users: {type(e).__name__}: {e}, using default: {DEFAULT_SECONDARY_USERS}")
        return DEFAULT_SECONDARY_USERS


def init_scheduler(bot: Bot, user_id: int, chat_id: int = None):
    """Initialize APScheduler with morning digest for primary and secondary users."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler

    # Initialize scheduler with Asia/Tbilisi timezone
    tbilisi_tz = timezone("Asia/Tbilisi")
    scheduler = AsyncIOScheduler(timezone=tbilisi_tz)

    # Morning digest at 08:00 Tbilisi time for primary user (with tasks)
    scheduler.add_job(
        morning_digest,
        CronTrigger(hour=8, minute=0, timezone=tbilisi_tz),
        args=[bot, user_id, chat_id, False, False],  # skip_sports=False, skip_tasks=False
        id="morning_digest",
        name="Morning digest (primary user)",
    )

    # Morning digest for secondary users (without tasks)
    secondary_users = _get_secondary_users()
    for i, secondary_user_id in enumerate(secondary_users):
        secondary_chat_id = secondary_user_id  # Use user_id as chat_id for secondary users
        scheduler.add_job(
            morning_digest,
            CronTrigger(hour=8, minute=0, timezone=tbilisi_tz),
            args=[bot, secondary_user_id, secondary_chat_id, True, True],  # skip_sports=True, skip_tasks=True
            id=f"morning_digest_secondary_{secondary_user_id}",
            name=f"Morning digest (secondary user {secondary_user_id})",
        )
        logger.info(f"  ✓ Secondary digest scheduled for user {secondary_user_id} (without tasks/sports)")

    # Update historical forex rates every 1 hour (for digest)
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        _update_historical_forex_cache,
        IntervalTrigger(hours=1),
        id="update_forex_cache",
        name="Update historical forex rates",
    )

    # Hourly precipitation alert check
    scheduler.add_job(
        check_precipitation_alert,
        CronTrigger(minute=0, timezone=tbilisi_tz),  # every hour at :00 Tbilisi time
        args=[bot, chat_id],
        id="precipitation_alert",
        name="Hourly precipitation check",
    )

    primary_digest = "primary user (with tasks)"
    secondary_count = len(secondary_users)
    secondary_str = f", {secondary_count} secondary user(s) (without tasks)" if secondary_count > 0 else ""
    logger.info(
        f"Scheduler initialized with: morning digest (08:00 - {primary_digest}{secondary_str}), forex cache update (hourly), precipitation alerts (hourly)"
    )
    return scheduler
