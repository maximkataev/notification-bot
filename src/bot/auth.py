"""Authorization utilities for bot commands."""

import logging
from typing import Optional
from aiogram.filters import BaseFilter
from aiogram import types
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

# Cache authorized IDs
_AUTHORIZED_ID: Optional[int] = None


def get_authorized_id() -> int:
    """Get the authorized user/chat ID."""
    global _AUTHORIZED_ID
    if _AUTHORIZED_ID is None:
        try:
            # Try TELEGRAM_USER_ID first (for single-user bot)
            _AUTHORIZED_ID = int(get_secret("TELEGRAM_USER_ID"))
            logger.debug(f"Using TELEGRAM_USER_ID: {_AUTHORIZED_ID}")
        except:
            # Fallback to TELEGRAM_CHAT_ID
            _AUTHORIZED_ID = int(get_secret("TELEGRAM_CHAT_ID"))
            logger.debug(f"Using TELEGRAM_CHAT_ID: {_AUTHORIZED_ID}")
    return _AUTHORIZED_ID


class AuthorizedOnly(BaseFilter):
    """Filter that checks if user is authorized."""

    async def __call__(self, message: types.Message) -> bool:
        authorized_id = get_authorized_id()
        user_id = message.from_user.id
        is_authorized = user_id == authorized_id

        if not is_authorized:
            logger.warning(f"❌ Unauthorized access attempt from user {user_id}")
            await message.reply(
                "❌ У тебя нет прав на использование этого бота.\n\nТвой ID: "
                + str(user_id)
            )

        return is_authorized
