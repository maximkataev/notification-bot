#!/usr/bin/env python3
"""Inspect Meetup.com structure to find date selectors."""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 INSPECTING MEETUP.COM DATE STRUCTURE")
    print("="*100 + "\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("📡 Loading meetup.com Tbilisi events...")
        await page.goto("https://www.meetup.com/find/?location=Tbilisi&keywords=events",
                       wait_until="networkidle", timeout=30000)

        print("✅ Page loaded\n")

        # Wait for event items to load
        await page.wait_for_selector("[class*='event']", timeout=10000)
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
            "[data-date]",
            "[aria-label*='date']",
            "[aria-label*='time']",
            ".eventTime",
            ".eventDate",
            ".event-date",
            ".event-time",
            "[class*='DateTime']",
            "[class*='startDate']",
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

        event_cards = soup.select("[class*='EventCard'], [class*='eventCard'], [data-eventid]")
        print(f"Event cards found: {len(event_cards)}\n")

        if event_cards:
            card = event_cards[0]
            print("First event card structure:")

            # Check what's inside
            title = card.select_one("h2, h3, [class*='title'], a")
            print(f"Title: {title.get_text(strip=True)[:60] if title else 'NOT FOUND'}")

            # Look for date/time info
            for child in card.find_all(True):
                text = child.get_text(strip=True)
                if any(word in text.lower() for word in ['may', 'june', 'pm', 'am', ':', 'am', 'date', 'time', 'sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']):
                    tag = child.name
                    classes = ' '.join(child.get('class', []))
                    print(f"\n<{tag} class='{classes}'>")
                    print(f"   Text: {text[:80]}")

        # Full card HTML sample
        print("\n\n📄 FULL FIRST CARD HTML:\n")
        if event_cards:
            print(str(event_cards[0])[:1000])

        print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
