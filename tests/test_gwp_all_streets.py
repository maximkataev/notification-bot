#!/usr/bin/env python3
"""Test GWP parser - show ALL water cuts, not just Vazha Iverievi."""
import asyncio
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_all_water_cuts():
    """Get ALL water cuts from GWP website (not just Vazha Iverievi)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        urls = [
            ("https://www.gwp.ge/en/news/scheduled-works/", "📅 Scheduled Works"),
            ("https://www.gwp.ge/en/news/nonscheduled-works/", "🚨 Unscheduled Works"),
        ]

        for url, title in urls:
            print(f"\n{'='*70}")
            print(f"{title}")
            print(f"{'='*70}\n")

            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(2000)

                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                # Find all region cards (water cut notifications)
                cards = soup.find_all("div", class_="region-card")

                if not cards:
                    print("❌ No water cuts found\n")
                    continue

                print(f"✓ Found {len(cards)} water cut(s):\n")

                for i, card in enumerate(cards, 1):
                    text = card.get_text(separator=" ", strip=True)

                    # Extract key info
                    lines = text.split()

                    # Format output
                    print(f"{i}. {text[:150]}...")
                    print()

            except Exception as e:
                logger.error(f"Error: {e}")
                import traceback

                traceback.print_exc()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(get_all_water_cuts())
