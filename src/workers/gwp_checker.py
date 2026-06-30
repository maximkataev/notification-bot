"""Check GWP (Georgian Water and Power) for water cuts affecting our street.

GWP renders "Planned Works" and "Ongoing Works" tabs from a single JSON API.
We hit that API directly instead of scraping the HTML cards, because the cards
only show a truncated head address while the full list of affected streets
(where "ვაჟა ივერიელი" actually appears) lives in the item's `emailText`.

API: https://www.gwp.ge/api/Disconnect/ByCity?cityId=1  (cityId 1 = Tbilisi)
Returns both work types in one response:
    type "გეგმიური"     → Planned Works  (scheduled-works tab)
    type "არაგეგმიური"  → Ongoing Works  (nonscheduled-works tab)
"""

import logging
import re
from datetime import date, datetime
from typing import Optional, List, Dict

import httpx

logger = logging.getLogger(__name__)

GWP_API_URL = "https://www.gwp.ge/api/Disconnect/ByCity?cityId=1"  # Tbilisi

# Streets we care about (various spellings and languages).
# Correct name is "ვაჟა ივერიელი" / "Vazha Iverieli". We match on the
# distinctive surname stem "ივერიელი" / "iverieli" so we catch the street
# regardless of how "ვაჟა" is written or whether "ქუჩა"/house number follows.
WATCH_STREETS = [
    "ვაჟა ივერიელი",  # Georgian full name
    "vazha iverieli",  # English full name
]

# Map GWP work type -> human label
TYPE_LABELS = {
    "გეგმიური": "Planned",
    "არაგეგმიური": "Ongoing",
}


async def _fetch_disconnections() -> List[Dict]:
    """Fetch the raw list of current water disconnections from the GWP API.

    Returns both planned and ongoing works. Empty list on any failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GWP_API_URL,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            logger.warning(f"GWP API returned unexpected payload type: {type(data)}")
            return []
    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch GWP API: {type(e).__name__}: {e}")
        logger.debug("Full error:", exc_info=True)
        return []


def _item_blob(item: Dict) -> str:
    """Concatenate all street-bearing text fields of a work item."""
    parts = [item.get("emailText"), item.get("address"), item.get("smsText")]
    return " ".join(p for p in parts if p)


def _match_street(item: Dict) -> Optional[str]:
    """Return the matched watch-street if this work mentions our street."""
    blob = _item_blob(item).lower()
    for street in WATCH_STREETS:
        if street.lower() in blob:
            return street
    return None


async def check_gwp_works() -> Optional[List[str]]:
    """Check GWP (both planned + ongoing) for works affecting our street.

    Returns a list of human-readable strings, or None if nothing matches.
    """
    items = await _fetch_disconnections()
    works_found = []

    for item in items:
        if not _match_street(item):
            continue

        label = TYPE_LABELS.get(item.get("type", ""), item.get("type", ""))
        district = item.get("district") or ""
        when = _extract_water_cut_time(_item_blob(item), "iverieli")

        if when:
            detail = when
        else:
            detail = f"{district}, {item.get('address', '')}".strip(", ")

        works_found.append(f"{label} work: {detail}")
        logger.info(f"Found GWP work on Vazha Iverieli ({label}): {detail}")

    if works_found:
        logger.info(f"✓ Found {len(works_found)} works on Vazha Iverieli")
        return works_found

    logger.info("No works found on Vazha Iverieli")
    return None


async def check_water_cuts() -> Optional[str]:
    """Return a human-readable water-cut summary for our street (digest section).

    Aggregates all matching planned/ongoing works into one string, or None.
    """
    items = await _fetch_disconnections()
    lines = []

    for item in items:
        if not _match_street(item):
            continue
        when = _extract_water_cut_time(_item_blob(item), "iverieli")
        if when:
            lines.append(when)
        else:
            district = item.get("district") or ""
            lines.append(
                f"{district}: ожидается отключение воды на улице "
                f"ვაჟა ივერიელი (Vazha Iverieli)".strip()
            )

    if lines:
        # De-duplicate while preserving order
        seen = set()
        unique = [l for l in lines if not (l in seen or seen.add(l))]
        return "\n".join(unique)

    return None


async def check_water_cuts_today() -> Optional[str]:
    """Return current/upcoming water-cut info for our street (hourly monitor).

    The GWP API only returns *active* disconnections (status "მიმდინარე"), so a
    match on our street is relevant right now. We still drop entries whose date
    is clearly in the past. Dates are compared in Tbilisi time (the server may
    run in UTC, which would otherwise shift `today` and silently hide a cut).
    """
    items = await _fetch_disconnections()
    today = _tbilisi_today()

    for item in items:
        if not _match_street(item):
            continue
        result = _extract_water_cut_time(_item_blob(item), "iverieli")
        if not result:
            # Street is listed but we couldn't parse a date — alert anyway,
            # since the API only lists active works.
            district = item.get("district") or ""
            fallback = (
                f"{district}: отключение воды на улице "
                f"ვაჟა ივერიელი (Vazha Iverieli)"
            ).strip()
            logger.info(f"Water cut (no parsable date) on Vazha Iverieli: {fallback}")
            return fallback

        # Drop only entries that are strictly in the past (stale).
        cut_date = result[:10]  # "YYYY-MM-DD"
        if cut_date >= today.isoformat():
            logger.info(f"Water cut on Vazha Iverieli: {result}")
            return result
        logger.debug(f"Water cut found but date is in the past, skipping: {result}")

    return None


def _tbilisi_today() -> date:
    """Today's date in Asia/Tbilisi (independent of server timezone)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Tbilisi")).date()
    except Exception:
        return date.today()


def _extract_water_cut_time(article_text: str, street: str) -> Optional[str]:
    """Extract water cut date/time range from text.

    Looks for patterns like "6/30/2026 11:00 დან 6/30/2026 23:00".

    Returns:
        "2026-06-30 ожидается отключение воды с 11:00 по 23:00 на улице ვაჟა ივერიელი (Vazha Iverieli)"
        or None if time cannot be extracted.
    """
    try:
        date_time_pattern = (
            r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}).*?(\d{1,2}):(\d{2})"
        )
        match = re.search(date_time_pattern, article_text)
        if not match:
            logger.debug("Could not extract date/time range from text")
            return None

        month, day, year, start_hour, start_min, end_hour, end_min = match.groups()

        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        start_time = f"{start_hour.zfill(2)}:{start_min}"
        end_time = f"{end_hour.zfill(2)}:{end_min}"

        street_text = "ვაჟა ივერიელი (Vazha Iverieli)"
        message = (
            f"{date_str} ожидается отключение воды с {start_time} "
            f"по {end_time} на улице {street_text}"
        )
        logger.info(f"Extracted water cut: {message}")
        return message

    except Exception as e:
        logger.warning(f"Failed to extract water cut time: {type(e).__name__}: {e}")
        return None
