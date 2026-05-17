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
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

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
    Aggregates events in Tbilisi from available free sources.

    Args:
        days_ahead: Number of days to look ahead (default 7 for next week)

    Returns:
        List of events sorted by date
    """

    logger.debug("🎬 Fetching events from Tbilisi sources...")

    tasks = [
        _scrape_redevents(),           # Russian events site
        _scrape_eventbrite(),          # Eventbrite Georgia/Tbilisi
        _scrape_meetup_tbilisi(),      # Meetup.com Tbilisi events
        _scrape_cinemaqa(),            # Georgian cinema - movie showtimes
        # TODO: biletebi.ge and georgia.travel need better selectors
        # _scrape_biletebi(),            # Georgian tickets site (needs HTML structure fix)
        # _scrape_georgia_travel(),      # Official tourism portal (needs HTML structure fix)
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
    if events:
        events = _deduplicate_events(events)
        # Sort by date (None dates go to end), then by time
        events.sort(key=lambda e: (e.get("date") or "9999-12-31", e.get("time") or "23:59"))
        logger.info(f"✅ Total events fetched: {len(events)}")
    else:
        logger.warning("⚠️ No events found")

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


async def _scrape_redevents() -> Optional[List[Dict]]:
    """Scrape events from redevents.ge using Playwright (JS-rendered)"""
    try:
        async with async_playwright() as p:
            logger.debug("🎬 Playwright: redevents.ge")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Load page
                await asyncio.wait_for(
                    page.goto("https://redevents.ge/ru", wait_until="networkidle"),
                    timeout=20.0
                )

                # Wait for events to render
                await asyncio.sleep(2)

                html = await page.content()
                logger.debug(f"📄 HTML: {len(html)} bytes")
                await browser.close()

                # Clean HTML and search for dates
                import re
                html_clean = re.sub(r'<[^>]+>', '', html)

                # Parse HTML for detailed extraction
                soup = BeautifulSoup(html, "html.parser")
                events = []

                months_ru = {
                    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                    'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                    'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
                }
                current_year = datetime.now().year

                # Look for date patterns in cleaned HTML
                # Pattern handles: "23 мая 20:00" or "23 мая в 20:00"
                date_pattern = r'(\d{1,2})\s+(\w+)\s+[в]?\s*(\d{2}):(\d{2})'
                matches = list(re.finditer(date_pattern, html_clean))
                logger.debug(f"Found {len(matches)} date matches")

                # Find actual event elements with links for URLs
                event_links = {}
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if 'event' in href.lower() or 'ticket' in href.lower():
                        text = link.get_text(strip=True)[:100]
                        event_links[text] = href

                logger.debug(f"Found {len(event_links)} event links")

                for match in matches:
                    try:
                        day = int(match.group(1))
                        month_str = match.group(2).lower()
                        hour = match.group(3)
                        minute = match.group(4)

                        month = months_ru.get(month_str)
                        logger.debug(f"Found: {day} {month_str} {hour}:{minute}, month_num={month}")

                        if not month or day > 31:
                            logger.debug(f"  Skipped: month={month}, day={day}")
                            continue

                        date_obj = datetime(current_year, month, day)
                        date_str = date_obj.strftime("%Y-%m-%d")
                        time_str = f"{hour}:{minute}"

                        # Try to find event title near this date
                        # Look backwards from match position to find title
                        context_start = max(0, match.start() - 300)
                        context = html_clean[context_start:match.start()]

                        # Split by common separators to find event name
                        title = "Концерт в Тбилиси"  # Default title
                        for sep in ['\n', '•', '|', ' - ']:
                            parts = context.split(sep)
                            if parts:
                                potential_title = parts[-1].strip()
                                if len(potential_title) > 5 and len(potential_title) < 200:
                                    # Check if it looks like an event name (has letters)
                                    if any(c.isalpha() for c in potential_title):
                                        title = potential_title
                                        break

                        # Clean up title
                        title = title.strip()
                        if len(title) > 100:
                            title = title[:100]

                        # Try to find URL for this event
                        url = "https://redevents.ge/ru"
                        for event_text, event_url in event_links.items():
                            if title.lower() in event_text.lower() or event_text.lower() in title.lower():
                                url = event_url if event_url.startswith('http') else "https://redevents.ge" + event_url
                                break

                        # Avoid duplicates
                        if not any(e['date'] == date_str and e['time'] == time_str for e in events):
                            category = _categorize_event(title, "")
                            events.append({
                                "title": title,
                                "date": date_str,
                                "time": time_str,
                                "location": "Tbilisi",
                                "description": "",
                                "category": category,
                                "source": "redevents.ge",
                                "url": url,
                                "price": "По ссылке",
                            })
                            logger.debug(f"✅ Added: {title[:40]} on {date_str}")

                    except (ValueError, IndexError) as e:
                        logger.debug(f"Error: {e}")
                        continue

                if events:
                    logger.info(f"✅ Found {len(events)} events from redevents.ge")
                    return events

                logger.warning("⚠️ No events parsed from redevents.ge")
                return None

            except asyncio.TimeoutError:
                logger.warning("⏱️ redevents.ge timeout")
                await browser.close()
                return None
            except Exception as e:
                logger.error(f"redevents.ge parse error: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    except Exception as e:
        logger.error(f"redevents.ge browser error: {e}")
        return None


async def _scrape_biletebi() -> Optional[List[Dict]]:
    """Scrape events from biletebi.ge using text-based regex parsing"""
    try:
        logger.debug("🎬 Playwright: biletebi.ge")
        import re

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await asyncio.wait_for(
                    page.goto("https://biletebi.ge/en/concerts", wait_until="networkidle"),
                    timeout=20.0
                )
                await asyncio.sleep(2)
                html = await page.content()
                await browser.close()

                logger.debug(f"📄 biletebi HTML: {len(html)} bytes")

                # Clean HTML and look for event patterns
                html_clean = re.sub(r'<[^>]+>', '', html)

                # Pattern: Event name followed by day name and date
                # e.g., "Concert: Guri and Giga JalaghoniaFri, 22 May, 20:00Gardenia Shevardnadze"
                # or "NAVAI Sat, 23 May, 20:00Old Sport PlaceFrom 120 ₾"

                events = []
                months_en = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12,
                }
                current_year = datetime.now().year

                # Look for patterns like "Day, DD Month, HH:MM"
                date_pattern = r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{2}):(\d{2})'

                matches = list(re.finditer(date_pattern, html_clean, re.IGNORECASE))
                logger.debug(f"Found {len(matches)} date patterns in biletebi.ge")

                seen_dates = set()
                for match in matches:
                    try:
                        day_name = match.group(1)
                        day = int(match.group(2))
                        month_str = match.group(3).lower()
                        hour = match.group(4)
                        minute = match.group(5)

                        month = months_en.get(month_str)
                        if not month or day > 31:
                            continue

                        date_obj = datetime(current_year, month, day)
                        date_str = date_obj.strftime("%Y-%m-%d")
                        time_str = f"{hour}:{minute}"

                        # Avoid duplicates
                        key = (date_str, time_str)
                        if key in seen_dates:
                            continue
                        seen_dates.add(key)

                        # Try to extract event title from context (text before the date)
                        start_idx = max(0, match.start() - 100)
                        context = html_clean[start_idx:match.start()]

                        # Clean up and get meaningful title
                        # Split by punctuation to avoid grabbing partial sentences
                        context = context.strip()
                        for sep in ['.', '\n', '•', '|']:
                            parts = context.split(sep)
                            if parts:
                                context = parts[-1].strip()

                        title = context if context and len(context) >= 3 else "Event"

                        # Remove leading numbers and common junk patterns
                        title = re.sub(r'^[\d\s]{1,20}', '', title).strip()
                        if not title or title.isdigit():
                            title = "Event"

                        # Limit title to reasonable length
                        title = title[:70]

                        events.append({
                            "title": title,
                            "date": date_str,
                            "time": time_str,
                            "location": "Tbilisi",
                            "description": "",
                            "category": _categorize_event(title, ""),
                            "source": "biletebi.ge",
                            "url": "https://biletebi.ge/en/concerts",
                            "price": "По ссылке",
                        })
                        logger.debug(f"✅ biletebi: {title[:40]} on {date_str}")

                    except (ValueError, IndexError) as e:
                        logger.debug(f"Error parsing biletebi event: {e}")
                        continue

                if events:
                    logger.info(f"✅ Found {len(events)} events from biletebi.ge")
                    return events

                logger.warning("⚠️ No events parsed from biletebi.ge")
                return None

            except asyncio.TimeoutError:
                logger.warning("⏱️ biletebi.ge timeout")
                await browser.close()
                return None
            except Exception as e:
                logger.error(f"biletebi.ge error: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    except Exception as e:
        logger.error(f"biletebi.ge browser error: {e}")
        return None


async def _scrape_eventbrite() -> Optional[List[Dict]]:
    """Scrape events from eventbrite.com (Georgia/Tbilisi section)"""
    try:
        async with async_playwright() as p:
            logger.debug("🎬 Playwright: eventbrite.com")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await asyncio.wait_for(
                    page.goto(
                        "https://www.eventbrite.com/d/georgia--tbilisi/events/",
                        wait_until="networkidle"
                    ),
                    timeout=20.0
                )
                await asyncio.sleep(2)
                html = await page.content()
                await browser.close()

                logger.debug(f"📄 eventbrite HTML: {len(html)} bytes")

                soup = BeautifulSoup(html, "html.parser")
                events = []
                seen_titles = {}  # Track titles: title -> (event_obj, has_date, has_time)

                # Eventbrite event cards
                event_items = soup.select("div.event-card, [data-event-id]")

                if not event_items:
                    logger.warning("⚠️ No event items found on eventbrite.com")
                    return None

                for item in event_items[:30]:
                    try:
                        # Title - look for aria-label or link text
                        title = None
                        link = item.select_one("a[aria-label]")
                        if link:
                            title = link.get("aria-label", "")
                            # Clean up title - remove "View " prefix if present
                            if title.startswith("View "):
                                title = title[5:]
                        else:
                            title_elem = item.select_one("a, h2, h3, h4")
                            if title_elem:
                                title = title_elem.get_text(strip=True)

                        if not title or len(title) < 3:
                            continue

                        # Date/Time extraction - look for pattern like "Today • 8:00 PM" or "May 23 • 8:00 PM"
                        date_str = None
                        time_str = None
                        event_date = None

                        # Find all paragraph elements that might contain date/time
                        date_time_paragraphs = item.select("p")
                        for para in date_time_paragraphs:
                            text = para.get_text(strip=True)
                            # Look for text containing time pattern (e.g., "8:00 PM", "20:00")
                            if ":" in text and ("AM" in text.upper() or "PM" in text.upper() or text[-2:].isdigit()):
                                # Found potential date/time paragraph
                                # Try splitting by bullet point first
                                parts = text.split("•")
                                if len(parts) >= 2:
                                    # Take the last part as time
                                    time_part = parts[-1].strip()
                                    # Take everything before time as date
                                    date_part = "•".join(parts[:-1]).strip()

                                    # Parse date part
                                    if date_part.lower() == "today":
                                        event_date = datetime.now().strftime("%Y-%m-%d")
                                    elif date_part.lower() == "tomorrow":
                                        tomorrow = datetime.now() + timedelta(days=1)
                                        event_date = tomorrow.strftime("%Y-%m-%d")
                                    else:
                                        # Try to parse actual date (e.g., "May 23")
                                        parsed = _parse_date(date_part)
                                        if parsed:
                                            event_date = parsed

                                    # Parse time part (e.g., "8:00 PM")
                                    time_str = _parse_eventbrite_time(time_part)
                                    date_str = date_part

                                    if event_date or time_str:
                                        break
                                else:
                                    # No bullet point, just check if this is a time string
                                    time_str = _parse_eventbrite_time(text)
                                    if time_str:
                                        break

                        # Location
                        location = "Tbilisi"  # Default since events are filtered by location
                        location_elem = item.select_one("[data-event-location]")
                        if location_elem:
                            location = location_elem.get("data-event-location", "Tbilisi")

                        # Description - avoid picking up date/time paragraphs
                        description = ""
                        # Find first paragraph that doesn't look like date/time
                        for p in item.select("p"):
                            text = p.get_text(strip=True)
                            # Skip if this looks like a date/time element
                            if "•" in text and ("AM" in text.upper() or "PM" in text.upper() or ":" in text):
                                continue
                            # Skip if it's just numbers/metadata
                            if len(text) > 20 and not any(char.isalpha() for char in text[:10]):
                                continue
                            if len(text) > 20:
                                description = text[:200]
                                break

                        # URL - get from link href
                        url = ""
                        link = item.select_one("a[href*='eventbrite']")
                        if link:
                            url = link.get("href", "")

                        if title:
                            category = _categorize_event(title, description)
                            new_event = {
                                "title": title,
                                "date": event_date,
                                "time": time_str,
                                "location": location,
                                "description": description,
                                "category": category,
                                "source": "eventbrite.com",
                                "url": url,
                                "price": "По ссылке",
                            }

                            # Check if we've seen this title before
                            if title in seen_titles:
                                prev_event, prev_has_date, prev_has_time = seen_titles[title]
                                # Replace if new event has better info
                                # Priority: with_date > with_time > without either
                                if event_date and not prev_has_date:
                                    # New event has date, old doesn't - replace
                                    logger.debug(f"⏭️ Replacing {title[:40]} (no date) with version with date")
                                    seen_titles[title] = (new_event, bool(event_date), bool(time_str))
                                elif time_str and prev_has_time and not event_date:
                                    # Both have time, no date - skip
                                    logger.debug(f"⏭️ Skipping duplicate: {title[:40]}")
                                    continue
                                else:
                                    logger.debug(f"⏭️ Skipping duplicate: {title[:40]}")
                                    continue
                            else:
                                seen_titles[title] = (new_event, bool(event_date), bool(time_str))

                            logger.debug(f"✅ eventbrite: {title[:40]} on {event_date} at {time_str}")

                    except Exception as e:
                        logger.debug(f"Error parsing eventbrite event: {e}")
                        continue

                # Extract just the event objects from our tracking dict
                events = [event for event, _, _ in seen_titles.values()]

                if events:
                    logger.info(f"✅ Found {len(events)} events from eventbrite.com")
                    return events

                logger.warning("⚠️ No events parsed from eventbrite.com")
                return None

            except asyncio.TimeoutError:
                logger.warning("⏱️ eventbrite.com timeout")
                await browser.close()
                return None
            except Exception as e:
                logger.error(f"eventbrite.com error: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    except Exception as e:
        logger.error(f"eventbrite.com browser error: {e}")
        return None


async def _scrape_georgia_travel() -> Optional[List[Dict]]:
    """Scrape events from georgia.travel (official tourism portal)"""
    try:
        logger.debug("🎬 Playwright: georgia.travel")
        import re

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await asyncio.wait_for(
                    page.goto("https://georgia.travel/events", wait_until="networkidle"),
                    timeout=20.0
                )
                await asyncio.sleep(2)
                html = await page.content()
                await browser.close()

                logger.debug(f"📄 georgia.travel HTML: {len(html)} bytes")

                # Clean HTML and parse events using regex
                html_clean = re.sub(r'<[^>]+>', '', html)

                events = []
                months_en = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12,
                }
                current_year = datetime.now().year

                # Pattern: DD Month or Month DD, optionally followed by time
                # e.g., "May 23", "23 May", "May 23, 20:00", etc.
                date_pattern = r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:[,\s]+(\d{4}))?(?:[,\s]*(\d{2}):(\d{2}))?'

                matches = list(re.finditer(date_pattern, html_clean, re.IGNORECASE))
                logger.debug(f"Found {len(matches)} date patterns in georgia.travel")

                seen_dates = set()
                for match in matches:
                    try:
                        day = int(match.group(1))
                        month_str = match.group(2).lower()
                        year = int(match.group(3)) if match.group(3) else current_year
                        hour = match.group(4)
                        minute = match.group(5)

                        month = months_en.get(month_str)
                        if not month or day > 31:
                            continue

                        date_obj = datetime(year, month, day)
                        date_str = date_obj.strftime("%Y-%m-%d")
                        time_str = f"{hour}:{minute}" if hour and minute else None

                        # Avoid duplicates
                        key = (date_str, time_str or "")
                        if key in seen_dates:
                            continue
                        seen_dates.add(key)

                        # Extract title from context
                        start_idx = max(0, match.start() - 100)
                        context = html_clean[start_idx:match.start()]

                        # Clean up and get meaningful title
                        context = context.strip()
                        for sep in ['.', '\n', '•', '|']:
                            parts = context.split(sep)
                            if parts:
                                context = parts[-1].strip()

                        title = context if context and len(context) >= 3 else "Event"

                        # Remove leading numbers and common junk patterns
                        title = re.sub(r'^[\d\s]{1,20}', '', title).strip()
                        if not title or title.isdigit():
                            title = "Event"

                        title = title[:70]

                        events.append({
                            "title": title,
                            "date": date_str,
                            "time": time_str,
                            "location": "Tbilisi",
                            "description": "",
                            "category": _categorize_event(title, ""),
                            "source": "georgia.travel",
                            "url": "https://georgia.travel/events",
                            "price": "По ссылке",
                        })
                        logger.debug(f"✅ georgia.travel: {title[:40]} on {date_str}")

                    except (ValueError, IndexError) as e:
                        logger.debug(f"Error parsing georgia.travel event: {e}")
                        continue

                if events:
                    logger.info(f"✅ Found {len(events)} events from georgia.travel")
                    return events

                logger.warning("⚠️ No events parsed from georgia.travel")
                return None

            except asyncio.TimeoutError:
                logger.warning("⏱️ georgia.travel timeout")
                await browser.close()
                return None
            except Exception as e:
                logger.error(f"georgia.travel error: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    except Exception as e:
        logger.error(f"georgia.travel browser error: {e}")
        return None


async def _scrape_meetup_tbilisi() -> Optional[List[Dict]]:
    """Scrape events from Meetup.com Tbilisi using Playwright for full rendering"""
    try:
        logger.debug("🎬 Playwright: meetup.com Tbilisi events...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await asyncio.wait_for(
                    page.goto("https://www.meetup.com/find/?location=Tbilisi&keywords=events",
                             wait_until="networkidle"),
                    timeout=30.0
                )

                # Wait for event items to load
                try:
                    await page.wait_for_selector("time", timeout=5000)
                except:
                    pass  # Timeout is OK, continue anyway

                await asyncio.sleep(1)
                html = await page.content()
                await browser.close()

                logger.debug(f"📄 meetup.com HTML: {len(html)} bytes")

                soup = BeautifulSoup(html, "html.parser")
                events = []

                # Find all <time> elements (these contain dates)
                time_elements = soup.select("time")
                logger.debug(f"Found {len(time_elements)} time elements")

                # Parse dates from time elements
                for time_elem in time_elements[:30]:
                    try:
                        date_text = time_elem.get_text(strip=True)
                        logger.debug(f"Time element: {date_text}")

                        # Parse format: "Fri, May 22 · 7:00 PM"
                        date_obj = _parse_meetup_date(date_text)
                        if not date_obj:
                            continue

                        date_str = date_obj["date"]
                        time_str = date_obj["time"]

                        # Find associated title for this date
                        # Search backwards from time element to find event title
                        parent = time_elem.parent
                        title = None
                        description = ""

                        # Search up the tree for title
                        for _ in range(10):  # Search up to 10 levels up
                            if parent:
                                title_elem = parent.select_one("h2, h3, a[href*='/events/']")
                                if title_elem:
                                    title = title_elem.get_text(strip=True)
                                    break
                                parent = parent.parent
                            else:
                                break

                        if not title or len(title) < 3:
                            continue

                        # Get URL
                        url_elem = parent.select_one("a[href*='/events/']") if parent else None
                        url = url_elem.get("href", "") if url_elem else ""
                        if url and not url.startswith("http"):
                            url = "https://www.meetup.com" + url

                        category = _categorize_event(title, "")

                        events.append({
                            "title": title[:100],
                            "date": date_str,
                            "time": time_str,
                            "location": "Tbilisi",
                            "description": "Встреча на Meetup.com",
                            "category": category,
                            "source": "meetup.com",
                            "url": url,
                            "price": "Зависит от события",
                        })
                        logger.debug(f"✅ meetup: {title[:40]} on {date_str} at {time_str}")

                    except Exception as e:
                        logger.debug(f"Error parsing meetup time element: {e}")
                        continue

                if events:
                    logger.info(f"✅ Found {len(events)} events from meetup.com")
                    return events

                logger.warning("⚠️ No events parsed from meetup.com")
                return None

            except asyncio.TimeoutError:
                logger.warning("⏱️ meetup.com timeout")
                await browser.close()
                return None
            except Exception as e:
                logger.error(f"meetup.com parse error: {e}")
                try:
                    await browser.close()
                except:
                    pass
                return None

    except Exception as e:
        logger.error(f"meetup.com browser error: {e}")
        return None


def _parse_meetup_date(date_text: str) -> Optional[Dict]:
    """Parse Meetup.com date format: 'Fri, May 22 · 7:00 PM'"""
    import re

    try:
        # Format: "Fri, May 22 · 7:00 PM"
        # Extract: month day and time
        pattern = r'(\w+),\s+(\w+)\s+(\d{1,2})\s+·\s+(\d{1,2}):(\d{2})\s+(AM|PM)'
        match = re.search(pattern, date_text)

        if not match:
            return None

        month_str = match.group(2).lower()
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = match.group(5)
        am_pm = match.group(6)

        # Convert to 24-hour format
        if am_pm == "PM" and hour != 12:
            hour += 12
        elif am_pm == "AM" and hour == 12:
            hour = 0

        # Map month name to number
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12,
        }

        month = months.get(month_str)
        if not month:
            return None

        # Create date
        try:
            date_obj = datetime(datetime.now().year, month, day)
            # If date is in the past, assume next year
            if date_obj < datetime.now():
                date_obj = datetime(datetime.now().year + 1, month, day)

            date_str = date_obj.strftime("%Y-%m-%d")
            time_str = f"{hour:02d}:{minute}"

            return {
                "date": date_str,
                "time": time_str,
            }
        except ValueError:
            return None

    except Exception as e:
        logger.debug(f"Error parsing meetup date '{date_text}': {e}")
        return None


def _parse_eventbrite_time(time_text: str) -> Optional[str]:
    """Parse Eventbrite time format: '8:00 PM' -> '20:00'"""
    import re

    try:
        # Pattern: "8:00 PM" or "8:00 AM"
        pattern = r'(\d{1,2}):(\d{2})\s+(AM|PM)'
        match = re.search(pattern, time_text)

        if not match:
            return None

        hour = int(match.group(1))
        minute = match.group(2)
        am_pm = match.group(3)

        # Convert to 24-hour format
        if am_pm == "PM" and hour != 12:
            hour += 12
        elif am_pm == "AM" and hour == 12:
            hour = 0

        return f"{hour:02d}:{minute}"

    except Exception as e:
        logger.debug(f"Error parsing eventbrite time '{time_text}': {e}")
        return None


async def _scrape_cinemaqa() -> Optional[List[Dict]]:
    """Scrape cinema showtimes from cinemaqa.ge"""
    try:
        logger.debug("🎬 Fetching cinemaqa.ge (Georgian cinemas)...")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://cinemaqa.ge",
                follow_redirects=True
            )
            response.raise_for_status()

        logger.debug(f"📄 cinemaqa HTML: {len(response.text)} bytes")

        soup = BeautifulSoup(response.text, "html.parser")
        events = []

        # Cinema showtimes - look for movie cards
        movie_items = soup.select(
            "[class*='movie'], [class*='film'], .cinema-item, [data-movie], article"
        )

        if not movie_items:
            logger.warning("⚠️ No cinema events found")
            return None

        for item in movie_items[:15]:
            try:
                # Movie title
                title_elem = item.select_one("h2, h3, .title, .movie-title, a")
                title = title_elem.get_text(strip=True) if title_elem else None
                if not title or len(title) < 2:
                    continue

                # Cinema location
                location_elem = item.select_one("[class*='location'], .cinema, .place")
                location = location_elem.get_text(strip=True) if location_elem else "Tbilisi"

                # Showtime if available
                time_elem = item.select_one("[class*='time'], .showtime, time")
                time_str = time_elem.get_text(strip=True) if time_elem else None

                # Description (movie genre/synopsis)
                desc_elem = item.select_one("p, [class*='description'], .synopsis")
                description = desc_elem.get_text(strip=True)[:200] if desc_elem else "Киносеанс"

                # Link
                link = item.select_one("a[href]")
                url = link.get("href", "") if link else ""
                if url and not url.startswith("http"):
                    url = "https://cinemaqa.ge" + url

                events.append({
                    "title": title[:80],
                    "date": None,  # Cinema sites require JS for dates
                    "time": time_str,
                    "location": location,
                    "description": description,
                    "category": "exhibition",  # Movies as exhibitions
                    "source": "cinemaqa.ge",
                    "url": url,
                    "price": "7-12 GEL",
                })
                logger.debug(f"✅ cinema: {title[:40]}")

            except Exception as e:
                logger.debug(f"Error parsing cinema event: {e}")
                continue

        if events:
            logger.info(f"✅ Found {len(events)} cinema showtimes from cinemaqa.ge")
            return events

        logger.warning("⚠️ No cinema events parsed")
        return None

    except Exception as e:
        logger.error(f"cinemaqa.ge error: {e}")
        return None


async def _scrape_tkt_ge() -> Optional[List[Dict]]:
    """Scrape events from tkt.ge API"""
    try:
        import json

        # API endpoint discovered through network inspection
        # Using Categories API which returns all available events/shows
        api_url = "https://gateway.tkt.ge/Categories"

        async with httpx.AsyncClient(timeout=15.0) as client:
            logger.debug("📡 Fetching events from tkt.ge API...")
            response = await client.get(api_url)
            response.raise_for_status()

        data = response.json()
        logger.debug(f"✅ API response: {len(response.text)} bytes")

        events = []

        # API returns categories with events
        if isinstance(data, dict):
            # Try to find categories
            categories = data.get('categories', []) or data.get('data', [])

            if isinstance(categories, list):
                logger.debug(f"Found {len(categories)} categories")

                for category in categories:
                    if not isinstance(category, dict):
                        continue

                    category_name = category.get('name', '')
                    items = category.get('items', []) or category.get('shows', []) or category.get('events', [])

                    if isinstance(items, list):
                        logger.debug(f"  Category '{category_name}': {len(items)} items")

                        for item in items:
                            if not isinstance(item, dict):
                                continue

                            title = item.get('name') or item.get('title') or item.get('eventName')
                            date_str = item.get('date') or item.get('eventDate') or item.get('startDate')
                            location = item.get('location') or item.get('venue') or "Tbilisi"
                            url = item.get('url') or item.get('link') or ""
                            description = item.get('description') or category_name

                            if title:
                                # Parse date if available
                                parsed_date = _parse_date(date_str) if date_str else None

                                events.append({
                                    "title": title,
                                    "date": parsed_date,
                                    "time": item.get('time') or item.get('startTime'),
                                    "location": location,
                                    "description": str(description)[:200],
                                    "category": _categorize_event(title, description),
                                    "source": "tkt.ge",
                                    "url": str(url) if url else "",
                                })

        if events:
            logger.info(f"✅ Extracted {len(events)} events from tkt.ge API")
            return events

        logger.warning("No events found in tkt.ge API response")
        return None

    except httpx.HTTPError as e:
        logger.error(f"tkt.ge API error: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"tkt.ge: JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"tkt.ge: Unexpected error: {e}")
        return None


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
    """Remove duplicate events based on title, location, date, and time"""

    seen = set()
    unique = []

    for event in events:
        # Create key: (title, location, date, time)
        # Events with same name/location but different times are different events
        key = (
            event.get("title", "").lower().strip(),
            event.get("location", "").lower().strip(),
            event.get("date", ""),
            event.get("time", ""),  # Include time to distinguish same-day events
        )
        if key not in seen:
            seen.add(key)
            unique.append(event)
        else:
            logger.debug(f"⏭️  Skipped duplicate: {event.get('title', 'Unknown')[:40]} "
                        f"on {event.get('date')} at {event.get('time', 'N/A')}")

    return unique


async def _generate_event_description(event: Dict) -> str:
    """Generate event description using ChatGPT (280 chars)"""
    from openai import AsyncOpenAI
    from src.utils.doppler import get_secret

    try:
        api_key = await get_secret("OPENAI_API_KEY")
        client = AsyncOpenAI(api_key=api_key)

        title = event.get("title", "Event")
        category = event.get("category", "other")
        location = event.get("location", "Tbilisi")
        existing_desc = event.get("description", "")

        prompt = f"""Write a brief, engaging description (exactly 280 characters) for this event in Russian:

Event: {title}
Category: {category}
Location: {location}
Details: {existing_desc}

Description should be interesting, informative, and enticing. Write ONLY the description, nothing else."""

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )

        description = response.choices[0].message.content.strip()
        # Truncate to 280 chars without ellipsis
        if len(description) > 280:
            description = description[:280]
        return description

    except Exception as e:
        logger.warning(f"Failed to generate description for {event.get('title', 'Unknown')}: {e}")
        return event.get("description", "")[:280]


def format_events_for_telegram(events: List[Dict]) -> str:
    """Format events list for Telegram message with new format:

    Название события • Дата, Время, Место

    Описание на 280 символов

    Цена билета: цена. Ссылка: ссылка
    """

    if not events:
        return "На следующую неделю в Тбилиси пока ничего не найдено 🤔"

    today = datetime.now().date()
    lines = ["📅 *События в Тбилиси на следующую неделю:*\n"]

    for i, event in enumerate(events, 1):
        event_date = event.get("date")

        # Skip past events
        if event_date:
            try:
                event_dt = datetime.strptime(event_date, "%Y-%m-%d").date()
                if event_dt < today:
                    continue
            except ValueError:
                continue

        # Build event details line: Title • Date, Time, Location
        title = event.get("title", "Unknown Event")
        date_str = event.get("date", "N/A")
        time_str = event.get("time", "N/A")
        location = event.get("location", "Tbilisi")

        details_line = f"{title} • {date_str}, {time_str}, {location}"
        lines.append(f"*{i}. {details_line}*")

        # Description (280 chars)
        description = event.get("description", "")[:280]
        if description:
            lines.append(f"\n{description}")

        # Price and link
        price = event.get("price")
        url = event.get("url", "")

        footer_parts = []
        if price and price not in ["", "N/A", "По ссылке"]:
            footer_parts.append(f"Цена: {price}")
        if url:
            footer_parts.append(f"[Ссылка]({url})")

        if footer_parts:
            footer = ". ".join(footer_parts)
            lines.append(f"\n{footer}\n")
        elif url:
            lines.append(f"\n[Ссылка]({url})\n")
        else:
            lines.append("")

    return "\n".join(lines)


def _get_day_name_ru(date: datetime.date) -> str:
    """Get Russian day name for date"""
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    return days[date.weekday()]
