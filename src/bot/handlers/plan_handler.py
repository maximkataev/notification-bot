"""Handler for /plan command."""
import logging
from aiogram import Router, types
from aiogram.filters import CommandObject, Command
from src.db.database import (
    get_ai_rules,
    add_ai_rule,
    delete_ai_rule,
    reset_ai_rules,
)
from src.workers.todoist_client import create_todoist_task
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("plan"), AuthorizedOnly())
async def plan_command(message: types.Message, command: CommandObject):
    """Handle /plan <text> command - create task in Todoist."""
    if not command.args:
        await message.reply(
            "Используй: /plan <описание задачи>\n\n"
            "Примеры:\n"
            "  /plan купить молоко\n"
            "  /plan позвонить другу\n"
            "  /plan забронировать билеты"
        )
        return

    text = command.args
    user_id = message.from_user.id

    logger.info(f"📝 /plan command from user {user_id}: {text[:50]}...")

    # Show "creating..." message
    creating_msg = await message.reply("🔄 Создаю задачу в Todoist...")

    try:
        task_url = await create_todoist_task(text)

        if task_url:
            response = f"✓ Задача создана!\n\n📝 {text}\n\n🔗 [Открыть в Todoist]({task_url})"
            logger.info(f"✓ Task created in Todoist for user {user_id}")
        else:
            response = "❌ Не удалось создать задачу в Todoist. Проверь, что проект 'Личное' существует и API ключ верный."
            logger.error(f"Failed to create task in Todoist for user {user_id}")

        await creating_msg.edit_text(response, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"✗ Error creating task in Todoist for user {user_id}: {e}", exc_info=True)
        await creating_msg.edit_text(f"❌ Ошибка: {str(e)}")
