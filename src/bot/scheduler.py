"""APScheduler setup for morning digest."""

import asyncio
import logging
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
from src.ai.weather_aggregator import get_aggregated_weather
from src.workers.news_fetcher import (
    get_politics_economy_news,
    get_sports_news,
    get_technology_news,
    get_culture_science_news,
    get_good_news,
)
from src.ai.news_processor import select_and_summarize_news_with_gpt
from src.workers.gwp_checker import check_gwp_works, check_water_cuts
from src.workers.rates_fetcher import (
    get_crypto_and_forex_rates,
    _update_historical_forex_cache,
)
from src.ai.task_explainer import get_task_explanations, score_task_importance
from src.workers.holidays import get_today_holidays, get_today_events
from src.workers.air_quality import get_air_quality_tbilisi
from src.workers.product_hunt import get_top_product
from src.workers.content_recommender import get_content_recommendation
from src.workers.quote_of_day import get_quote_of_day
from src.workers.football_matches import get_today_matches
from src.workers.football_analyzer import get_match_analysis
from src.workers.match_context import get_extended_match_analysis
from src.workers.forex_multi_source import get_eur_usd_multi_source
from src.workers.meme_fetcher import get_fresh_memes_for_digest
from src.workers.precipitation_checker import get_upcoming_precipitation
from src.workers.tbilisi_events import get_tbilisi_events, format_events_for_telegram

logger = logging.getLogger(__name__)

# Constants
MORNING_DIGEST_TIMEOUT_SECONDS = 120
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
        logger.error(f"Failed to load {name}", exc_info=result)
        return None
    return result


async def morning_digest(bot: Bot, user_id: int, chat_id: int = None):
    """Send morning digest: intro + news + task list with timeout and error handling."""
    logger.info(f"🌅 Starting morning digest for user {user_id}")

    try:
        # Set global timeout for entire digest (120 seconds = 2 minutes for all API calls)
        try:
            if hasattr(asyncio, "timeout"):  # Python 3.11+
                async with asyncio.timeout(120):
                    await _morning_digest_impl(bot, user_id, chat_id)
            else:  # Python 3.10 and earlier
                await asyncio.wait_for(
                    _morning_digest_impl(bot, user_id, chat_id),
                    timeout=MORNING_DIGEST_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            logger.error(f"❌ Morning digest exceeded 120s timeout for user {user_id}")
            try:
                if chat_id is None:
                    chat_id = get_secret("TELEGRAM_CHAT_ID")
                await bot.send_message(
                    chat_id=chat_id,
                    text="🌅 Доброе утро! (дайджест не готов - превышен timeout)",
                    disable_web_page_preview=True,
                )
            except Exception as fallback_err:
                logger.error(f"Failed to send timeout fallback message: {fallback_err}")

    except Exception as e:
        logger.error(f"❌ Morning digest failed for user {user_id}")
        logger.error(f"  Exception type: {type(e).__name__}")
        logger.error(f"  Exception message: {e}")
        logger.error(f"  Full details:", exc_info=True)
        try:
            if chat_id is None:
                chat_id = get_secret("TELEGRAM_CHAT_ID")
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Дайджест не отправлен: {type(e).__name__}",
                disable_web_page_preview=True,
            )
        except Exception as fallback_err:
            logger.error(f"Failed to send error fallback message: {fallback_err}")


async def _morning_digest_impl(bot: Bot, user_id: int, chat_id: int = None, include_tasks: bool = True):
    """Implementation of morning digest (called with timeout)."""
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
    if weather and isinstance(weather, dict):
        # Get temperature from any period (morning/day/evening/night)
        temp = None
        for period in ["morning", "day", "evening", "night"]:
            if isinstance(weather.get(period), dict):
                temp = weather[period].get("temperature")
                if temp:
                    break

        # Check for precipitation (new: use precipitation_mm instead of condition string)
        is_raining = any(
            isinstance(weather.get(period), dict)
            and weather[period].get("precipitation_mm", 0) > 0
            for period in ["morning", "day", "evening"]
        )

        weather_details = f"Температура: {temp}°C" if temp else ""
        if is_raining:
            weather_details += (
                " (ожидаются осадки)" if weather_details else "Ожидаются осадки"
            )

    intro_prompt = f"""Напиши мне утренний привет и совет про погоду в два этапа:

1️⃣ ПРОСТОЙ ПРИВЕТ (одна строка):
Простое, ясное приветствие. БЕЗ клише и странных метафор.
НЕ используй: "пусть день принесет", "улучшит настроение", "зарядит энергией", странные фразы про кофе
ИСПОЛЬЗУЙ: обычный язык, может быть с лёгким юмором или наблюдением

Примеры:
- "Доброе утро! Кофе в руках, можно работать"
- "Утро, солнце на улице, давай начнём"
- "Доброе утро! День начинается"

2️⃣ СОВЕТ ПРО ПОГОДУ (1-2 предложения):
От первого лица (я вижу, я советую) - практичный совет связанный с погодой.
Погода в Тбилиси: {weather_desc}

Стиль: просто, понятно, практично.

{weather_details}

Формат ответа - ДВЕ СТРОКИ:
[простой привет]
[совет про погоду]"""

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

    # Parse response - should be two lines
    lines = response_text.strip().split("\n") if response_text else []
    simple_greeting = lines[0] if len(lines) > 0 else "Доброе утро!"
    weather_advice = lines[1] if len(lines) > 1 else "Подготовьтесь к предстоящему дню."

    if not simple_greeting or not weather_advice:
        logger.error("❌ AI returned incomplete response, using fallback")
        simple_greeting = "Доброе утро!"
        weather_advice = "Подготовьтесь к переменчивой погоде."

    # Compute clothing recommendation based on weather rules (not AI)
    morning_temp = None
    if weather and isinstance(weather.get("morning"), dict):
        morning_temp = weather["morning"].get("temperature")

    # Jacket needed if: temp below threshold OR precipitation expected
    needs_jacket = (
        morning_temp is not None and morning_temp < WEATHER_JACKET_THRESHOLD_C
    ) or is_raining
    outer_layer = "куртку" if needs_jacket else "худи"
    outfit_advice = f"Штаны, кофта, {outer_layer}, кроссовки"

    logger.info(
        f"✓ Generated - greeting: {simple_greeting[:50]}... | advice: {weather_advice[:50]}... | outfit: {outfit_advice}"
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

    # Add AI weather advice and outfit recommendation
    message_lines.append(weather_advice)
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

    if total_news > 0:
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

            # Match indices back to original news items and format with URLs
            message_lines.append("Новости:")
            message_lines.append("")

            for i, item in enumerate(selected_with_indices, 1):
                idx = item["index"]
                category = item["category"]
                description_ru = item.get("description_ru", "")

                # Get original news item by index (with safety check)
                if 0 <= idx < len(all_news):
                    original_news = all_news[idx]
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
                    logger.warning(f"Invalid index {idx} for news selection, skipping")

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

        # Sort tasks by importance
        today_tasks_sorted = sorted(today_tasks, key=score_task_importance, reverse=True)
        logger.info(f"Sorted {len(today_tasks_sorted)} tasks by importance")

        # Get AI explanations for tasks with weather and profile context
        task_explanations = {}
        if today_tasks_sorted:
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
                today_tasks_sorted, weather=weather, profile=profile_dict
            )
            if not isinstance(explanations_result, Exception):
                task_explanations = explanations_result
                logger.info(f"Generated explanations for {len(task_explanations)} tasks")
            else:
                logger.warning(
                    f"Failed to generate task explanations: {explanations_result}"
                )

        # Process and organize tasks
        if today_tasks_sorted:
            # Separate urgent and non-urgent tasks (check both is_urgent flag and keywords)
            urgent_tasks = [
                t
                for t in today_tasks_sorted
                if t.is_urgent or _is_task_urgent_by_keywords(t)
            ]
            non_urgent_tasks = [
                t
                for t in today_tasks_sorted
                if not t.is_urgent and not _is_task_urgent_by_keywords(t)
            ]

            # Show urgent tasks
            if urgent_tasks:
                message_lines.append(f"СРОЧНЫЕ ({len(urgent_tasks)} задач):")
                for task in urgent_tasks:
                    name = task.what or task.raw_text[:50]
                    task_data = task_explanations.get(task.id, {})
                    explanation = task_data.get("explanation", "")
                    time_minutes = task_data.get("time_minutes", 30)

                    message_lines.append(f"• {name} ({time_minutes} мин)")
                    if explanation:
                        message_lines.append(f"  └ {explanation}")

                    logger.info(f"  Urgent task: {name} | {time_minutes}min")

                message_lines.append("")

            # Show non-urgent tasks if available
            if non_urgent_tasks:
                message_lines.append(f"НЕСРОЧНЫЕ (если захочешь взяться):")
                display_non_urgent = non_urgent_tasks[:3]  # Show top 3 non-urgent

                if len(non_urgent_tasks) > 3:
                    message_lines.append(
                        f"(показаны 3 из {len(non_urgent_tasks)} несрочных)\n"
                    )

                for task in display_non_urgent:
                    name = task.what or task.raw_text[:50]
                    task_data = task_explanations.get(task.id, {})
                    explanation = task_data.get("explanation", "")
                    time_minutes = task_data.get("time_minutes", 30)

                    message_lines.append(f"• {name} ({time_minutes} мин)")
                    if explanation:
                        message_lines.append(f"  └ {explanation}")

                    logger.info(f"  Non-urgent task: {name} | {time_minutes}min")

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

    # Check for football matches (Barcelona/Real Madrid/PSG priority)
    logger.info("Checking for football matches today")
    football_matches = await get_today_matches()
    product = None

    if football_matches and football_matches.get("matches"):
        # Show football matches instead of Product Hunt
        matches = football_matches["matches"]
        logger.info(f"✓ Found {len(matches)} football match(es)")

        # Get AI analysis for matches
        logger.info("Generating AI commentary for matches")
        match_analysis = await get_match_analysis(matches, max_matches=3)
        logger.info(f"✓ Generated commentary for {len(match_analysis)} matches")

        message_lines.append("⚽ <b>Матчи сегодня</b>:")
        message_lines.append("")

        for i, match in enumerate(matches):
            home = match.get("home", "Unknown")
            away = match.get("away", "Unknown")
            time = match.get("time", "TBD")
            league = match.get("league", "")
            home_flag = match.get("home_flag", "⚽")
            away_flag = match.get("away_flag", "⚽")

            message_lines.append(f"{home_flag} {home} vs {away} {away_flag}")
            # Include timezone info for clarity (Tbilisi time zone)
            message_lines.append(f"<i>{league}</i> • {time} Tbilisi (GMT+4)")

            # Get extended match context (standings, odds, form)
            league_codes = {
                "La Liga": ("LA", 140),
                "Premier League": ("PL", 39),
                "Ligue 1": ("FL1", 61),
            }
            league_info = league_codes.get(league, ("", None))
            league_code, league_id = league_info

            if league_code:
                try:
                    context = await get_extended_match_analysis(
                        home, away, league, league_code, league_id
                    )
                    if context:
                        message_lines.append(f"📊 {context}")
                except Exception as e:
                    logger.debug(f"Failed to get extended analysis: {e}")

            # Add AI commentary if available
            if i in match_analysis:
                commentary = match_analysis[i]
                message_lines.append(f"💭 {commentary}")

            message_lines.append("")

        logger.info(f"Displayed {len(matches)} matches with AI commentary")
    else:
        # No matches - show sports news + Product Hunt together
        logger.info("No football matches found, showing sports news + Product Hunt")

        # Show top sports news
        if sports_news and len(sports_news) > 0:
            logger.info(f"Showing top sports news")
            message_lines.append("📰 <b>Спортивные новости</b>:")
            message_lines.append("")

            for i, news in enumerate(sports_news[:1]):  # Just 1 top story
                title = news.get("title", "")
                url = news.get("url", "")
                source = news.get("source", "")

                if url:
                    message_lines.append(f'<a href="{url}">{title}</a>')
                else:
                    message_lines.append(title)

                message_lines.append(f"<i>{source}</i>")
                message_lines.append("")
        else:
            logger.debug("No sports news available")

        # Always show Product Hunt as well
        logger.info("Fetching Product Hunt")
        try:
            product = await get_top_product()

            if product:
                message_lines.append("🚀 <b>Product Hunt</b> (новое на рынке):")
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

    if not isinstance(content, Exception) and content:
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
        # Split by major sections
        parts = []
        current_part = []
        current_length = 0

        for line in message_lines:
            line_len = len(line) + 1  # +1 for newline
            if current_length + line_len > TELEGRAM_MESSAGE_CHAR_LIMIT and current_part:
                parts.append("\n".join(current_part))
                current_part = [line]
                current_length = line_len
            else:
                current_part.append(line)
                current_length += line_len

        if current_part:
            parts.append("\n".join(current_part))

        logger.info(f"Split into {len(parts)} messages")
        for i, part in enumerate(parts, 1):
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
    """Format weather data by periods (morning/day/evening/night) with emojis and conditions."""
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

    # New format: by periods
    lines = ["🌦️ Погода в Тбилиси:"]

    periods = {
        "morning": "Утро",
        "day": "День",
        "evening": "Вечер",
        "night": "Ночь",
    }

    for period_key, period_label in periods.items():
        if period_key in weather:
            p = weather[period_key]
            emoji = p.get("emoji", "🌥️")
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


async def morning_digest_both_users(bot: Bot, user_id: int, chat_id: int = None):
    """Send morning digest to both main user and secondary user."""
    logger.info(f"Sending morning digest to both users")

    # Send to main user with tasks
    await morning_digest(bot, user_id, chat_id)

    # Send to secondary user (498233237) without tasks
    secondary_user_id = 498233237
    await _morning_digest_impl(bot, user_id, chat_id=secondary_user_id, include_tasks=False)


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


def init_scheduler(bot: Bot, user_id: int, chat_id: int = None):
    """Initialize APScheduler with morning digest."""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler

    # Initialize scheduler with Asia/Tbilisi timezone
    tbilisi_tz = timezone("Asia/Tbilisi")
    scheduler = AsyncIOScheduler(timezone=tbilisi_tz)

    # Morning digest at 08:00 Tbilisi time (to both users)
    scheduler.add_job(
        morning_digest_both_users,
        CronTrigger(hour=8, minute=0, timezone=tbilisi_tz),
        args=[bot, user_id, chat_id],
        id="morning_digest",
        name="Morning digest (both users)",
    )

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

    logger.info(
        "Scheduler initialized with: morning digest (08:00), forex cache update (hourly), precipitation alerts (hourly), Tbilisi events (Sat 18:00)"
    )
    return scheduler
