"""Handler for /move command - move overdue tasks to today or tomorrow."""

import logging
from datetime import datetime, timedelta
from aiogram import Router, types
from aiogram.filters import CommandObject, Command
from src.workers.todoist_client import get_overdue_tasks, update_todoist_task_due_date
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("move"), AuthorizedOnly())
async def move_command(message: types.Message, command: CommandObject):
    """Handle /move <сегодня|завтра> command - reschedule overdue tasks."""
    if not command.args:
        await message.reply(
            "Используй: /move <сегодня|завтра>\n\n"
            "Переносит все задачи с прошлым сроком на сегодня или завтра.\n\n"
            "Примеры:\n"
            "  /move сегодня\n"
            "  /move завтра",
            disable_web_page_preview=True,
        )
        return

    arg = command.args.strip().lower()
    if arg not in ["сегодня", "завтра"]:
        await message.reply(
            "❌ Ошибка: используй либо 'сегодня' либо 'завтра'\n\n"
            "Примеры:\n"
            "  /move сегодня\n"
            "  /move завтра",
            disable_web_page_preview=True,
        )
        return

    logger.info(f"📌 /move command from user {message.from_user.id}: {arg}")

    # Show "processing..." message
    processing_msg = await message.reply(
        "🔄 Переношу задачи...", disable_web_page_preview=True
    )

    try:
        # Fetch overdue tasks
        overdue_tasks = await get_overdue_tasks()

        if not overdue_tasks:
            await processing_msg.edit_text(
                "✅ Нет задач с прошлым сроком.", disable_web_page_preview=True
            )
            return

        # Calculate target date
        today = datetime.now().date()
        target_date = today if arg == "сегодня" else today + timedelta(days=1)
        target_date_str = target_date.isoformat()

        # Update all overdue tasks
        updated_count = 0
        failed_count = 0

        for task in overdue_tasks:
            task_id = task.get("id")
            task_content = task.get("content", "")
            old_due_date = task.get("due_date")

            success = await update_todoist_task_due_date(task_id, target_date_str)

            if success:
                updated_count += 1
                logger.info(
                    f"✓ Moved task: {task_content} from {old_due_date} to {target_date_str}"
                )
            else:
                failed_count += 1
                logger.error(f"✗ Failed to move task: {task_content}")

        # Build response
        date_name = "на сегодня" if arg == "сегодня" else "на завтра"
        response = (
            f"✅ Перенесено задач на {date_name}: {updated_count}\n"
        )

        if failed_count > 0:
            response += f"❌ Ошибок: {failed_count}"

        await processing_msg.edit_text(response, disable_web_page_preview=True)
        logger.info(
            f"✓ Move command completed: {updated_count} updated, {failed_count} failed"
        )

    except Exception as e:
        logger.error(
            f"✗ Error in move command for user {message.from_user.id}: {e}",
            exc_info=True,
        )
        await processing_msg.edit_text(
            "❌ Ошибка при переносе задач. Попробуй позже.",
            disable_web_page_preview=True,
        )
