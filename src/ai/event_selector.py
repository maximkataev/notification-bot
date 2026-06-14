"""Curate Tbilisi events via ChatGPT.

Picks the most interesting, category-balanced subset of events for the weekly
digest instead of dumping every scraped item chronologically. Drops low-signal
placeholder entries and (optionally) matches the user's interests. Real data only:
GPT only REORDERS/SELECTS from the events passed in — it never invents events.
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Generic placeholder titles (no real event name) — dropped before selection.
_JUNK_TITLES = {
    "event", "событие", "концерт в тбилиси", "киносеанс", "unknown event", "tbilisi",
}


def _profile_interests(user_profile) -> str:
    """Extract free-text interests from a UserProfile dataclass or dict."""
    if not user_profile:
        return ""
    if hasattr(user_profile, "preferences"):
        return getattr(user_profile, "preferences", "") or ""
    if isinstance(user_profile, dict):
        return user_profile.get("preferences", "") or ""
    return ""


def _fallback(events: List[Dict[str, Any]], max_events: int) -> List[Dict[str, Any]]:
    """Junk-filtered, chronological top-N — used when GPT is unavailable."""
    filtered = [e for e in events if e.get("title", "").strip().lower() not in _JUNK_TITLES]
    return (filtered or events)[:max_events]


async def select_events_with_gpt(
    events: List[Dict[str, Any]],
    user_profile=None,
    max_events: int = 10,
) -> List[Dict[str, Any]]:
    """Return up to `max_events` curated events (GPT-selected, balanced by category).

    Falls back to a junk-filtered chronological top-N if GPT is unavailable or fails.
    """
    if not events:
        return events

    # Drop obvious placeholder-titled items up front
    candidates = [e for e in events if e.get("title", "").strip().lower() not in _JUNK_TITLES]
    if not candidates:
        candidates = list(events)

    # If we already have few enough, no need to call GPT
    if len(candidates) <= max_events:
        return candidates

    import os
    from src.utils.doppler import get_secret

    try:
        indexed = []
        for idx, e in enumerate(candidates):
            indexed.append({
                "index": idx,
                "title": e.get("title", ""),
                "category": e.get("category", "other"),
                "date": e.get("date", ""),
                "time": e.get("time", ""),
                "location": e.get("location", ""),
                "source": e.get("source", ""),
            })

        interests = _profile_interests(user_profile)
        interests_block = (
            f"\nИнтересы пользователя (учитывай при отборе): {interests}\n"
            if interests else ""
        )

        system_prompt = (
            "Ты — городской куратор афиши Тбилиси. Из списка событий выбираешь самые "
            "интересные и разнообразные для еженедельного дайджеста. Возвращаешь ТОЛЬКО JSON."
        )

        user_prompt = f"""Вот список реальных событий в Тбилиси на ближайшую неделю. Отбери до {max_events} САМЫХ интересных и достойных афиши.

ПРАВИЛА ОТБОРА:
- ТОЛЬКО Тбилиси. Если по названию/локации видно, что событие в другом городе или онлайн — НЕ бери.
- БЕЗ повторов: одно и то же событие (тот же фильм/спектакль/концерт/выставка) в разные даты или на разных площадках бери МАКСИМУМ ОДИН раз. Не давай одному фильму занять несколько слотов.
- Разнообразие по категориям: концерты 🎵, выставки 🖼️, фестивали 🎭, спорт ⚽, театр, воркшопы, заметные митапы. Не бери 10 однотипных IT-митапов.
- Приоритет ярким, уникальным, культурным событиям.
- Пропусти мусор: пустые/служебные названия, рекламу, события без смысла.
- Сохрани хронологический порядок внутри выбранных (по дате/времени).{interests_block}
СОБЫТИЯ:
{json.dumps(indexed, ensure_ascii=False, indent=2)}

Ответь СТРОГО в JSON (без пояснений), список индексов выбранных событий в порядке показа:
{{"selected": [<index>, <index>, ...]}}"""

        api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-5.4-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.4,
                    "max_completion_tokens": 300,
                },
            )

        if response.status_code != 200:
            logger.error(f"Event selection OpenAI error: {response.status_code} - {response.text[:200]}")
            return _fallback(candidates, max_events)

        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Extract JSON object
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.warning("Event selection: no JSON in GPT response, using fallback")
            return _fallback(candidates, max_events)

        data = json.loads(match.group(0))
        selected_indices = data.get("selected", [])
        if not isinstance(selected_indices, list):
            logger.warning("Event selection: 'selected' not a list, using fallback")
            return _fallback(candidates, max_events)

        # Map indices back to events (dedupe, validate, preserve GPT order)
        seen = set()
        chosen = []
        for i in selected_indices:
            if isinstance(i, int) and 0 <= i < len(candidates) and i not in seen:
                seen.add(i)
                chosen.append(candidates[i])
            if len(chosen) >= max_events:
                break

        if not chosen:
            logger.warning("Event selection: GPT returned no valid indices, using fallback")
            return _fallback(candidates, max_events)

        logger.info(f"✓ GPT curated {len(chosen)}/{len(candidates)} events for the digest")
        return chosen

    except Exception as e:
        logger.error(f"Event selection failed ({type(e).__name__}: {e}), using fallback")
        return _fallback(candidates, max_events)
