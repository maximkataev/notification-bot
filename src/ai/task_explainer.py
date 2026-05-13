"""Generate AI explanations for tasks."""

import logging
import json
from typing import List, Dict, Optional
from src.db.models import Task
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)


async def get_task_explanations(
    tasks: List[Task], weather: Optional[Dict] = None, profile: Optional[Dict] = None
) -> Dict[int, Dict[str, any]]:
    """Generate detailed AI explanations for tasks: what, why, how, when, and purpose.

    Args:
        tasks: List of tasks to explain
        weather: Weather data with periods (morning/day/evening/night)
        profile: User profile (wake_time, sleep_time, preferences)
    """
    if not tasks:
        return {}

    # Build task list with full context
    task_details = []
    for i, task in enumerate(tasks, 1):
        details = f"{i}. {task.what or task.raw_text}"
        constraints = getattr(task, "constraints", None)
        if constraints:
            details += f" (ограничения: {constraints})"
        if task.place:
            details += f" | место: {task.place}"
        if task.proposed_time:
            details += f" | время: {task.proposed_time}"
        if task.is_urgent:
            details += " | 🔴 СРОЧНО"
        if task.is_outdoor:
            details += " | 🌦️ На улице"
        task_details.append(details)

    task_list = "\n".join(task_details)

    # Build rich context for AI
    context_lines = []

    if weather:
        context_lines.append("📋 Погода на сегодня:")
        for period, data in weather.items():
            if isinstance(data, dict):
                condition = data.get("condition", "?")
                temp = data.get("temperature", "?")
                context_lines.append(f"  • {period}: {condition}, {temp}°C")

    if profile:
        context_lines.append(f"👤 Профиль:")
        context_lines.append(
            f"  • Просыпается: {profile.get('wake_time', '09:00')}, спит: {profile.get('sleep_time', '23:00')}"
        )
        if profile.get("preferences"):
            context_lines.append(f"  • Интересы: {profile['preferences'][:80]}")

    context_str = (
        "\n".join(context_lines) if context_lines else "Контекст: стандартный день"
    )

    prompt = f"""Проанализируй КАЖДУЮ задачу и верни JSON с рекомендациями.

Для КАЖДОЙ задачи определи:
1. ОБЪЯСНЕНИЕ: Логичное, аналитичное обоснование ПОЧЕМУ делать СЕЙЧАС (до 220 символов)
   - Учитывай контекст: срочность, время, погода, загруженность дня
   - Будь прямолинейным и практичным
   - Без лишней эмоциональности, только аргументы
2. ВРЕМЯ: примерное время на выполнение в МИНУТАХ (5, 15, 30, 60, 120 и т.д.)
3. ТЯЖЕСТЬ: сложность от 1 (легко) до 5 (очень сложно)
4. ПРИОРИТЕТ: true если срочная, false если можно отложить

При анализе приоритета:
- Есть ли отметка СРОЧНО/🔴
- Есть ли указанное время (более приоритетно)
- На улице ли (зависит от погоды)
- Логическая последовательность действий

Контекст дня:
{context_str}

Задачи на сегодня:
{task_list}

Ответь ТОЛЬКО JSON (без markdown, без комментариев):
[
  {{
    "task_index": 0,
    "explanation": "Срочно: без питания невозможно работать продуктивно, особенно в начале дня когда нужна энергия",
    "time_minutes": 20,
    "difficulty": 2,
    "is_urgent": true
  }},
  {{
    "task_index": 1,
    "explanation": "Задача требует проверки функциональности, легко выполнить сейчас в рабочее время",
    "time_minutes": 15,
    "difficulty": 1,
    "is_urgent": false
  }}
]"""

    try:
        logger.info(
            f"🔄 Analyzing {len(tasks)} tasks with time, difficulty, and priority"
        )

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=800,
            messages=[
                {
                    "role": "system",
                    "content": "Ты аналитик. Анализируешь задачи логично и прямолинейно. Определяешь время, сложность, приоритет. Возвращаешь валидный JSON. Никаких комментариев, только JSON. Рекомендации практичные и обоснованные, без эмоциональности.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        response_text = response.choices[0].message.content
        logger.info(f"✓ Got task analysis from AI")

        # Clean markdown code blocks if present
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
        elif response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # Remove trailing ```
        response_text = response_text.strip()

        # Parse JSON response
        analysis_data = json.loads(response_text)

        # Build explanations dict with task_id and additional data
        explanations = {}
        for item in analysis_data:
            task_idx = item.get("task_index", 0)
            if 0 <= task_idx < len(tasks):
                task = tasks[task_idx]
                explanations[task.id] = {
                    "explanation": item.get("explanation", ""),
                    "time_minutes": item.get("time_minutes", 30),
                    "difficulty": item.get("difficulty", 2),
                    "is_urgent": item.get("is_urgent", False),
                }

        if len(explanations) < len(tasks):
            logger.warning(
                f"⚠️  Only parsed {len(explanations)}/{len(tasks)} task analyses"
            )

        logger.info(f"✓ Analyzed {len(explanations)} tasks")
        return explanations

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️  Failed to parse JSON response: {e}")
        logger.debug(f"Response was: {response_text[:200]}")
        return {}
    except Exception as e:
        logger.warning(f"⚠️  Failed to generate task analysis: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return {}


def score_task_importance(task: Task) -> int:
    """Score task importance (higher = more important)."""
    score = 0

    # Urgency: +100
    if task.is_urgent:
        score += 100

    # Outdoor tasks (weather-dependent): +30
    if task.is_outdoor:
        score += 30

    # Has specific time: +20 (means it's planned and important)
    if task.proposed_time:
        score += 20

    # Has specific date: +10
    if task.when_date:
        score += 10

    return score
