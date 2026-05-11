"""Handler for /tasks command."""

import logging
from aiogram import Router, types
from aiogram.filters import Command
from src.workers.todoist_client import get_todoist_tasks
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("tasks"), AuthorizedOnly())
async def tasks_command(message: types.Message):
    """Show all tasks from Todoist."""
    tasks = await get_todoist_tasks()

    if not tasks:
        await message.reply("У вас нет запланированных задач.")
        return

    lines = ["📋 Ваши задачи:\n"]
    for task in tasks:
        task_name = task.what or task.raw_text[:50]
        line = f"• {task_name}"

        when_parts = []
        if task.when_date:
            when_parts.append(task.when_date)
        if task.proposed_time:
            when_parts.append(task.proposed_time)
        if when_parts:
            when_str = " ".join(when_parts)
            line += f" ({when_str})"

        markers = []
        if task.is_urgent:
            markers.append("🔴")
        if task.is_outdoor:
            markers.append("🌦️")
        if markers:
            line += " " + " ".join(markers)

        lines.append(line)

    await message.reply("\n".join(lines))
