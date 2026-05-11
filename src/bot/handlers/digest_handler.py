"""Handler for digest commands."""

import logging
from aiogram import Router, types
from aiogram.filters import Command
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()

logger.info("🔧 digest_handler module loaded - starting imports")

try:
    from src.bot.scheduler import morning_digest

    logger.info("✓ morning_digest imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import morning_digest: {e}")
    raise


@router.message(Command("digest"), AuthorizedOnly())
async def digest_command(message: types.Message):
    """Send morning digest right now on demand."""
    try:
        logger.info("=" * 60)
        logger.info("🎯 DIGEST COMMAND HANDLER TRIGGERED")
        logger.info("=" * 60)

        user_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text

        logger.info(f"📋 /digest command received")
        logger.info(f"  User ID: {user_id}")
        logger.info(f"  Chat ID: {chat_id}")
        logger.info(f"  Message text: {text}")
        logger.info(f"  Message type: {message.content_type}")
    except Exception as e:
        logger.error(f"❌ ERROR at command start: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {str(e)}")
        return

    # Get bot instance from dispatcher
    bot = message.bot
    logger.info(f"  Bot instance: {bot.token[:20]}...")

    # Send "generating..." message
    logger.info(f"Sending status message...")
    try:
        status_msg = await message.reply("⏳ Генерирую дайджест...")
        logger.info(f"✓ Status message sent (message_id={status_msg.message_id})")
    except Exception as e:
        logger.error(f"❌ Failed to send status message: {e}", exc_info=True)
        return

    try:
        # Run morning digest
        logger.info(f"🚀 Starting on-demand morning digest for user {user_id}")
        logger.info(f"Calling morning_digest(bot, {user_id}, {chat_id})")
        await morning_digest(bot, user_id, chat_id)
        logger.info(f"✓ morning_digest() completed")

        # Update status
        logger.info(f"Updating status message...")
        await status_msg.edit_text("✓ Дайджест отправлен выше")
        logger.info(f"✓ Status message updated")
        logger.info(f"✓✓ ON-DEMAND DIGEST COMPLETED SUCCESSFULLY")

    except Exception as e:
        logger.error(f"❌ DIGEST GENERATION FAILED")
        logger.error(f"  Exception type: {type(e).__name__}")
        logger.error(f"  Exception message: {e}")
        logger.error(f"  Full traceback:", exc_info=True)

        try:
            await status_msg.edit_text(
                f"❌ Ошибка при генерации дайджеста:\n{str(e)[:100]}"
            )
            logger.info(f"Error message sent to user {user_id}")
        except Exception as edit_error:
            logger.error(f"Failed to send error message: {edit_error}")

    logger.info("=" * 60)
    logger.info("DIGEST COMMAND HANDLER FINISHED")
