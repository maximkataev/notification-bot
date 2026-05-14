"""Fetch betting odds from pari.ru for football matches."""

import logging
from typing import Optional, Dict, Tuple
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def get_pari_odds(home_team: str, away_team: str) -> Optional[Tuple[float, float, float]]:
    """
    Fetch 1X2 odds from pari.ru for a specific match.
    Returns (home_odds, draw_odds, away_odds) or None if not found.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Set timeout and load page
                await page.goto("https://pari.ru/", timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=10000)

                content = await page.content()

                # Parse with BeautifulSoup
                soup = BeautifulSoup(content, "html.parser")

                # Try multiple selector strategies
                odds = _extract_odds_from_html(soup, home_team, away_team)

                if odds:
                    logger.info(f"✓ Found odds for {home_team} vs {away_team}: {odds}")
                    return odds

                logger.debug(f"Could not find odds for {home_team} vs {away_team} on pari.ru")
                return None

            finally:
                await browser.close()

    except Exception as e:
        logger.warning(f"Failed to fetch pari.ru odds: {type(e).__name__}: {e}")
        return None


def _extract_odds_from_html(
    soup: BeautifulSoup, home_team: str, away_team: str
) -> Optional[Tuple[float, float, float]]:
    """
    Extract odds from parsed HTML.
    Looks for match rows containing team names and their 1X2 coefficients.
    """

    # Normalize team names for matching
    home_normalized = home_team.lower().strip()
    away_normalized = away_team.lower().strip()

    # Strategy 1: Look for divs/rows that contain both team names
    containers = soup.find_all(["div", "tr", "li"])

    for container in containers:
        text = container.get_text().lower()

        # Check if both teams are in this container
        if home_normalized in text and away_normalized in text:
            # Look for coefficient-like patterns in this container
            # Coefficients are typically: 1.xx to 9.xx
            odds = _extract_coefficients_from_text(container)

            if odds and len(odds) >= 3:
                try:
                    # Return first 3 odds (1X2)
                    return (float(odds[0]), float(odds[1]), float(odds[2]))
                except (ValueError, IndexError):
                    continue

    # Strategy 2: Look for obvious match rows and extract structure
    # pari.ru often uses structured layouts, look for clickable match elements
    match_divs = soup.find_all("div", class_=lambda x: x and "event" in x.lower())

    for match_div in match_divs:
        text = match_div.get_text().lower()

        if home_normalized in text and away_normalized in text:
            odds = _extract_coefficients_from_text(match_div)

            if odds and len(odds) >= 3:
                try:
                    return (float(odds[0]), float(odds[1]), float(odds[2]))
                except (ValueError, IndexError):
                    continue

    return None


def _extract_coefficients_from_text(element) -> list:
    """
    Extract coefficient numbers from element text.
    Looks for patterns like "1.25 3.00 7.01"
    """
    import re

    text = element.get_text()

    # Find all number patterns that look like odds (1.xx to 99.xx)
    pattern = r"\b([1-9]\d{0,2}\.\d{2,4})\b"
    matches = re.findall(pattern, text)

    if matches:
        return matches

    return []
