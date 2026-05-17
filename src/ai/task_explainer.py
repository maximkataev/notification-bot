"""Generate comprehensive AI task analysis and recommendations."""

import logging
import json
from typing import List, Dict, Optional
from src.db.models import Task
from src.utils.openai_client import get_client

logger = logging.getLogger(__name__)


async def get_task_explanations(
    tasks: List[Task], weather: Optional[Dict] = None, profile: Optional[Dict] = None
) -> Dict[int, Dict[str, any]]:
    """Generate comprehensive task analysis: what, why, how, when, difficulty, importance, and practical advice.

    Args:
        tasks: List of tasks to explain
        weather: Weather data with periods (morning/day/evening/night)
        profile: User profile (wake_time, sleep_time, preferences)

    Returns:
        Dict mapping task.id to detailed analysis:
        {
            "explanation": "Why do it today",
            "difficulty": 1-5,
            "urgency": 1-5,
            "importance": 1-5,
            "time_minutes": estimated execution time,
            "priority_rank": order (1 = first),
            "how_to_do": "Step-by-step advice",
            "what_to_bring": "Items/tools needed",
            "what_to_think": "Mental preparation / things to consider",
            "comparison": "How it relates to other tasks",
        }
    """
    if not tasks:
        return {}

    # Build task list with full context
    task_details = []
    for i, task in enumerate(tasks, 1):
        details = f"{i}. {task.what or task.raw_text}"
        constraints = getattr(task, "constraints", None)
        if constraints:
            details += f" | {constraints}"
        if task.place:
            details += f" | {task.place}"
        if task.proposed_time:
            details += f" | {task.proposed_time}"
        if task.is_urgent:
            details += " 🔴"
        if task.is_outdoor:
            details += " 🌦️"
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
                wind = data.get("wind_speed", None)
                wind_str = f", ветер {wind} м/с" if wind else ""
                context_lines.append(f"  • {period.title()}: {condition}, {temp}°C{wind_str}")

    if profile:
        context_lines.append(f"👤 Профиль:")
        wake = profile.get('wake_time', '09:00')
        sleep = profile.get('sleep_time', '23:00')
        context_lines.append(f"  • День: {wake}-{sleep}")
        if profile.get("preferences"):
            context_lines.append(f"  • Интересы: {profile['preferences'][:60]}")

    context_str = (
        "\n".join(context_lines) if context_lines else "Обычный день"
    )

    prompt = f"""Ты личный помощник по планированию. Анализируешь задачи комплексно и даёшь практические рекомендации.

ЗАДАЧИ НА СЕГОДНЯ:
{task_list}

КОНТЕКСТ:
{context_str}

ДЛЯ КАЖДОЙ ЗАДАЧИ определи:

1️⃣ СЛОЖНОСТЬ (1-5): Как сложно выполнить?
2️⃣ СРОЧНОСТЬ (1-5): Насколько срочно СЕЙЧАС?
3️⃣ ВАЖНОСТЬ (1-5): Последствия, если не сделать?
4️⃣ ВРЕМЯ: Минут на выполнение (реалистично)
5️⃣ ПРИОРИТЕТ (ранг): Порядок исполнения от 1 (первая) до N (последняя)
6️⃣ ОБЪЯСНЕНИЕ: Почему в такой очередности? (100-150 символов)
7️⃣ КАК ДЕЛАТЬ: Пошаговый алгоритм/совет (2-3 строки)
8️⃣ ЧТО ВЗЯТЬ: Материалы, инструменты, что подготовить
9️⃣ О ЧЕМ ПОДУМАТЬ: Что помнить, на что обратить внимание
🔟 ОТНОШЕНИЕ К ДРУГИМ: Зависит ли от других задач? Блокирует ли?
1️⃣1️⃣ ОПИСАНИЕ ДЛЯ ДАЙДЖЕСТА: Полноценное, связное описание ровно до 280 символов включительно
   • Комбинируй: почему делать + как делать + что взять + о чём помнить
   • РОВНО до 280 символов (не больше, не меньше)
   • Без троеточий и обрезаний
   • Законченное предложение в конце
   • Практичное, информативное, читаемое

Ответь ТОЛЬКО валидный JSON (без markdown, без комментариев):
[
  {{
    "task_index": 0,
    "difficulty": 2,
    "urgency": 4,
    "importance": 5,
    "time_minutes": 45,
    "priority_rank": 1,
    "explanation": "Критично и срочно: без этого невозможно начать остальное",
    "how_to_do": "1. Собери материалы\\n2. Выполни по плану\\n3. Проверь результат",
    "what_to_bring": "Ноутбук, ручка, блокнот",
    "what_to_think": "Возможны задержки, подготовься к импровизации",
    "comparison": "Блокирует задачи 2 и 3, делай первым",
    "digest_description": "Критично и срочно. Собери материалы, выполни по плану, проверь результат. Взять: ноутбук, ручка, блокнот. Помнить: возможны задержки, будь готов к импровизации."
  }}
]"""

    try:
        logger.info(
            f"🔄 Analyzing {len(tasks)} tasks comprehensively (difficulty, urgency, importance, time, priority, recommendations)"
        )

        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=2000,
            messages=[
                {
                    "role": "system",
                    "content": "Ты опытный личный помощник. Анализируешь задачи логично, даёшь практичные советы. Возвращаешь валидный JSON без комментариев. Рекомендации конкретные и полезные.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        response_text = response.choices[0].message.content
        logger.info(f"✓ Comprehensive task analysis received from AI")

        # Clean markdown code blocks if present
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Parse JSON response
        analysis_data = json.loads(response_text)

        # Build comprehensive explanations dict
        explanations = {}
        for item in analysis_data:
            task_idx = item.get("task_index", 0)
            if 0 <= task_idx < len(tasks):
                task = tasks[task_idx]
                explanations[task.id] = {
                    "explanation": item.get("explanation", ""),
                    "difficulty": item.get("difficulty", 2),
                    "urgency": item.get("urgency", 2),
                    "importance": item.get("importance", 2),
                    "time_minutes": item.get("time_minutes", 30),
                    "priority_rank": item.get("priority_rank", 999),
                    "how_to_do": item.get("how_to_do", ""),
                    "what_to_bring": item.get("what_to_bring", ""),
                    "what_to_think": item.get("what_to_think", ""),
                    "comparison": item.get("comparison", ""),
                    "digest_description": item.get("digest_description", ""),
                }

        if len(explanations) < len(tasks):
            logger.warning(
                f"⚠️  Only parsed {len(explanations)}/{len(tasks)} task analyses"
            )

        logger.info(f"✓ Analyzed {len(explanations)} tasks with all metrics")
        return explanations

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️  Failed to parse JSON response: {e}")
        logger.debug(f"Response was: {response_text[:500]}")
        return {}
    except Exception as e:
        logger.warning(f"⚠️  Failed to generate task analysis: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return {}
