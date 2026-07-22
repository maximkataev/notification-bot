"""Joke of the day (анекдот дня, «категория Б») from real sources — NOT AI-generated.

Per user requirement the joke must be FOUND, not invented, so it is fetched from
real joke services:

1. Primary: rzhunemogu.ru random-joke API, CType=11 (анекдоты 18+ — «категория Б»).
   NOTE: the API declares utf-8 in the XML header but actually returns
   windows-1251 bytes — decode manually.
2. Fallback: anekdot.ru RSS "свежая десятка" (today's top-10 jokes).

History: shown jokes are persisted to data/joke_history.json for 28 days and used
as a dedup list, so a joke is never repeated within a 28-day window. Entries older
than 28 days are dropped on each run. The chosen joke is cached per day, so all
recipients get the same joke on a given date.

Per project rules: NO HARDCODED FALLBACKS — if all sources fail, return None and
the scheduler simply omits the section.
"""

import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
import feedparser

logger = logging.getLogger(__name__)

# Jokes shown within this window are excluded and never repeated.
_HISTORY_DAYS = 28
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
_HISTORY_PATH = os.path.join(_DATA_DIR, "joke_history.json")

# rzhunemogu.ru: CType=11 = анекдоты 18+ («категория Б»)
_RZHUNEMOGU_URL = "http://rzhunemogu.ru/Rand.aspx?CType=11"
# How many random draws to try before giving up on a non-repeated joke
_RZHUNEMOGU_ATTEMPTS = 5

_ANEKDOT_RU_RSS = "https://www.anekdot.ru/rss/export_j.xml"

_REQUEST_TIMEOUT = 10.0


def _normalize(text: str) -> str:
    """Normalize joke text for dedup comparison (case/whitespace-insensitive)."""
    return re.sub(r"\s+", " ", text).strip().lower()


# rzhunemogu hard-wraps lines at roughly this width; lines at or above it are
# treated as wrapped and re-joined with their continuation.
_WRAP_WIDTH = 55


def _unwrap(text: str) -> str:
    """Undo the source's hard line-wrapping while keeping dialogue lines intact.

    rzhunemogu returns text wrapped at ~60 chars with \\r\\n mid-sentence. A line
    is considered wrapped (and joined with the next one) when it is long enough
    to hit the wrap width and the next line is not a new dialogue cue ("- ...").
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out and len(out[-1]) >= _WRAP_WIDTH and not line.startswith(("-", "—")):
            out[-1] += " " + line
        else:
            out.append(line)
    return "\n".join(out)


def _load_history() -> List[Dict[str, Any]]:
    """Load the joke history list (oldest → newest). Returns [] on any error."""
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Could not read joke history: {type(e).__name__}: {e}")
    return []


def _trim_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only entries from the last _HISTORY_DAYS days."""
    cutoff = (datetime.now() - timedelta(days=_HISTORY_DAYS)).strftime("%Y-%m-%d")
    return [h for h in history if h.get("date", "") >= cutoff]


def _save_history(history: List[Dict[str, Any]]) -> None:
    """Persist the joke history (trimmed to the last _HISTORY_DAYS days)."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(_trim_history(history), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Could not write joke history: {type(e).__name__}: {e}")


async def _fetch_rzhunemogu() -> Optional[str]:
    """Fetch one random 18+ joke from rzhunemogu.ru. Returns joke text or None."""
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(_RZHUNEMOGU_URL)
            response.raise_for_status()

        # The XML header claims utf-8 but the bytes are windows-1251
        raw = response.content.decode("windows-1251", errors="replace")
        match = re.search(r"<content>(.*?)</content>", raw, re.DOTALL)
        if not match:
            logger.warning("rzhunemogu: no <content> in response")
            return None

        text = _unwrap(match.group(1).strip())
        return text or None
    except Exception as e:
        logger.warning(f"rzhunemogu fetch failed: {type(e).__name__}: {str(e)[:100]}")
        return None


async def _fetch_anekdot_ru() -> List[Dict[str, str]]:
    """Fetch today's top-10 jokes from anekdot.ru RSS. Returns [{text, url}, ...]."""
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(_ANEKDOT_RU_RSS)
            response.raise_for_status()

        feed = feedparser.parse(response.content)
        jokes = []
        for entry in feed.entries:
            # Joke text lives in the description as HTML with <br> line breaks
            desc = entry.get("description", "") or entry.get("summary", "")
            if not desc:
                continue
            text = re.sub(r"<br\s*/?>", "\n", desc)
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                jokes.append({"text": text, "url": entry.get("link", "")})
        return jokes
    except Exception as e:
        logger.warning(f"anekdot.ru RSS fetch failed: {type(e).__name__}: {str(e)[:100]}")
        return []


async def get_joke_of_day() -> Optional[Dict[str, Any]]:
    """Fetch the joke of the day from real sources, avoiding repeats within 28 days.

    Returns:
        {
            "text": str,    # joke text
            "source": str,  # "rzhunemogu.ru" | "anekdot.ru"
            "url": str,     # link to the joke ("" if the source has none)
        }
        or None if all sources fail.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    history = _trim_history(_load_history())

    # Same day → return the already-chosen joke so every recipient sees the same one.
    if history and history[-1].get("date") == today:
        cached = {k: v for k, v in history[-1].items() if k != "date"}
        logger.info(f"Joke of day (cached for {today}): {cached.get('text', '')[:50]}...")
        return cached

    shown = {_normalize(h.get("text", "")) for h in history if h.get("text")}

    result = None

    # Primary source: rzhunemogu.ru (random draw, retry on repeats)
    for attempt in range(_RZHUNEMOGU_ATTEMPTS):
        text = await _fetch_rzhunemogu()
        if not text:
            break  # source is down, no point retrying
        if _normalize(text) in shown:
            logger.info(f"rzhunemogu: joke already shown (attempt {attempt + 1}), retrying")
            continue
        result = {"text": text, "source": "rzhunemogu.ru", "url": ""}
        break

    # Fallback: anekdot.ru top-10 of the day
    if result is None:
        logger.info("Falling back to anekdot.ru RSS")
        jokes = await _fetch_anekdot_ru()
        random.shuffle(jokes)
        for joke in jokes:
            if _normalize(joke["text"]) not in shown:
                result = {"text": joke["text"], "source": "anekdot.ru", "url": joke["url"]}
                break

    if result is None:
        logger.warning("Joke of day: all sources failed or exhausted, skipping")
        return None

    # Record in history (keyed by date) so it is not repeated for 28 days.
    history.append({"date": today, **result})
    _save_history(history)

    logger.info(f"✓ Joke of day [{result['source']}]: {result['text'][:60]}...")
    return result
