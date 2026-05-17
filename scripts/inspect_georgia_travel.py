#!/usr/bin/env python3
"""Inspect georgia.travel HTML structure."""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 INSPECTING GEORGIA.TRAVEL STRUCTURE")
    print("="*100 + "\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Loading https://georgia.travel/events...")
        await page.goto("https://georgia.travel/events", wait_until="networkidle")
        await asyncio.sleep(2)

        html = await page.content()
        print(f"✅ HTML loaded: {len(html)} bytes\n")
        await browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Find all elements with common patterns
        print("🔎 Looking for event-like elements:\n")

        # Check for common class patterns
        patterns = [
            "event", "card", "item", "post", "listing", "article", "tile"
        ]

        for pattern in patterns:
            elements = soup.find_all(class_=lambda x: x and pattern in x.lower())
            if elements:
                print(f"✅ Found {len(elements)} elements with '{pattern}' in class")
                for elem in elements[:2]:
                    print(f"   Tag: {elem.name}, Classes: {elem.get('class', [])}")
                    text = elem.get_text(strip=True)[:80]
                    print(f"   Text: {text}\n")

        # Look for div structure
        print("🔍 Checking main content structure:")
        main_content = soup.find("main") or soup.find("div", class_=lambda x: x and "main" in (x or "").lower())
        if main_content:
            direct_divs = main_content.find_all("div", recursive=False)[:5]
            print(f"   Main content direct children: {len(direct_divs)}")
            for div in direct_divs:
                print(f"   - Classes: {div.get('class', [])}")

        # Look for all divs with data attributes
        print("\n🔍 Divs with data attributes:")
        data_divs = soup.find_all(True, attrs=lambda x: x and any(k.startswith('data-') for k in x.keys()))
        print(f"   Found {len(data_divs)}")
        for div in data_divs[:3]:
            data_attrs = {k: v for k, v in div.attrs.items() if k.startswith('data-')}
            print(f"   Tag: {div.name}, Data: {data_attrs}")

        # Look for links to events
        print("\n🔍 Finding event-like links:")
        links = soup.find_all("a", href=lambda x: x and ("/event" in x.lower() or "/events" in x.lower()))
        print(f"   Found {len(links)} event links")
        for link in links[:5]:
            print(f"   - {link.get_text(strip=True)[:60]}")

        # Dump HTML snippet
        print("\n" + "="*100)
        print("📄 FIRST 2000 CHARS OF HTML:")
        print("="*100 + "\n")
        print(html[:2000])

        print("\n" + "="*100)
        print("📄 HTML AROUND 'event' KEYWORD (if found):")
        print("="*100 + "\n")
        event_idx = html.lower().find("event")
        if event_idx > 0:
            start = max(0, event_idx - 300)
            end = min(len(html), event_idx + 500)
            print(html[start:end])


if __name__ == "__main__":
    asyncio.run(main())
