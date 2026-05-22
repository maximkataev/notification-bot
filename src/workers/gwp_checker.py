"""Check GWP (Georgian Water and Power) website for scheduled/unscheduled works."""

import logging
import httpx
import re
from typing import Optional, List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Streets we care about (various spellings and languages)
WATCH_STREETS = [
    "vazha iverievi",  # English transliteration
    "ვაზა ივერიელი",  # Georgian
    "ვაჟა ივერელის ქუჩა",  # Georgian with "street" suffix
    "ვაჟა ივერელი",  # Georgian alternative spelling
    "vazha iverelis",  # Alternative transliteration
]


async def check_gwp_works() -> Optional[List[str]]:
    """Check GWP website for works on Vazha Iverievi street using Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            works_found = []

            # Check both scheduled and unscheduled works
            urls = [
                ("https://www.gwp.ge/en/news/scheduled-works/", "Scheduled"),
                ("https://www.gwp.ge/en/news/nonscheduled-works/", "Unscheduled"),
            ]

            for url, work_type in urls:
                logger.info(f"Checking {url}")
                try:
                    await page.goto(url, wait_until="load", timeout=10000)
                    await page.wait_for_timeout(500)

                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")

                    # GWP uses region-card class for work items
                    articles = soup.find_all("div", class_="region-card")
                    logger.debug(f"Found {len(articles)} articles on {url}")

                    for article in articles:
                        # Get full text including all nested elements
                        article_text = article.get_text(separator=" ", strip=True)
                        article_text_lower = article_text.lower()

                        # Check if any watched street is mentioned
                        street_found = None
                        for street in WATCH_STREETS:
                            street_lower = street.lower()
                            if street_lower in article_text_lower:
                                street_found = street
                                break

                        if street_found:
                            # Extract title - look for headings or first substantial text
                            title = None
                            for heading_tag in ["h2", "h3", "h4", "h5"]:
                                heading = article.find(heading_tag)
                                if heading:
                                    title = heading.get_text(strip=True)
                                    break

                            if not title:
                                # Use first 100 chars as title
                                title = article_text[:100].strip()

                            if title:
                                works_found.append(f"{work_type} work: {title}")
                                logger.info(
                                    f"Found work on Vazha Iverievi ({street_found}): {title}"
                                )

                except Exception as e:
                    logger.debug(f"Error checking {url}: {e}")
                    continue

            await browser.close()

            if works_found:
                logger.info(f"✓ Found {len(works_found)} works on Vazha Iverievi")
                return works_found
            else:
                logger.info("No works found on Vazha Iverievi")
                return None

    except Exception as e:
        logger.warning(f"⚠️  Failed to check GWP: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None


async def check_water_cuts() -> Optional[str]:
    """
    Scrape GWP website for water cuts on Vazha Ivereli street.
    Extract full article text, send to ChatGPT for summarization.

    Returns:
        "Сегодня с 14:00 до 15:00 ожидается отключение воды на Vazha Ivereli street."
        or None if no water cuts found on that street
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            urls = [
                "https://www.gwp.ge/en/news/scheduled-works/",
                "https://www.gwp.ge/en/news/nonscheduled-works/",
            ]

            for url in urls:
                logger.info(f"Checking {url} for water cuts")
                try:
                    response = await client.get(
                        url, follow_redirects=True, timeout=10.0
                    )

                    # Skip 4xx errors (not found, etc) without retry
                    if 400 <= response.status_code < 500:
                        logger.debug(f"{url}: {response.status_code} Not Found")
                        continue

                    response.raise_for_status()
                except Exception as e:
                    logger.debug(f"Error fetching {url}: {e}")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")

                # Find all text content, look for mentions of Vazha Ivereli
                page_text = soup.get_text(separator=" ", strip=True)
                page_text_lower = page_text.lower()

                # Check if any street variation is mentioned
                found_street = False
                for street in WATCH_STREETS:
                    if street.lower() in page_text_lower:
                        found_street = True
                        logger.info(f"Found mention of {street} on {url}")
                        break

                if found_street:
                    # Extract more detailed text - look for all divs/articles
                    all_divs = soup.find_all("div")
                    for div in all_divs:
                        div_text = div.get_text(separator=" ", strip=True)
                        div_text_lower = div_text.lower()

                        # Check if this div contains Vazha Ivereli info
                        for street in WATCH_STREETS:
                            if street.lower() in div_text_lower and len(div_text) > 50:
                                logger.info(f"Found detailed info for {street}")
                                # Send to ChatGPT for summarization
                                summary = await _summarize_water_cut_with_gpt(div_text)
                                if summary:
                                    return summary
                                break

    except Exception as e:
        logger.warning(f"Failed to check water cuts: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)

    return None


async def check_water_cuts_today() -> Optional[str]:
    """
    Parse GWP website for water cuts on Vazha Iverievi TODAY using Playwright.
    Extracts time range and street name without GPT (token saving).

    Returns:
        "2026-05-10 ожидается отключение воды с 02:00 по 12:00 на улице ვაზა ივერიელი (Vazha Iverievi)"
        or None if no water cuts found on Vazha Iverievi
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            urls = [
                "https://www.gwp.ge/en/news/scheduled-works/",
                "https://www.gwp.ge/en/news/nonscheduled-works/",
            ]

            for url in urls:
                logger.info(
                    f"Checking {url} for Vazha Iverievi water cuts (with Playwright)"
                )
                try:
                    await page.goto(url, wait_until="load", timeout=10000)
                    await page.wait_for_timeout(500)

                    page_text = await page.content()
                    soup = BeautifulSoup(page_text, "html.parser")
                    page_body = soup.get_text(separator=" ", strip=True)
                    page_body_lower = page_body.lower()

                    # Check if Vazha Iverievi is mentioned
                    found_street = None
                    for street in WATCH_STREETS:
                        if street.lower() in page_body_lower:
                            found_street = street
                            logger.info(f"Found mention of {street} on {url}")
                            break

                    if found_street:
                        # Extract time range for this street
                        result = _extract_water_cut_time(page_body, found_street)
                        if result:
                            await browser.close()
                            return result

                except Exception as e:
                    logger.debug(f"Error checking {url}: {e}")
                    continue

            await browser.close()

    except Exception as e:
        logger.warning(f"Failed to check water cuts: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)

    return None


def _extract_water_cut_time(article_text: str, street: str) -> Optional[str]:
    """
    Extract water cut time range from page text for specific street.
    Look for date/time patterns like "5/10/2026 02:00 დან 5/10/2026 12:00".

    Returns:
        "2026-05-10 ожидается отключение воды с 02:00 по 12:00 на улице ვაზა ივერიელი (Vazha Iverievi)"
        or None if time cannot be extracted
    """
    try:
        # Look for date and time pattern: M/D/YYYY HH:MM ... HH:MM
        date_time_pattern = (
            r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}).*?(\d{1,2}):(\d{2})"
        )
        match = re.search(date_time_pattern, article_text)

        if not match:
            logger.debug(f"Could not extract date/time range from page")
            return None

        month, day, year, start_hour, start_min, end_hour, end_min = match.groups()

        # Format as YYYY-MM-DD
        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        start_time = f"{start_hour.zfill(2)}:{start_min}"
        end_time = f"{end_hour.zfill(2)}:{end_min}"

        # Format street with Georgian and English names
        # Handle different input formats
        if (
            "ვაზა" in street
            or "ვაჟა" in street
            or "ivereeli" in street.lower()
            or "iverievi" in street.lower()
        ):
            street_text = "ვაზა ივერიელი (Vazha Iverievi)"
        else:
            street_text = street

        message = f"{date_str} ожидается отключение воды с {start_time} по {end_time} на улице {street_text}"

        logger.info(f"Extracted water cut: {message}")
        return message

    except Exception as e:
        logger.warning(f"Failed to extract water cut time: {type(e).__name__}: {e}")
        return None
