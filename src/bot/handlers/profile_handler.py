"""Handler for /me command (user profile)."""

import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from src.db.database import get_user_profile, save_user_profile
from src.db.models import UserProfile
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("me"), AuthorizedOnly())
async def me_command(message: types.Message, command: CommandObject):
    """Get or update user profile."""
    user_id = message.from_user.id

    if not command.args:
        # Show profile
        profile = await get_user_profile(user_id)
        await message.reply(
            f"Ваш профиль:\n\n"
            f"⏰ Просыпаетесь: {profile.wake_time}\n"
            f"😴 Спите: {profile.sleep_time}\n"
            f"🌍 Временная зона: {profile.timezone}\n"
            f"📝 Предпочтения: {profile.preferences or '(не указаны)'}\n\n"
            f"Используй: /me <предпочтения>\n"
            f"Пример: /me просыпаюсь в 11:00, предпочитаю дневное время",
            disable_web_page_preview=True,
        )
        return

    # Update preferences
    text = command.args
    profile = await get_user_profile(user_id)
    profile.preferences = text
    await save_user_profile(profile)

    await message.reply(
        f"✓ Профиль обновлен.\n\nПредпочтения: {text}",
        disable_web_page_preview=True,
    )
    logger.info(f"Profile updated for user {user_id}: {text}")
