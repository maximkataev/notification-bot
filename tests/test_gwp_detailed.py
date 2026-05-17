#!/usr/bin/env python3
"""Detailed GWP parser test with Playwright for JavaScript rendering."""
import asyncio
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_gwp_with_playwright():
    """Test GWP website with Playwright to render JavaScript."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        urls = [
            "https://www.gwp.ge/en/news/scheduled-works/",
            "https://www.gwp.ge/en/news/nonscheduled-works/",
        ]

        for url in urls:
            print(f"\n{'='*60}")
            print(f"🔍 Checking: {url}")
            print(f"{'='*60}\n")

            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(2000)

                # Get full page content
                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                # Try to find all possible containers
                print("Searching for containers...\n")

                selectors = [
                    ("div.item-news", "div.item-news"),
                    ("article", "article"),
                    ("div.news-item", "div.news-item"),
                    ("div.news", "div.news"),
                    ("li.news", "li.news"),
                    ("div.content", "div.content"),
                    ("div.main-content", "div.main-content"),
                    ("div.page-content", "div.page-content"),
                ]

                for name, selector in selectors:
                    if ".news" in selector:
                        elements = soup.select(selector)
                        if elements:
                            print(
                                f"✓ Found {len(elements)} element(s) matching '{name}'"
                            )
                            for i, elem in enumerate(elements[:3], 1):
                                text = elem.get_text(separator=" ", strip=True)
                                print(f"  {i}. {text[:150]}...")
                            print()

                # Also try to find all text that might be about water cuts
                page_text = soup.get_text(separator=" ", strip=True)

                # Look for keywords
                keywords = [
                    "water",
                    "cut",
                    "scheduled",
                    "street",
                    "отключение",
                    "вода",
                    "улица",
                ]
                found_keywords = [
                    kw for kw in keywords if kw.lower() in page_text.lower()
                ]

                print(f"Keywords found on page: {found_keywords}\n")

                # Get full page length
                print(f"Page text length: {len(page_text)} characters")
                print(f"First 1000 characters:\n{page_text[:1000]}\n")

                # Try to find all div/section elements with classes
                all_divs = soup.find_all("div", limit=30)
                print(f"First 30 divs with their classes:")
                for i, div in enumerate(all_divs, 1):
                    classes = div.get("class", [])
                    div_id = div.get("id", "")
                    text = div.get_text(separator=" ", strip=True)[:100]
                    if classes or div_id:
                        print(f"  {i}. classes={classes}, id={div_id}")
                        if text:
                            print(f"     Text: {text}...")

            except Exception as e:
                logger.error(f"Error: {e}")
                import traceback

                traceback.print_exc()
            finally:
                print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_gwp_with_playwright())
