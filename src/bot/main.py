"""Main bot entry point with aiogram."""
import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from src.utils.doppler import get_secret
from src.utils.logging_config import setup_logging, get_logger
from src.bot.auth import AuthorizedOnly

# Load .env file if it exists (for local development)
load_dotenv()
from src.db.database import init_db
from src.bot.handlers import plan_handler, tasks_handler, profile_handler, ai_handler, news_handler, digest_handler
from src.bot.scheduler import init_scheduler
from src.workers.currency_monitor import CurrencyMonitor
from src.workers.water_cut_monitor import WaterCutMonitor

logger = get_logger(__name__)


class DebugMiddleware(BaseMiddleware):
    """Log all messages for debugging."""
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message):
            logger.info(f"📨 Middleware: Got message '{event.text}' from user {event.from_user.id}")
        return await handler(event, data)


async def start_command(message: types.Message):
    """Handle /start command."""
    await message.reply(
        "👋 Привет! Я AI-помощник по планированию задач.\n\n"
        "Используй /info для полного списка всех команд."
    )


async def ping_command(message: types.Message):
    """Handle /ping command - check bot is alive."""
    await message.reply("🏓 pong")


async def debug_command(message: types.Message):
    """Show debug info."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    await message.reply(
        f"🔍 DEBUG INFO:\n"
        f"Your user_id: {user_id}\n"
        f"Chat ID: {chat_id}\n"
        f"Message type: {message.chat.type}\n\n"
        f"Используй эти значения для TELEGRAM_USER_ID и TELEGRAM_CHAT_ID"
    )


async def info_command(message: types.Message):
    """Handle /info command - show all available commands."""
    await message.reply(
        "КОМАНДЫ:\n\n"
        "ЗАДАЧИ:\n"
        "/plan <текст> - добавить задачу\n"
        "/tasks - показать все задачи\n\n"
        "ПРОФИЛЬ:\n"
        "/me - показать профиль\n"
        "/me <текст> - обновить предпочтения\n\n"
        "ПРАВИЛА AI:\n"
        "/airules - показать правила\n"
        "/aiadd <правило> - добавить правило\n"
        "/aidel <id> - удалить правило\n"
        "/aireset - удалить все правила\n\n"
        "НОВОСТИ:\n"
        "/newsprompt - показать промпт\n"
        "/newsset <текст> - установить промпт\n"
        "/newsreset - вернуть default\n\n"
        "ДАЙДЖЕСТ:\n"
        "/digest - отправить дайджест сейчас\n"
        "(обычно в 08:00)\n\n"
        "ПРИМЕРЫ:\n"
        "/plan в пн вечером концерт\n"
        "/me просыпаюсь в 11:00\n"
        "/aiadd встречи только в четверг\n"
        "/newsset только политика и экономика\n"
    )


async def main():
    """Initialize and run bot."""
    # Determine if running in Docker
    docker_mode = os.getenv("DOCKER_MODE", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Initialize logging
    setup_logging(level=getattr(logging, log_level), docker_mode=docker_mode)
    logger.info(f"🚀 Bot starting (Docker: {docker_mode}, Level: {log_level})")

    # Initialize database
    await init_db()
    logger.info("✓ Database initialized")

    # Get credentials
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in Doppler")

    # Initialize bot
    bot = Bot(token=bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Register middleware for debugging
    dp.message.middleware(DebugMiddleware())
    logger.info("✓ Debug middleware registered")

    # Register routers (digest_handler first, before plan_handler's catch-all)
    logger.info("Registering routers...")
    dp.include_router(digest_handler.router)
    logger.info("  ✓ digest_handler router registered")
    dp.include_router(tasks_handler.router)
    logger.info("  ✓ tasks_handler router registered")
    dp.include_router(profile_handler.router)
    logger.info("  ✓ profile_handler router registered")
    dp.include_router(ai_handler.router)
    logger.info("  ✓ ai_handler router registered")
    dp.include_router(news_handler.router)
    logger.info("  ✓ news_handler router registered")
    dp.include_router(plan_handler.router)
    logger.info("  ✓ plan_handler router registered (last due to catch-all handler)")

    # Register start, info, debug, and ping commands
    logger.info("Registering commands...")
    dp.message.register(start_command, Command("start"))
    logger.info("  ✓ /start command registered")
    dp.message.register(ping_command, Command("ping"), AuthorizedOnly())
    logger.info("  ✓ /ping command registered (auth required)")
    dp.message.register(debug_command, Command("debug"))
    logger.info("  ✓ /debug command registered")
    dp.message.register(info_command, Command("info"), AuthorizedOnly())
    logger.info("  ✓ /info command registered (auth required)")

    logger.info("✓ All routers and handlers registered")

    # Initialize scheduler for morning digest only
    chat_id = int(get_secret("TELEGRAM_CHAT_ID"))  # Chat ID for morning digest

    # For single-user bot: chat_id should be same as user_id
    # If bot is in group: TELEGRAM_CHAT_ID is the group, need separate USER_ID for task queries
    try:
        user_id = int(get_secret("TELEGRAM_USER_ID"))
        logger.info(f"Using TELEGRAM_USER_ID: {user_id}")
    except:
        # Fallback: assume private chat where chat_id == user_id
        user_id = chat_id
        logger.warning(f"⚠️  TELEGRAM_USER_ID not set, using TELEGRAM_CHAT_ID ({chat_id}). If bot is in group, set TELEGRAM_USER_ID to your Telegram user ID.")

    logger.info(f"Scheduler config: chat_id={chat_id}, user_id={user_id}")
    scheduler = init_scheduler(bot, user_id, chat_id)
    scheduler.start()
    logger.info("Scheduler started: morning digest (04:00 UTC = 08:00 Tbilisi)")

    # Start currency monitor as background task
    currency_monitor = CurrencyMonitor(bot=bot, chat_id=chat_id)
    monitor_task = asyncio.create_task(currency_monitor.run_loop())
    logger.info("Currency monitor started in background")

    # Start water cut monitor as background task
    water_monitor = WaterCutMonitor(bot=bot, chat_id=chat_id)
    water_monitor_task = asyncio.create_task(water_monitor.run_loop())
    logger.info("Water cut monitor started in background")

    try:
        await dp.start_polling(bot)
    finally:
        monitor_task.cancel()
        water_monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("Currency monitor task cancelled")
        try:
            await water_monitor_task
        except asyncio.CancelledError:
            logger.info("Water cut monitor task cancelled")
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
