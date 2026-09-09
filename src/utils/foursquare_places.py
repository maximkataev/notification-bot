"""Foursquare Places API — verify that an AI-recommended place actually exists.

Used by place_recommender.py to guard against LLM hallucination: gpt-5.4-mini is
asked to recommend a real place, but nothing stops it from inventing a plausible
name on a real street in a real neighborhood. Before a place is shown in the
digest, its name is looked up on Foursquare near the target city; only a real,
matching result is accepted.

Per project rules (CLAUDE.md — NO HARDCODED FALLBACKS / real data only): a failed
or unavailable lookup must NOT be treated as "assume it's real". The caller is
expected to skip the place (or retry with a different candidate) whenever this
returns None.

Auth note: this uses the current Places API (places-api.foursquare.com), which
requires a "Service API Key" generated from the Foursquare Developer Console
(Project → Settings → Service API Keys → Generate Service API Key). The old v3
API keys (api.foursquare.com/v3, plain `Authorization: <key>` header) were fully
retired by Foursquare (410 Gone) and will not work here.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

import httpx

from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

FOURSQUARE_SEARCH_URL = "https://places-api.foursquare.com/places/search"
FOURSQUARE_API_VERSION = "2025-06-17"

# City center + search radius (meters), wide enough to cover the neighborhoods
# the recommender talks about (e.g. all of central Tbilisi).
_CITY_COORDS = {
    "tbilisi": (41.7151, 44.8271, 15000),
    "vienna": (48.2082, 16.3738, 12000),
}

_api_key_cache: Optional[str] = None
_api_key_fetched = False


def _get_api_key() -> Optional[str]:
    global _api_key_cache, _api_key_fetched
    if not _api_key_fetched:
        _api_key_cache = get_secret("FOURSQUARE_API_KEY")
        _api_key_fetched = True
        if not _api_key_cache:
            logger.error(
                "FOURSQUARE_API_KEY not set — place-of-day verification is disabled, "
                "AI-recommended places cannot be confirmed real"
            )
    return _api_key_cache


def _normalize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9а-яё\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# Generic venue-type words, stripped before the fuzzy match. Without this, two
# DIFFERENT businesses that share a common category word (e.g. "Ravi Coffee
# Roasters" vs. the real "Shavi Coffee Roasters") score a deceptively high
# whole-string ratio (0.93) because "coffee roasters" dominates the comparison
# and masks the one word that actually identifies the business.
_GENERIC_WORDS = {
    "coffee", "cafe", "kafe", "roasters", "roastery", "restaurant", "bar", "bistro",
    "kitchen", "bakery", "house", "hotel", "hostel", "rooms", "room", "wine", "winebar",
    "pub", "lounge", "club", "market", "deli", "grill", "tea", "teahouse", "shop", "store",
    "studio", "gallery", "park", "garden", "place", "spot", "corner", "the", "and",
    "кофейня", "кафе", "ресторан", "бар", "паб", "бистро", "пекарня", "отель", "хостел",
    "чайная", "магазин", "галерея", "парк", "сад", "и",
}


def _core(name: str) -> str:
    """Normalized name with generic venue-type words stripped, leaving the
    distinctive part (the actual brand/proper name) to compare on."""
    tokens = [t for t in _normalize(name).split() if t not in _GENERIC_WORDS]
    return " ".join(tokens) if tokens else _normalize(name)


def _names_match(a: str, b: str) -> bool:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    core_a, core_b = _core(a), _core(b)
    if not core_a or not core_b:
        return False
    if core_a == core_b:
        return True
    return SequenceMatcher(None, core_a, core_b).ratio() >= 0.75


async def verify_place_exists(name: str, city: str = "tbilisi") -> Optional[Dict[str, Any]]:
    """Check whether `name` matches a real place on Foursquare near `city`.

    Returns the matched Foursquare result ({"name", "address"}) if a close name
    match is found among nearby results, else None. None covers both "no match"
    and "lookup failed/unconfigured" — callers must treat both as unverified.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    lat, lon, radius = _CITY_COORDS.get(city, _CITY_COORDS["tbilisi"])

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                FOURSQUARE_SEARCH_URL,
                params={
                    "query": name,
                    "ll": f"{lat},{lon}",
                    "radius": radius,
                    "limit": 5,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "X-Places-Api-Version": FOURSQUARE_API_VERSION,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning(f"Foursquare lookup failed for '{name}' [{city}]: {type(e).__name__}: {e}")
        return None

    for result in data.get("results", []):
        fsq_name = result.get("name", "")
        if _names_match(name, fsq_name):
            location = result.get("location", {})
            address = location.get("formatted_address", "")
            logger.info(f"✓ Verified '{name}' → Foursquare '{fsq_name}' ({address})")
            return {"name": fsq_name, "address": address}

    logger.warning(f"✗ Could not verify '{name}' [{city}] on Foursquare — likely hallucinated, rejecting")
    return None
