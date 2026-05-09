"""Handlers for AI rules management."""
import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from src.db.database import get_ai_rules, add_ai_rule, delete_ai_rule, reset_ai_rules
from src.bot.auth import AuthorizedOnly

logger = logging.getLogger(__name__)
router = Router()

logger.info("🔧 ai_handler module loaded - router created")


@router.message(Command("airules"), AuthorizedOnly())
async def ai_rules_command(message: types.Message):
    """Show current AI rules."""
    logger.info("🎯 /airules handler triggered!")
    user_id = message.from_user.id
    rules = await get_ai_rules(user_id)

    if not rules:
        await message.reply(
            "У вас нет кастомных правил для AI.\n\n"
            "Используй /ai-add <правило> для добавления.\n\n"
            "Примеры:\n"
            "  /ai-add не планировать в понедельник\n"
            "  /ai-add предпочитаю дневное время (12-17)\n"
            "  /ai-add избегай спортзалов\n"
            "  /ai-add срочные дела - только сегодня"
        )
        return

    lines = ["📋 Ваши правила для AI:\n"]
    for rule_id, rule_text, category in rules:
        cat_label = f"[{category}] " if category else ""
        lines.append(f"  {rule_id}. {cat_label}{rule_text}")

    lines.append(f"\n/ai-del <id> — удалить правило")
    lines.append(f"/ai-reset — удалить все правила")
    await message.reply("\n".join(lines))


@router.message(Command("aiadd"), AuthorizedOnly())
async def ai_add_command(message: types.Message, command: CommandObject):
    """Add a new AI rule."""
    if not command.args:
        await message.reply(
            "Используй: /ai-add <правило>\n\n"
            "Примеры:\n"
            "  /ai-add не планировать в понедельник\n"
            "  /ai-add предпочитаю дневное время (12-17)\n"
            "  /ai-add избегай прогулок в дождь\n"
            "  /ai-add только срочные дела между 10-12"
        )
        return

    rule_text = command.args
    user_id = message.from_user.id

    rule_id = await add_ai_rule(user_id, rule_text)
    await message.reply(f"✓ Правило #{rule_id} добавлено:\n\n'{rule_text}'\n\nАI будет учитывать это в следующих задачах.")
    logger.info(f"AI rule added: #{rule_id} for user {user_id}: {rule_text}")


@router.message(Command("aidel"), AuthorizedOnly())
async def ai_del_command(message: types.Message, command: CommandObject):
    """Delete an AI rule."""
    if not command.args:
        await message.reply("Используй: /ai-del <id>\n\nПосмотри ID в /ai-rules")
        return

    try:
        rule_id = int(command.args)
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    user_id = message.from_user.id
    deleted = await delete_ai_rule(rule_id, user_id)

    if deleted:
        await message.reply(f"✓ Правило #{rule_id} удалено.")
        logger.info(f"AI rule deleted: #{rule_id} for user {user_id}")
    else:
        await message.reply("Правило не найдено.")


@router.message(Command("aireset"), AuthorizedOnly())
async def ai_reset_command(message: types.Message):
    """Delete all AI rules."""
    user_id = message.from_user.id

    # Confirm deletion
    rules = await get_ai_rules(user_id)
    if not rules:
        await message.reply("У вас нет правил для удаления.")
        return

    await reset_ai_rules(user_id)
    await message.reply(
        f"✓ Удалены все {len(rules)} правило(а).\n\n"
        "AI вернулся к дефолтным настройкам."
    )
    logger.info(f"All AI rules reset for user {user_id}")
