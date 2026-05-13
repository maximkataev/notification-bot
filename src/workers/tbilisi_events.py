"""
Aggregates events in Tbilisi from free sources:
- visitgeorgia.ge (official tourism site)
- Google Calendar public events
- Meetup.com RSS feeds
- Direct scraping of venues (theaters, clubs, concert halls)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import httpx
from bs4 import BeautifulSoup
import feedparser

logger = logging.getLogger(__name__)

EVENT_CATEGORIES = {
    "concert": "🎵 Концерт",
    "workshop": "🎓 Воркшоп",
    "meetup": "👥 Митап",
    "sport": "⚽ Спорт",
    "festival": "🎭 Фестиваль",
    "exhibition": "🖼️ Выставка",
    "conference": "💼 Конференция",
    "other": "📅 Событие",
}


def _extract_events_from_html(
    html: str, source: str, base_url: str, max_events: int = 20
) -> Optional[List[Dict]]:
    """Extract events from HTML with multiple fallback selectors."""
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # Try multiple selector combinations (ordered by specificity)
    event_selectors = [
        ".event-item, .event-card",
        "article",
        "[data-event]",
        ".event",
        ".item",
    ]

    event_items = []
    for selector in event_selectors:
        event_items = soup.select(selector)
        if event_items:
            logger.debug(f"Found {len(event_items)} items using selector: {selector}")
            break

    if not event_items:
        logger.warning(f"No events found on {source}")
        return None

    for item in event_items[:max_events]:
        try:
            # Title extraction with multiple fallbacks
            title_elem = item.select_one("h2, h3, h4, .event-title, .title, a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Date extraction
            date_elem = item.select_one("[data-date], .date, .event-date, time")
            event_date = None
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                event_date = _parse_date(date_text)

            # Location extraction
            location_elem = item.select_one(
                "[data-location], .location, .venue, .place, .address"
            )
            location = (
                location_elem.get_text(strip=True) if location_elem else "Тбилиси"
            )

            # Description extraction
            desc_elem = item.select_one(".description, .summary, .info, p")
            description = (
                desc_elem.get_text(strip=True)[:200] if desc_elem else ""
            )

            # URL extraction
            link_elem = item.select_one("a[href]")
            url = link_elem.get("href", "") if link_elem else ""
            if url and not url.startswith("http"):
                url = base_url + url

            category = _categorize_event(title, description)

            # Add event if it has title (date optional as it may be on detail page)
            if title:
                events.append(
                    {
                        "title": title,
                        "date": event_date,
                        "time": None,
                        "location": location,
                        "description": description,
                        "category": category,
                        "source": source,
                        "url": url,
                    }
                )
        except Exception as e:
            logger.debug(f"Error parsing event from {source}: {e}")
            continue

    return events if events else None


async def get_tbilisi_events(days_ahead: int = 7) -> List[Dict]:
    """
    Aggregates events in Tbilisi from multiple free sources.

    Args:
        days_ahead: Number of days to look ahead (default 7 for next week)

    Returns:
        List of events, each with:
        - title: Event name
        - date: YYYY-MM-DD
        - time: HH:MM or None
        - location: Venue/location name
        - description: Brief description
        - category: event type (concert, workshop, etc)
        - source: Where we found it
        - url: Link to event details
    """

    tasks = [
        _scrape_visitgeorgia(days_ahead),
        _scrape_tkt_ge(),
        _scrape_google_calendar(days_ahead),
        _scrape_meetup_rss(),
        _scrape_venue_websites(days_ahead),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    events = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Error fetching events: {result}")
            continue
        if result:
            events.extend(result)

    # Remove duplicates and sort by date
    events = _deduplicate_events(events)
    events.sort(key=lambda e: (e.get("date", ""), e.get("time", "23:59")))

    return events


async def _scrape_visitgeorgia(days_ahead: int) -> Optional[List[Dict]]:
    """Scrape events from visitgeorgia.ge"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://www.visitgeorgia.ge/en/events",
                follow_redirects=True
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"visitgeorgia.ge error: {e}")
        return None

    return _extract_events_from_html(
        response.text,
        source="visitgeorgia.ge",
        base_url="https://www.visitgeorgia.ge"
    )


async def _scrape_tkt_ge() -> Optional[List[Dict]]:
    """Scrape events from tkt.ge (Georgian ticket/events site)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://tkt.ge/en/events",
                follow_redirects=True
            )
            response.raise_for_status()
    except Exception as e:
        logger.error(f"tkt.ge error: {e}")
        return None

    return _extract_events_from_html(
        response.text,
        source="tkt.ge",
        base_url="https://tkt.ge"
    )


async def _scrape_google_calendar(days_ahead: int) -> Optional[List[Dict]]:
    """Scrape public Google Calendar events for Tbilisi"""
    # This would require a specific calendar URL or feed
    # For now, return None (can be extended if public calendars found)
    # Example: https://calendar.google.com/calendar/r/month/2024/5/1?cid=<calendar-id>
    return None


async def _scrape_meetup_rss() -> Optional[List[Dict]]:
    """Scrape Meetup.com RSS feeds for Tbilisi events"""
    try:
        # Meetup RSS feed for Tbilisi (general)
        feed_url = "https://www.meetup.com/find/tbilisi/events/rss/xml/"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Meetup RSS error: {e}")
        return None

    events = []
    feed = feedparser.parse(response.text)

    for entry in feed.entries[:20]:
        try:
            title = entry.get("title", "").strip()
            if not title:
                continue

            # Parse published date
            published = entry.get("published", "")
            event_date = _parse_date(published)

            # Extract location from summary
            summary = entry.get("summary", "")
            soup = BeautifulSoup(summary, "html.parser")
            location_text = soup.get_text(strip=True)[:100]

            url = entry.get("link", "")

            category = _categorize_event(title, summary)

            events.append({
                "title": title,
                "date": event_date,
                "time": None,
                "location": "Тбилиси",
                "description": location_text,
                "category": category,
                "source": "meetup.com",
                "url": url,
            })
        except Exception as e:
            logger.debug(f"Error parsing Meetup entry: {e}")
            continue

    return events if events else None


async def _scrape_venue_websites(days_ahead: int) -> Optional[List[Dict]]:
    """Scrape local venue websites for events"""

    venues = [
        {
            "name": "Mtavari Theatre",
            "url": "https://mtavari.ge",
            "selector": ".event, .performance, article",
        },
        {
            "name": "Palace of Culture",
            "url": "https://palaceofculture.ge",
            "selector": ".event, .performance",
        },
        {
            "name": "Art Hall",
            "url": "https://arthall.ge",
            "selector": ".exhibition, .event",
        },
    ]

    events = []

    for venue in venues:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(venue["url"], follow_redirects=True)
                response.raise_for_status()
        except Exception as e:
            logger.debug(f"Error fetching {venue['name']}: {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        event_items = soup.select(venue["selector"])

        for item in event_items[:10]:
            try:
                title = item.get_text(strip=True)[:100]
                if not title or len(title) < 3:
                    continue

                link = item.select_one("a[href]")
                url = link.get("href", "") if link else ""
                if url and not url.startswith("http"):
                    url = venue["url"] + url

                category = _categorize_event(title, "")

                events.append({
                    "title": title,
                    "date": None,  # Would need more parsing
                    "time": None,
                    "location": venue["name"],
                    "description": "",
                    "category": category,
                    "source": venue["name"],
                    "url": url,
                })
            except Exception as e:
                logger.debug(f"Error parsing {venue['name']} item: {e}")
                continue

    return events if events else None


def _parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD"""
    if not date_str:
        return None

    date_str = date_str.strip()

    # Try common formats
    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try to extract ISO date from string
    if len(date_str) >= 10:
        potential_date = date_str[:10]
        try:
            datetime.strptime(potential_date, "%Y-%m-%d")
            return potential_date
        except ValueError:
            pass

    return None


def _categorize_event(title: str, description: str) -> str:
    """Categorize event based on keywords"""

    text = (title + " " + description).lower()

    keywords = {
        "concert": ["concert", "музыка", "musician", "band", "live", "концерт"],
        "workshop": [
            "workshop", "воркшоп", "training", "course", "обучение", "класс"
        ],
        "meetup": ["meetup", "meeting", "gathering", "встреча", "собрание"],
        "sport": [
            "sport", "match", "game", "football", "спорт", "матч", "футбол",
            "basketball", "tennis", "wrestling"
        ],
        "festival": [
            "festival", "фестиваль", "carnival", "feast", "celebration"
        ],
        "exhibition": [
            "exhibition", "выставка", "gallery", "museum", "art", "show"
        ],
        "conference": [
            "conference", "конференция", "summit", "congress", "forum"
        ],
    }

    for category, keywords_list in keywords.items():
        if any(kw in text for kw in keywords_list):
            return category

    return "other"


def _deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events based on title and location"""

    seen = set()
    unique = []

    for event in events:
        key = (
            event.get("title", "").lower(),
            event.get("location", "").lower(),
            event.get("date", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(event)

    return unique


def format_events_for_telegram(events: List[Dict]) -> str:
    """Format events list for Telegram message"""

    if not events:
        return "На следующую неделю в Тбилиси пока ничего не найдено 🤔"

    today = datetime.now().date()
    lines = ["📅 *События в Тбилиси на следующую неделю:*\n"]

    current_date = None
    for event in events:
        event_date = event.get("date")

        # Skip past events
        if event_date:
            try:
                event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
                if event_dt < today or event_dt > today + timedelta(days=7):
                    continue
            except ValueError:
                continue

        # Add date header
        if event_date != current_date:
            current_date = event_date
            if event_date:
                try:
                    date_obj = datetime.strptime(event_date, "%Y-%m-%d").date()
                    day_name = _get_day_name_ru(date_obj)
                    lines.append(f"\n*{day_name} ({event_date}):*")
                except ValueError:
                    pass

        # Format event
        emoji = {
            "concert": "🎵",
            "workshop": "🎓",
            "meetup": "👥",
            "sport": "⚽",
            "festival": "🎭",
            "exhibition": "🖼️",
            "conference": "💼",
            "other": "📅",
        }.get(event.get("category"), "📅")

        title = event.get("title", "")
        location = event.get("location", "")
        time_str = f" в {event.get('time')}" if event.get("time") else ""

        line = f"{emoji} {title}"
        if location:
            line += f" ({location})"
        if time_str:
            line += time_str

        url = event.get("url")
        if url:
            line += f"\n   [Подробнее]({url})"

        lines.append(line)

    return "\n".join(lines)


def _get_day_name_ru(date: datetime.date) -> str:
    """Get Russian day name for date"""
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    return days[date.weekday()]
