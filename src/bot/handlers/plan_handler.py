"""Handler for /plan command."""

import logging
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Router, types
from aiogram.filters import CommandObject, Command
from src.db.database import (
    get_ai_rules,
    add_ai_rule,
    delete_ai_rule,
    reset_ai_rules,
    get_user_profile,
)
from src.workers.todoist_client import create_todoist_task
from src.bot.auth import AuthorizedOnly
from src.ai.planner_agent import parse_task

logger = logging.getLogger(__name__)
router = Router()


def _get_nearest_date(date_str: str) -> Optional[str]:
    """Calculate nearest date if given a weekday name or relative reference.

    Returns ISO format date string (YYYY-MM-DD) or None if unable to parse.
    """
    if not date_str:
        return None

    # Check for day of week references (case-insensitive Russian)
    day_map = {
        "понедельник": 0,
        "пн": 0,
        "вторник": 1,
        "вт": 1,
        "среда": 2,
        "ср": 2,
        "четверг": 3,
        "чт": 3,
        "пятница": 4,
        "пт": 4,
        "суббота": 5,
        "сб": 5,
        "воскресенье": 6,
        "вс": 6,
    }

    date_lower = date_str.lower().strip()

    # Try to match day of week
    for day_name, day_idx in day_map.items():
        if day_name in date_lower:
            today = datetime.now().date()
            current_dow = today.weekday()
            days_ahead = (day_idx - current_dow) % 7
            if days_ahead == 0:
                days_ahead = 7  # If today is that day, go to next week
            target_date = today + timedelta(days=days_ahead)
            return target_date.isoformat()

    # If it already looks like YYYY-MM-DD, return as-is
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return date_str

    return None


@router.message(Command("plan"), AuthorizedOnly())
async def plan_command(message: types.Message, command: CommandObject):
    """Handle /plan <text> command - create task in Todoist with parsed date & priority."""
    if not command.args:
        await message.reply(
            "Используй: /plan <описание задачи>\n\n"
            "Примеры:\n"
            "  /plan купить молоко\n"
            "  /plan в субботу на маковые поля с утра\n"
            "  /plan позвонить другу завтра",
            disable_web_page_preview=True,
        )
        return

    text = command.args
    user_id = message.from_user.id

    logger.info(f"📝 /plan command from user {user_id}: {text[:50]}...")

    # Show "creating..." message
    creating_msg = await message.reply(
        "🔄 Создаю в Todoist...", disable_web_page_preview=True
    )

    try:
        # Get user profile for task parsing context
        user_profile = await get_user_profile(user_id)
        if not user_profile:
            from src.db.models import UserProfile

            user_profile = UserProfile(user_id=user_id)

        # Parse task with AI to extract date, time, priority
        logger.info("Parsing task with AI...")
        try:
            parsed = await parse_task(text, user_profile)
        except Exception as parse_err:
            logger.error(
                f"⚠️  AI parsing failed, using fallback: {parse_err}", exc_info=True
            )
            # Fallback: create task without date/priority parsing
            parsed = {
                "what": text,
                "is_urgent": False,
                "when_date": None,
                "when_time": None,
            }

        if parsed.get("needs_clarification"):
            response = f"❓ {parsed.get('clarification_question', 'Не понял. Опиши задачу подробнее.')}"
            await creating_msg.edit_text(response, disable_web_page_preview=True)
            return

        # Extract parsed fields
        when_date = parsed.get("when_date")
        # Prefer proposed_time (HH:MM format) over when_time (Russian text like "утром")
        when_time = parsed.get("proposed_time") or parsed.get("when_time")
        is_urgent = parsed.get("is_urgent", False)
        what = parsed.get("what", text)

        # Build due_date for Todoist
        todoist_due_date = None
        if when_date:
            # Date provided - use as-is (YYYY-MM-DD)
            todoist_due_date = when_date
            if when_time:
                # Add time if available (Todoist accepts ISO format with time)
                todoist_due_date = f"{when_date}T{when_time}:00"
        else:
            # No date parsed - try to parse from task text for common patterns
            if any(word in text.lower() for word in ["завтра"]):
                tomorrow = datetime.now().date() + timedelta(days=1)
                todoist_due_date = tomorrow.isoformat()
            elif any(word in text.lower() for word in ["сегодня", "сейчас"]):
                today = datetime.now().date()
                todoist_due_date = today.isoformat()

        # Determine priority (1=Normal, 2=Low, 3=Medium, 4=High)
        todoist_priority = 4 if is_urgent else 1

        logger.info(
            f"Parsed: what={what[:50]} | date={todoist_due_date} | priority={todoist_priority}"
        )

        # Create task in Todoist with date and priority
        task_url = await create_todoist_task(
            content=what, due_date=todoist_due_date, priority=todoist_priority
        )

        if task_url:
            # Format response with details
            details = []
            if when_date:
                details.append(f"📅 {when_date}")
            if when_time:
                details.append(f"⏰ {when_time}")
            if is_urgent:
                details.append("🔴 Срочно")

            details_str = " | ".join(details) if details else ""
            if details_str:
                details_str = f"\n{details_str}"

            response = f"✓ Задача создана!\n\n📝 {what}{details_str}\n\n🔗 [Открыть в Todoist]({task_url})"
            logger.info(f"✓ Task created in Todoist for user {user_id}")
        else:
            response = "❌ Не удалось создать задачу в Todoist. Проверь, что проект 'Личное' существует и API ключ верный."
            logger.error(f"Failed to create task in Todoist for user {user_id}")

        await creating_msg.edit_text(
            response, parse_mode="Markdown", disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(
            f"✗ Error creating task in Todoist for user {user_id}: {e}", exc_info=True
        )
        await creating_msg.edit_text(
            "❌ Ошибка при создании задачи. Попробуй позже или проверь конфигурацию.",
            disable_web_page_preview=True,
        )
