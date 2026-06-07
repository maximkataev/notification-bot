"""APScheduler setup for morning digest."""

import asyncio
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
from src.ai.weather_sources import get_aggregated_weather, generate_clothing_recommendation
from src.workers.news_fetcher import (
    get_politics_economy_news,
    get_sports_news,
    get_technology_news,
    get_culture_science_news,
    get_good_news,
)
from src.ai.news_processor import select_and_summarize_news_with_gpt, select_good_news_with_summaries
from src.workers.gwp_checker import check_gwp_works, check_water_cuts
from src.workers.subscriptions_checker import check_expiring_subscriptions
from src.workers.rates_fetcher import (
    get_crypto_and_forex_rates,
    _update_historical_forex_cache,
)
from src.ai.task_explainer import get_task_explanations
from src.workers.holidays import get_today_holidays, get_today_events
from src.workers.air_quality import get_air_quality_tbilisi
from src.workers.product_hunt import get_top_product
from src.workers.content_recommender import get_content_recommendation
from src.workers.content_parser import get_album_of_day
from src.workers.quote_of_day import get_quote_of_day
from src.workers.football_matches import get_today_matches, get_formatted_matches, get_yesterday_results, get_formatted_results
from src.workers.forex_multi_source import get_eur_usd_multi_source
from src.workers.meme_fetcher import get_fresh_memes_for_digest
from src.workers.precipitation_checker import get_upcoming_precipitation
from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram

logger = logging.getLogger(__name__)

# Constants
MORNING_DIGEST_TIMEOUT_SECONDS = 300
TELEGRAM_MESSAGE_CHAR_LIMIT = 4000
WEATHER_JACKET_THRESHOLD_C = 10
PRECIPITATION_ALERT_COOLDOWN_HOURS = 3

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

    logger.info(f"Loading tasks, profile, weather for user {user_id} (include_tasks={include_tasks})")

    # Parallel API calls - much faster than sequential
    # Only load tasks if include_tasks=True
    gather_tasks = [
        get_user_profile(user_id),
        get_aggregated_weather(),
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
    weather_desc = _format_weather(weather) if weather else "неизвестная погода"
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

    intro_prompt = f"""Напиши мне теплое утреннее приветствие (2-3 предложения):

📌 СУТЬ приветствия:
- Дружелюбное и поддерживающее
- Как будто знакомый человек, который рад тебя видеть
- Плавно подведи меня от "хорошего утра" к "давай начнем день"
- Это переход от сна к активности - спокойный, но мотивирующий

🚫 НЕ ИСПОЛЬЗУЙ:
- Клише: "начни день с улыбки", "ты можешь всё", "зарядит энергией"
- Странные фразы про кофе/чай
- Метафоры про "свеженность" и "воскрешение"
- Официозный тон
- Пустые мотивационные фразы

✅ СТИЛЬ:
- Личный контакт: можно "ты", теплая интонация, подбадривающие слова
- Практичность: учти погоду, подготовься к дню
- Лёгкий юмор или наблюдение, если уместно

🌡️ КОНТЕКСТ:
Погода в Тбилиси: {weather_desc}
{weather_details}

Напиши приветствие естественно, как письмо другу, которое начинается с "Привет" и заканчивается готовностью начать день. Ты пишешь человеку мужского пола, который просыпается в Тбилиси и видит такую погоду. Учитывай это в тоне и содержании приветствия."""  # noqa: E501

    logger.info("🔄 Calling AI to generate morning greeting and weather advice")

    response = await get_client().chat.completions.create(
        model="gpt-5.4-mini",
        max_completion_tokens=250,
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
    simple_greeting = response_text.strip() if response_text else "Доброе утро! Вот и началось новое утро - давай начнём день."

    if not simple_greeting or len(simple_greeting) < 10:
        logger.error("❌ AI returned incomplete response, using fallback")
        simple_greeting = "Доброе утро! Вот и началось новое утро. Кофе, завтрак, планы — и можно начинать день."

    # AI-based clothing recommendation with jacket validation
    # (Replaces old rule-based logic that didn't account for temperature < 10°C)
    outfit_advice = await generate_clothing_recommendation(weather, is_raining=is_raining)

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
        message_lines.append(f"✨ <i>\"{quote['text']}\"</i>")
        message_lines.append(f"<i>— {quote['author']}</i>")
        message_lines.append("")
    else:
        logger.warning("Quote fetch failed")

    # Add outfit recommendation
    message_lines.append(f"👕 {outfit_advice}")
    message_lines.append("")

    # Add weather by periods
    logger.info("Formatting weather by periods")
    if weather:
        weather_str = _format_weather(weather)
        message_lines.append(weather_str)
        message_lines.append("")
    else:
        message_lines.append("Погода недоступна")
        message_lines.append("")

    # Add air quality in Tbilisi
    logger.info("Fetching air quality")
    air_quality = await get_air_quality_tbilisi()
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

    # Check Google Sheet for expiring VPS / domains (within 7 days)
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

    # Check if this is a secondary user without tasks (and not user 71488343)
    is_secondary_no_tasks = skip_tasks and user_id != 71488343

    if total_news > 0:
        if is_secondary_no_tasks:
            # For secondary users without tasks: show only 6 good news with summaries
            if goodness_news:
                logger.info(f"Secondary user {user_id} without tasks: using good news selection ({len(goodness_news)} items)")
                selected_with_indices = await select_good_news_with_summaries(goodness_news)
            else:
                logger.warning(f"Secondary user {user_id}: no good news available, fallback to standard selection")
                selected_with_indices = await select_and_summarize_news_with_gpt(
                    politics_news,
                    sports_news,
                    technology_news,
                    culture_news,
                    goodness_news,
                    user_id,
                )
        else:
            # Standard news selection for primary user or user 71488343
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

            # Build combined news list for index matching
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

            for i, item in enumerate(selected_with_indices, 1):
                idx = item["index"]
                category = item["category"]
                description_ru = item.get("description_ru", "")

                # For good news selection, adjust index to combined array offset
                if is_secondary_no_tasks and category == "goodness":
                    combined_idx = idx + goodness_offset
                else:
                    combined_idx = idx

                # Get original news item by index (with safety check)
                if 0 <= combined_idx < len(all_news):
                    original_news = all_news[combined_idx]
                    source = original_news.get("source", "Unknown")
                    url = original_news.get("url", "")

                    # Format: <a href="url">Source</a>: description_ru (full, complete text)
                    news_text = (
                        f'{i}. <a href="{url}">{source}</a>: {description_ru}'
                        if url
                        else f"{i}. {source}: {description_ru}"
                    )

                    message_lines.append(news_text)
                    message_lines.append("")

                    logger.info(
                        f"  [{i}] {category}: {description_ru[:60]}... | {source}"
                    )
                else:
                    logger.warning(f"Invalid index {combined_idx} for news selection, skipping")

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

    # Tasks section (only if include_tasks=True)
    if include_tasks:
        # Tasks are already filtered by database to when_date <= today or NULL
        # Just use them as-is (no additional date filtering needed)
        today_tasks = tasks
        logger.info(f"Tasks loaded: {len(today_tasks)} tasks ready for today")

        # Get AI explanations and priority ranking for tasks
        task_explanations = {}
        if today_tasks:
            # Convert profile to dict for AI context
            profile_dict = None
            if user_profile:
                profile_dict = {
                    "wake_time": user_profile.wake_time,
                    "sleep_time": user_profile.sleep_time,
                    "preferences": user_profile.preferences,
                    "timezone": user_profile.timezone,
                }

            explanations_result = await get_task_explanations(
                today_tasks, weather=weather, profile=profile_dict
            )
            if not isinstance(explanations_result, Exception):
                task_explanations = explanations_result
                logger.info(f"Generated explanations for {len(task_explanations)} tasks")
            else:
                logger.warning(
                    f"Failed to generate task explanations: {explanations_result}"
                )

        # Sort tasks by GPT priority rank
        def _get_gpt_rank(task) -> int:
            return task_explanations.get(task.id, {}).get("priority_rank", 999)

        today_tasks_sorted = sorted(today_tasks, key=_get_gpt_rank)
        logger.info(f"Sorted {len(today_tasks_sorted)} tasks by GPT priority rank")

        # Process and organize tasks
        if today_tasks_sorted:
            # Separate urgent and non-urgent tasks (check both is_urgent flag and keywords)
            urgent_tasks = sorted(
                [
                    t
                    for t in today_tasks_sorted
                    if t.is_urgent or _is_task_urgent_by_keywords(t)
                ],
                key=_get_gpt_rank,
            )
            non_urgent_tasks = sorted(
                [
                    t
                    for t in today_tasks_sorted
                    if not t.is_urgent and not _is_task_urgent_by_keywords(t)
                ],
                key=_get_gpt_rank,
            )

            def _format_task_with_analysis(task, task_data, is_urgent=False):
                """Format task with AI-generated digest description (up to 280 chars)."""
                name = task.what or task.raw_text[:50]
                time_minutes = task_data.get("time_minutes", 30)
                importance = task_data.get("importance", 2)
                digest_description = task_data.get("digest_description", "")

                # Importance label
                importance_map = {1: "низко", 2: "средне", 3: "важно", 4: "очень важно", 5: "критично"}
                importance_label = importance_map.get(importance, "средне")

                # Title with metrics
                title = f"• {name} ({time_minutes} мин"
                if is_urgent:
                    title += ", срочно"
                else:
                    title += f", {importance_label}"
                title += ")"

                lines = [title]
                if digest_description:
                    lines.append(digest_description)

                return "\n".join(lines)

            # Show urgent tasks
            if urgent_tasks:
                message_lines.append("СРОЧНЫЕ:")
                for task in urgent_tasks:
                    task_data = task_explanations.get(task.id, {})
                    formatted = _format_task_with_analysis(task, task_data, is_urgent=True)
                    message_lines.append(formatted)
                    message_lines.append("")
                    logger.info(f"  Urgent: {task.what or task.raw_text[:30]}")
                message_lines.append("")

            # Show all non-urgent tasks if available
            if non_urgent_tasks:
                message_lines.append("НЕСРОЧНЫЕ ЗАДАЧИ:")
                for task in non_urgent_tasks:
                    task_data = task_explanations.get(task.id, {})
                    formatted = _format_task_with_analysis(task, task_data, is_urgent=False)
                    message_lines.append(formatted)
                    message_lines.append("")
                    logger.info(f"  Non-urgent: {task.what or task.raw_text[:30]}")
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
        message_lines.append("Курсы валют:")

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

        # BTC
        if rates.get("btc_usd"):
            btc_str = format_currency(rates["btc_usd"], decimals=5)
            change_str = format_change(
                rates.get("btc_change_24h"), rates.get("btc_change_30d")
            )
            message_lines.append(f"BTC: {btc_str} USD{change_str}")

        # ETH
        if rates.get("eth_usd"):
            eth_str = format_currency(rates["eth_usd"], decimals=5)
            change_str = format_change(
                rates.get("eth_change_24h"), rates.get("eth_change_30d")
            )
            message_lines.append(f"ETH: {eth_str} USD{change_str}")

        # EUR (multi-source)
        eur_multi = await get_eur_usd_multi_source()
        if eur_multi:
            source1 = eur_multi.get("eur_usd_source1")
            source2 = eur_multi.get("eur_usd_source2")
            avg = eur_multi.get("eur_usd_avg")

            if source1:
                source1_str = format_currency(source1, decimals=5)
                message_lines.append(f"EUR (ExchangeRate): {source1_str} USD")
            if source2:
                source2_str = format_currency(source2, decimals=5)
                message_lines.append(f"EUR (ECB): {source2_str} USD")
            if avg and rates.get("eur_change_24h") is not None:
                eur_str = format_currency(avg, decimals=5)
                change_str = format_change(
                    rates.get("eur_change_24h"), rates.get("eur_change_30d")
                )
                message_lines.append(f"EUR (avg): {eur_str} USD{change_str}")

        # RUB
        if rates.get("usd_rub"):
            rub_str = format_currency(rates["usd_rub"], decimals=2)
            logger.debug(
                f"RUB rates: usd_rub={rates.get('usd_rub')}, rub_change_24h={rates.get('rub_change_24h')}, rub_change_30d={rates.get('rub_change_30d')}"
            )
            change_str = format_change(
                rates.get("rub_change_24h"), rates.get("rub_change_30d")
            )
            message_lines.append(f"USD: {rub_str} RUB{change_str}")

        message_lines.append("")
    else:
        logger.info("Failed to fetch rates")

    # Check for water cuts on Vazha Ivereli street
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

        # Always show Product Hunt
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
                content = await get_content_recommendation()
        else:  # Python 3.10 and earlier
            content = await asyncio.wait_for(get_content_recommendation(), timeout=20.0)
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


def _format_weather(weather: dict) -> str:
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
    lines = ["Погода в Тбилиси:"]

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
        message += f"\n💧 {condition}"

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            disable_web_page_preview=True,
        )

        _last_precipitation_alert = datetime.now()
        logger.info(f"✓ Precipitation alert sent: {condition} in ~{hours_from_now}h")

    except Exception as e:
        logger.warning(f"Precipitation alert failed: {e}")




async def tbilisi_events_digest(bot: Bot, chat_id: int = None):
    """Send weekly events digest for Tbilisi (Saturday 18:00)."""
    try:
        logger.info(f"📅 Starting Tbilisi events digest")

        # Fetch events for next 7 days
        events = await get_tbilisi_events(days_ahead=7)

        if not events:
            message = "На следующую неделю в Тбилиси пока ничего интересного не найдено 🤔"
        else:
            message = format_events_for_telegram(events)

        if chat_id is None:
            chat_id = int(get_secret("TELEGRAM_CHAT_ID"))

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

        logger.info(f"✓ Tbilisi events digest sent ({len(events)} events)")

    except Exception as e:
        logger.error(f"❌ Tbilisi events digest failed: {e}", exc_info=True)
        try:
            if chat_id is None:
                chat_id = int(get_secret("TELEGRAM_CHAT_ID"))

            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка при загрузке событий: {str(e)[:100]}",
                disable_web_page_preview=True,
            )
        except Exception as inner_e:
            logger.error(f"Failed to send error message: {inner_e}")


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
            args=[bot, secondary_user_id, secondary_chat_id, False, True],  # skip_sports=False, skip_tasks=True
            id=f"morning_digest_secondary_{secondary_user_id}",
            name=f"Morning digest (secondary user {secondary_user_id})",
        )
        logger.info(f"  ✓ Secondary digest scheduled for user {secondary_user_id} (without tasks)")

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

    # Weekly Tbilisi events digest on Saturday at 18:00 Tbilisi time
    scheduler.add_job(
        tbilisi_events_digest,
        CronTrigger(day_of_week=5, hour=18, minute=0, timezone=tbilisi_tz),  # Saturday 18:00
        args=[bot, chat_id],
        id="tbilisi_events_digest",
        name="Tbilisi events digest",
    )

    primary_digest = "primary user (with tasks)"
    secondary_count = len(secondary_users)
    secondary_str = f", {secondary_count} secondary user(s) (without tasks)" if secondary_count > 0 else ""
    logger.info(
        f"Scheduler initialized with: morning digest (08:00 - {primary_digest}{secondary_str}), forex cache update (hourly), precipitation alerts (hourly), Tbilisi events (Sat 18:00)"
    )
    return scheduler
