#!/usr/bin/env python3
"""Test task explanation prompt with context."""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def show_prompt():
    """Show what the AI will receive as context."""

    # Sample tasks
    tasks = [
        ("поехать в горы", "19:00", True, True),  # (what, time, urgent, outdoor)
        ("сосать", "19:00", False, False),
        ("задача", None, False, False),
    ]

    # Sample weather
    weather = {
        "morning": {"temperature": 17.2, "wind_speed": 5.5},
        "day": {"temperature": 21.8, "wind_speed": 6.2},
        "evening": {"temperature": 18.8, "wind_speed": 5.0},
        "night": {"temperature": 14.8, "wind_speed": 3.2},
    }

    # Sample profile
    profile = {
        "wake_time": "09:00",
        "sleep_time": "23:00",
        "preferences": "интересуюсь футболом, путешествиями, экономикой",
        "timezone": "Asia/Tbilisi",
    }

    # Build context
    task_list = "\n".join([
        f"- {task[0]} (когда: {task[1] or 'гибко'}, срочно: {'да' if task[2] else 'нет'}, улица: {'да' if task[3] else 'нет'})"
        for task in tasks
    ])

    context_lines = []
    context_lines.append("📋 Погода на сегодня:")
    for period, data in weather.items():
        temp = data.get('temperature', '?')
        wind = data.get('wind_speed', '?')
        context_lines.append(f"  - {period}: {temp}°C, ветер {wind} км/ч")

    context_lines.append(f"👤 Профиль: просыпается в {profile['wake_time']}, спит в {profile['sleep_time']}")
    context_lines.append(f"  Предпочтения: {profile['preferences'][:100]}")

    context_str = "\n".join(context_lines)

    prompt = f"""Для каждой задачи напиши ОДНО предложение максимум (10-15 слов):
- Почему это дело надо сделать сегодня
- Почему ты так решил
- Комментарий с учетом контекста (погода, профиль, время)

Контекст:
{context_str}

Будь практичным и конкретным. Максимум 1 предложение на задачу.

Задачи на сегодня:
{task_list}

Формат ответа (только эти строки):
Задача 1: [объяснение]
Задача 2: [объяснение]
Задача 3: [объяснение]
..."""

    print("=" * 70)
    print("PROMPT ДЛЯ CHATGPT (с контекстом)")
    print("=" * 70)
    print(prompt)
    print("\n" + "=" * 70)
    print("ОЖИДАЕМЫЙ ОТВЕТ")
    print("=" * 70)
    print("""Задача 1: В 19:00 погода будет еще хорошая (21.8°C), идеально для походов в горы.
Задача 2: Время релаксации перед сном согласно твоему расписанию.
Задача 3: Общая задача для повседневного плана.""")
    print("\n")


if __name__ == "__main__":
    show_prompt()
