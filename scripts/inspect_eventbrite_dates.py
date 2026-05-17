#!/usr/bin/env python3
"""Inspect Eventbrite.com structure to find date selectors."""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 INSPECTING EVENTBRITE.COM DATE STRUCTURE")
    print("="*100 + "\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("📡 Loading eventbrite.com Tbilisi events...")
        await page.goto("https://www.eventbrite.com/d/georgia--tbilisi/events/",
                       wait_until="networkidle", timeout=30000)

        print("✅ Page loaded\n")

        # Wait for event items to load
        await page.wait_for_selector("[data-event-id], .event-card, article", timeout=10000)
        await asyncio.sleep(2)

        html = await page.content()
        print(f"📄 HTML size: {len(html)} bytes\n")
        await browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Look for date selectors
        print("🔎 SEARCHING FOR DATE PATTERNS:\n")

        # Try different date selectors
        date_selectors = [
            "time",
            "[class*='date']",
            "[class*='time']",
            "[class*='Date']",
            "[class*='Time']",
            "[data-date]",
            "[aria-label*='date']",
            "[aria-label*='time']",
            ".eventTime",
            ".eventDate",
            ".event-date",
            ".event-time",
            "[class*='DateTime']",
            "[class*='startDate']",
            "span[role='heading']",
            ".secondary-text",
        ]

        for selector in date_selectors:
            elements = soup.select(selector)
            if elements:
                print(f"✅ Found with '{selector}': {len(elements)} elements")
                for elem in elements[:2]:
                    text = elem.get_text(strip=True)[:100]
                    print(f"   - {text}")
                print()

        # Look for event cards with all their content
        print("\n🔎 EVENT CARD STRUCTURE:\n")

        event_cards = soup.select("[data-event-id], .event-card, article, [class*='EventCard']")
        print(f"Event cards found: {len(event_cards)}\n")

        if event_cards:
            card = event_cards[0]
            print("First event card content:\n")

            # Get full HTML of card
            card_html = str(card)[:1500]
            print(card_html)
            print("\n" + "="*100)

            # Check what text elements are inside
            print("\nText elements in first card:")
            for text_elem in card.find_all(['div', 'span', 'p']):
                text = text_elem.get_text(strip=True)
                if text and len(text) > 5 and len(text) < 100:
                    classes = ' '.join(text_elem.get('class', []))
                    role = text_elem.get('role', '')
                    print(f"  <{text_elem.name} class='{classes}' role='{role}'> {text[:60]}")

        print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
