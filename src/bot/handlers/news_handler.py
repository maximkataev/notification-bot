"""Handler for news configuration commands."""

import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from src.db.database import get_news_prompt, set_news_prompt, reset_news_prompt
from src.ai.news_selector import DEFAULT_NEWS_PROMPT
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("newsprompt"), AuthorizedOnly())
async def show_news_prompt(message: types.Message):
    """Show current news selection prompt."""
    user_id = message.from_user.id
    custom = await get_news_prompt(user_id)

    if custom:
        response = "📝 Твой кастомный промпт для новостей:\n\n" + custom
    else:
        response = "📝 Default промпт для новостей:\n\n" + DEFAULT_NEWS_PROMPT

    await message.reply(response, disable_web_page_preview=True)


@router.message(Command("newsset"), AuthorizedOnly())
async def set_news_prompt_cmd(message: types.Message, command: CommandObject):
    """Set custom news selection prompt."""
    logger.info(f"🎯 /newsset command triggered for user {message.from_user.id}")
    logger.info(f"  Command args: {command.args[:100] if command.args else 'None'}...")

    if not command.args:
        logger.info("No args provided, sending help message")
        await message.reply(
            "Используй: /news_set <новый промпт>\n\n"
            "Пример: /news_set Выбери только новости о конфликтах. Игнорируй спорт.",
            disable_web_page_preview=True,
        )
        return

    user_id = message.from_user.id
    new_prompt = command.args

    logger.info(f"Saving news prompt ({len(new_prompt)} chars) for user {user_id}")

    await set_news_prompt(user_id, new_prompt)
    logger.info(f"✓ News prompt saved for user {user_id}")

    logger.info(f"Sending confirmation reply")
    await message.reply(
        "✓ Промпт обновлен! Будет использован при следующем дайджесте.",
        disable_web_page_preview=True,
    )
    logger.info(f"✓ Reply sent")


@router.message(Command("newsreset"), AuthorizedOnly())
async def reset_news_prompt_cmd(message: types.Message):
    """Reset news prompt to default."""
    user_id = message.from_user.id

    await reset_news_prompt(user_id)
    logger.info(f"News prompt reset for user {user_id}")

    await message.reply("✓ Промпт сброшен на default.", disable_web_page_preview=True)
