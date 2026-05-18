"""AI-powered task planning agent using OpenAI gpt-5.4-mini."""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
from src.db.models import Task, UserProfile
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)


def _get_weather_emoji(weather_code: int) -> str:
    """Convert WMO weather code to emoji."""
    if weather_code in [0]:
        return "☀️"  # Clear sky
    elif weather_code in [1, 2]:
        return "🌤️"  # Partly cloudy
    elif weather_code in [3]:
        return "☁️"  # Overcast
    elif weather_code in [45, 48]:
        return "🌫️"  # Foggy
    elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "🌧️"  # Rainy
    elif weather_code in [71, 73, 75, 77, 80, 81, 82, 85, 86]:
        return "❄️"  # Snowy
    elif weather_code in [80, 81, 82]:
        return "⛈️"  # Thunderstorm
    else:
        return "🌥️"  # Variable


def _weather_code_to_condition(weather_code: int) -> str:
    """Convert WMO weather code to readable condition."""
    if weather_code in [0]:
        return "солнечно"
    elif weather_code in [1, 2]:
        return "переменная облачность"
    elif weather_code in [3]:
        return "пасмурно"
    elif weather_code in [45, 48]:
        return "туман"
    elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "дождь"
    elif weather_code in [71, 73, 75, 77, 85, 86]:
        return "снег"
    elif weather_code in [80, 81, 82]:
        return "гроза"
    else:
        return "переменная облачность"


async def get_weather_tbilisi() -> Optional[Dict[str, Any]]:
    """Fetch hourly weather forecast for Tbilisi (Isani district) for today."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            # Using open-meteo API with hourly forecast
            url = "https://api.open-meteo.com/v1/forecast?latitude=41.7151&longitude=44.8271&hourly=temperature_2m,weather_code,wind_speed_10m&temperature_unit=celsius&timezone=Asia/Tbilisi"
            logger.info(f"🌤️  Fetching hourly weather from open-meteo API")
            logger.debug(f"URL: {url}")

            response = await http_client.get(url)
            logger.info(f"HTTP {response.status_code}")

            response.raise_for_status()
            data = response.json()

            # Get hourly data
            times = data["hourly"]["time"]
            temps = data["hourly"]["temperature_2m"]
            codes = data["hourly"]["weather_code"]
            winds = data["hourly"]["wind_speed_10m"]

            # Group by time periods (0-6 night, 6-12 morning, 12-18 day, 18-24 evening)
            periods = {
                "night": (0, 6),  # 00:00-06:00
                "morning": (6, 12),  # 06:00-12:00
                "day": (12, 18),  # 12:00-18:00
                "evening": (18, 24),  # 18:00-24:00
            }

            weather_by_period = {}
            for period_name, (start_hour, end_hour) in periods.items():
                period_temps = []
                period_codes = []
                period_winds = []

                for i, time_str in enumerate(times):
                    hour = int(time_str.split("T")[1].split(":")[0])
                    if start_hour <= hour < end_hour:
                        period_temps.append(temps[i])
                        period_codes.append(codes[i])
                        period_winds.append(winds[i])

                if period_temps:
                    avg_temp = sum(period_temps) / len(period_temps)
                    avg_wind = sum(period_winds) / len(period_winds)
                    # Most common weather code
                    most_common_code = max(set(period_codes), key=period_codes.count)

                    weather_by_period[period_name] = {
                        "emoji": _get_weather_emoji(most_common_code),
                        "condition": _weather_code_to_condition(most_common_code),
                        "temperature": round(avg_temp, 1),
                        "wind_speed": round(avg_wind, 1),
                        "weather_code": most_common_code,
                    }

            logger.info(f"✓ Weather by period: {list(weather_by_period.keys())}")
            return weather_by_period

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch weather: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None


def _format_system_prompt(
    user_profile: UserProfile,
    weather: Optional[Dict],
    custom_rules: Optional[list] = None,
) -> str:
    """Build system prompt with user context, weather, and custom rules."""
    weather_context = ""
    if weather:
        # If weather is structured by periods, extract current period
        if (
            "night" in weather
            or "morning" in weather
            or "day" in weather
            or "evening" in weather
        ):
            # Get current hour to determine period
            from datetime import datetime

            current_hour = datetime.now().hour
            if 0 <= current_hour < 6:
                current_period = "night"
            elif 6 <= current_hour < 12:
                current_period = "morning"
            elif 12 <= current_hour < 18:
                current_period = "day"
            else:
                current_period = "evening"

            period_weather = weather.get(
                current_period, weather.get("day")
            )  # Fallback to day
            if period_weather:
                weather_code = period_weather.get("weather_code", 3)
                temperature = period_weather.get("temperature", 20)
                wind_speed = period_weather.get("wind_speed", 5)
            else:
                weather_code = 3
                temperature = 20
                wind_speed = 5
        else:
            # Flat structure (backward compatibility)
            weather_code = weather.get("weather_code", 3)
            temperature = weather.get("temperature", 20)
            wind_speed = weather.get("wind_speed", 5)

        # Determine conditions from weather code
        conditions = []
        if weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:  # Rain codes
            conditions.append("идет дождь")
        if temperature < 0:
            conditions.append("очень холодно (< 0°C)")
        if temperature > 28:
            conditions.append("очень жарко (> 28°C)")

        weather_str = ", ".join(conditions) if conditions else "нормальная погода"
        weather_context = f"""

CURRENT WEATHER (Tbilisi, Isani district):
- Temperature: {temperature}°C
- Wind: {wind_speed} km/h
- Conditions: {weather_str}
- Tip: If user hasn't specified time/urgency, consider weather when proposing time
  (e.g., if rainy, suggest indoor/covered places; if very cold/hot, suggest off-peak hours)"""

    # Add current date and day of week
    from datetime import datetime

    today = datetime.now()
    day_names = [
        "Понедельник",
        "Вторник",
        "Среда",
        "Четверг",
        "Пятница",
        "Суббота",
        "Воскресенье",
    ]
    today_day = day_names[today.weekday()]
    today_date = today.strftime("%Y-%m-%d")

    user_context = f"""

CURRENT DATE & TIME:
- Today: {today_date} ({today_day})
- Current time: {today.strftime("%H:%M")}

USER PROFILE:
- Wake time: {user_profile.wake_time}
- Sleep time: {user_profile.sleep_time}
- Timezone: {user_profile.timezone}
- Preferences: {user_profile.preferences if user_profile.preferences else '(none)'}
- Working hours: weekdays (Mon-Fri) 10:00-19:00
- Days off: Saturday & Sunday (user doesn't work these days)"""

    custom_rules_context = ""
    if custom_rules:
        rules_text = "\n".join([f"  • {rule[1]}" for rule in custom_rules])
        custom_rules_context = f"""

CUSTOM USER RULES (IMPORTANT - follow these strictly):
{rules_text}"""

    return f"""You are a personal AI assistant for task planning in Tbilisi. Your job is to:
1. Parse free-text task descriptions
2. Extract: what, when (date/time), place, urgency, constraints
3. Check for missing information and ask clarifying questions
4. Propose optimal timing considering user profile, weather, and working hours
5. Apply user's custom rules
6. Explain your suggestions clearly

IMPORTANT RULES:
- NEVER invent dates, times, or place hours — ask if unsure
- If a place is mentioned, ALWAYS attempt to lookup its opening hours
- If user says "urgent" / "today" / "ASAP" / similar, allow any time (override default working hours)
- If user mentions weather-dependent activities (outdoor, parks), factor in current weather
- If place/date/time is clearly specified in user's text, use it (don't override user intent)
- Respond in Russian (user's language)
- Be precise and concise in explanations
- WEEKEND AWARENESS: If task is on Saturday/Sunday (user doesn't work these days):
  a) Don't assume 10:00-19:00 working hours apply
  b) For social/leisure tasks on weekends: suggest flexible times (morning/afternoon/evening all OK)
  c) For errands: suggest morning-afternoon (not too early, not too late)
  d) Still respect explicit time if user specifies it
- PARSE FLEXIBLE DEADLINES: if user says "можно X" / "или X" / "если нет X" / "в крайнем случае X":
  a) Use the FIRST mentioned date/time as when_date/when_time
  b) Put the flexible option ("можно в среду") in constraints field
  c) Do NOT ask clarification — all info is already in the text
- Proposed time should be within user's working hours (10:00-19:00 weekdays) UNLESS:
  a) User explicitly says urgent/ASAP/today
  b) User specifies specific time/date/urgency
  c) Task is clearly outside normal hours (e.g., "поужинать" → evening)
  d) Task is on Saturday/Sunday (use flexible timing, not work hours)
{f'- APPLY CUSTOM RULES: {len(custom_rules)} rule(s) defined by user' if custom_rules else ''}

REMINDER PATTERN: If user says "напомни в X" / "remind me on X" / "позови в X":
- Create TWO separate tasks:
  1) Main task with original when_date/when_time
  2) Reminder task scheduled for the reminder_date with text "Напоминание: [main task]"
- Both are independent tasks with separate IDs

RECURRING TASKS: Detect patterns like:
- "каждый понедельник" → is_recurring: true, recurrence_pattern: "every_monday"
- "по вторникам и пятницам" → is_recurring: true, recurrence_pattern: "tue_fri"
- "каждый день" → is_recurring: true, recurrence_pattern: "every_day"
- "каждую неделю" → is_recurring: true, recurrence_pattern: "weekly"
- "по выходным" / "в выходные" → is_recurring: true, recurrence_pattern: "sat_sun"
- "рабочие дни" / "будни" → is_recurring: true, recurrence_pattern: "mon_tue_wed_thu_fri"

If recurring task has no specific date but has time (e.g. "каждый пн в 19:00"):
- when_date: null (no specific date, it's recurring)
- when_time: "19:00"
- is_recurring: true
- recurrence_pattern: "every_monday"

TIME OF DAY PATTERNS: Detect phrases like:
- "до обеда" / "до полудня" → proposed_time: "12:00", when_time: "до 12:00", constraints: "до обеда"
- "после обеда" → proposed_time: "14:00", when_time: "после 12:00", constraints: "после обеда"
- "с утра" / "утром" → proposed_time: "09:00", constraints: "с утра"
- "вечером" → proposed_time: "18:00", constraints: "вечером"
- "ночью" → proposed_time: "21:00", constraints: "ночью"

WEEKDAY SHORTCUTS: When user says specific day without date:
- "в субботу" / "в выходные" → when_date: next Saturday (YYYY-MM-DD)
- "в понедельник" → when_date: next Monday (YYYY-MM-DD)
- etc. (always calculate NEXT occurrence if today is that day)

Return valid JSON with this schema (or array of 2 if reminder pattern detected):
{{
  "what": "task action",
  "when_date": "YYYY-MM-DD or null (null for recurring tasks without specific date)",
  "when_time": "HH:MM or null",
  "place": "location name or null",
  "place_hours": {{"mon": "10:00-18:00", ...}} or null,
  "proposed_time": "HH:MM or null",
  "is_urgent": true/false,
  "is_outdoor": true/false,
  "is_recurring": true/false,
  "recurrence_pattern": "every_monday|tue_fri|every_day|weekly|sat_sun|mon_tue_wed_thu_fri|null",
  "recurrence_end_date": "YYYY-MM-DD or null (when to stop recurring)",
  "constraints": "extracted constraints as text",
  "explanation": "human-readable explanation in Russian",
  "needs_clarification": true/false,
  "clarification_question": "question for user or null"
}}

If reminder pattern detected, return:
[
  {{ main_task_object }},
  {{
    "what": "Напоминание: [main task description]",
    "when_date": "reminder_date",
    "when_time": "reminder_time",
    "is_urgent": true,
    "constraints": "автоматическое напоминание",
    ...other fields...
  }}
]{user_context}{weather_context}{custom_rules_context}"""


async def parse_task(
    raw_text: str,
    user_profile: UserProfile,
    existing_tasks: list = None,
    custom_rules: list = None,
) -> Dict[str, Any]:
    """
    Parse raw task text using gpt-5.4-mini with context (weather, working hours, user profile, custom rules).

    Args:
        raw_text: User's free-text task description
        user_profile: User's preferences and schedule
        existing_tasks: List of already-planned tasks (for context)
        custom_rules: List of (id, rule, category) tuples from user

    Returns:
        Dict with parsed task fields + urgency/outdoor flags
    """
    if not existing_tasks:
        existing_tasks = []

    # Fetch current weather for Tbilisi
    weather = await get_weather_tbilisi()
    logger.info(f"Weather fetched: {weather}")

    # Build system prompt with user context, weather, and custom rules
    system_prompt = _format_system_prompt(user_profile, weather, custom_rules)

    # Prepare existing tasks context
    tasks_context = ""
    if existing_tasks:
        tasks_context = f"""

Already planned:
{json.dumps([{'date': t.when_date, 'time': t.proposed_time, 'task': t.what} for t in existing_tasks[:5]], ensure_ascii=False)}"""

    try:
        logger.info(f"📝 Parsing task: '{raw_text[:100]}...'")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        logger.info(f"User message length: {len(raw_text + tasks_context)} chars")

        logger.info("🔄 Calling gpt-5.4-mini API")
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=1024,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text + tasks_context},
            ],
        )

        logger.info(f"✓ OpenAI response object received")
        logger.info(f"  Model: {response.model}")
        logger.info(
            f"  Tokens: {response.usage.prompt_tokens}→{response.usage.completion_tokens}"
        )
        logger.info(f"  Choices: {len(response.choices)}")

        if not response.choices:
            logger.error("❌ OpenAI returned 0 choices!")
            raise ValueError("OpenAI returned no choices")

        result_text = response.choices[0].message.content
        logger.info(f"  Content length: {len(result_text) if result_text else 0} chars")

        if not result_text:
            logger.error("❌ Response content is EMPTY!")
            logger.error(f"  Full response object: {response}")
            raise ValueError("OpenAI returned empty content")
        # Extract JSON from response (might contain markdown code blocks)
        logger.info(f"Extracting JSON from response")
        if "```json" in result_text:
            logger.info("Found ```json block, extracting...")
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            logger.info("Found ``` block, extracting...")
            result_text = result_text.split("```")[1].split("```")[0]

        logger.info(f"JSON text length: {len(result_text)} chars")
        logger.info(f"JSON text preview: {result_text[:200]}...")

        result = json.loads(result_text)
        logger.info(f"✓ JSON parsed successfully")

        # Check if result is array (reminder pattern) or single object
        if isinstance(result, list):
            logger.info(
                f"✓ Tasks parsed (with reminder): '{result[0].get('what')}' + reminder"
            )
        else:
            logger.info(
                f"✓ Task parsed: '{result.get('what')}' | "
                f"urgent={result.get('is_urgent')} | "
                f"time={result.get('proposed_time')}"
            )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON Parse Error: {e}")
        logger.error(f"  Error type: {type(e).__name__}")
        logger.error(f"  Error position: {e.pos if hasattr(e, 'pos') else 'N/A'}")
        logger.error(
            f"  Response text length: {len(result_text) if 'result_text' in locals() else 'N/A'}"
        )
        logger.error(
            f"  Response text: {result_text[:500] if 'result_text' in locals() else 'NOT SET'}"
        )
        return {
            "what": raw_text,
            "needs_clarification": True,
            "clarification_question": "Не удалось разобрать задачу. Пожалуйста, опиши ее подробнее.",
            "explanation": "Ошибка парсинга",
        }
    except Exception as e:
        logger.error(f"❌ AI parsing failed: {type(e).__name__}: {e}")
        logger.error(f"  Exception details: {repr(e)}")
        logger.error(f"  Exception traceback:", exc_info=True)
        return {
            "what": raw_text,
            "needs_clarification": True,
            "clarification_question": "Сервис планирования временно недоступен. Попробуй позже.",
            "explanation": "Ошибка сервиса",
        }


async def generate_morning_digest(
    tasks: list, user_profile: UserProfile, weather: Optional[Dict] = None
) -> str:
    """
    Generate natural-language morning summary with context and reasoning.

    Args:
        tasks: List of tasks scheduled for today
        user_profile: User preferences
        weather: Current weather data

    Returns:
        Natural-language contextual summary with explanation
    """
    if not tasks:
        return "Доброе утро! На сегодня запланированных дел нет. Можешь отдохнуть! ☀️"

    # Format tasks for prompt
    tasks_text = "\n".join(
        [
            f"- {t.what or t.raw_text[:40]} "
            f"(время: {t.proposed_time or 'гибкое'}, "
            f"место: {t.place or 'не указано'}, "
            f"срочно: {'да' if t.is_urgent else 'нет'})"
            for t in tasks
        ]
    )

    # Format weather context
    weather_text = ""
    if weather:
        conditions = []
        if weather["is_raining"]:
            conditions.append(f"идет дождь (🌧️)")
        if weather["is_very_cold"]:
            conditions.append(f"очень холодно ({weather['temperature']}°C)")
        if weather["is_very_hot"]:
            conditions.append(f"очень жарко ({weather['temperature']}°C)")
        if not conditions:
            conditions.append(f"{weather['temperature']}°C, переменная облачность")

        weather_text = f"""
Current weather in Tbilisi: {', '.join(conditions)}
Temperature: {weather["temperature"]}°C
Wind: {weather["wind_speed"]} km/h"""

    prompt = f"""You are a helpful morning planning assistant. Generate a warm, encouraging
morning message for the user in Russian with:
1. A brief weather context explanation (how it affects today)
2. Their wake-up time consideration
3. Ordered list of tasks with reasoning for timing
4. One practical suggestion or encouragement

User profile:
- Wake time: {user_profile.wake_time}
- Preferences: {user_profile.preferences or '(none)'}
- Timezone: {user_profile.timezone}{weather_text}

Tasks for today:
{tasks_text}

Generate a warm, contextual morning digest that explains WHY these tasks
are scheduled this way, considering weather, user preferences, and practicality.
Be encouraging and practical. Format as markdown with emojis."""

    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful morning planning assistant in Russian.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Morning digest generation failed: {e}")
        return "Доброе утро! У вас есть запланированные задачи на день."


async def generate_evening_digest(
    tasks: list, user_profile: UserProfile, completed_count: int = 0
) -> str:
    """
    Generate evening review summary with context and encouragement.

    Args:
        tasks: List of remaining tasks for today
        user_profile: User preferences
        completed_count: How many tasks were completed today

    Returns:
        Natural-language evening summary
    """
    if not tasks:
        return (
            f"🌙 Отличная работа! Вы выполнили все задачи на день. Отдыхайте! "
            f"{'Завтра новые вызовы ждут!' if completed_count > 0 else ''}"
        )

    # Format remaining tasks
    tasks_text = "\n".join(
        [
            f"- {t.what or t.raw_text[:40]} "
            f"(время: {t.proposed_time or 'гибкое'}, "
            f"срочно: {'да' if t.is_urgent else 'нет'})"
            for t in tasks
        ]
    )

    prompt = f"""You are an encouraging evening review assistant. Generate a warm
evening message for the user in Russian with:
1. Acknowledgment of tasks completed (if any)
2. Review of remaining tasks
3. Realistic assessment of what can still be done tonight
4. Encouragement or practical suggestion for evening

User profile:
- Sleep time: {user_profile.sleep_time}
- Preferences: {user_profile.preferences or '(none)'}

Completed today: {completed_count} tasks
Remaining tasks:
{tasks_text}

Generate a warm, realistic evening review that helps user decide
what to focus on or whether to rest. Be honest and encouraging.
Format as markdown with emojis."""

    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": "You are an encouraging evening review assistant in Russian.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Evening digest generation failed: {e}")
        return "🌙 Вечер! Посмотрите, какие дела осталось выполнить, или отдохните. Спокойной ночи!"
