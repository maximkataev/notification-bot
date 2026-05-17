#!/usr/bin/env python3
"""Inspect biletebi.ge HTML structure."""

import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 INSPECTING BILETEBI.GE STRUCTURE")
    print("="*100 + "\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Loading https://biletebi.ge/en/concerts...")
        await page.goto("https://biletebi.ge/en/concerts", wait_until="networkidle")
        await asyncio.sleep(2)

        html = await page.content()
        print(f"✅ HTML loaded: {len(html)} bytes\n")
        await browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Find all divs with classes
        print("🔎 Looking for event-like elements:\n")

        # Check for common class patterns
        patterns = [
            "event", "concert", "card", "item", "ticket", "show", "performance"
        ]

        for pattern in patterns:
            elements = soup.find_all(class_=lambda x: x and pattern in x.lower())
            if elements:
                print(f"✅ Found {len(elements)} elements with '{pattern}' in class")
                for elem in elements[:3]:
                    print(f"   Tag: {elem.name}, Classes: {elem.get('class', [])}")
                    text = elem.get_text(strip=True)[:80]
                    print(f"   Text: {text}\n")

        # Look for any articles or structured content
        print("\n🔍 Checking for <article> tags:")
        articles = soup.find_all("article")
        print(f"   Found {len(articles)} articles")
        if articles:
            for i, art in enumerate(articles[:2], 1):
                print(f"   Article {i} classes: {art.get('class', [])}")
                print(f"   Text: {art.get_text(strip=True)[:100]}\n")

        # Look for links to events
        print("🔍 Finding event links:")
        links = soup.find_all("a", href=lambda x: x and ("/en/" in x or "/ru/" in x))
        print(f"   Found {len(links)} links\n")

        event_links = [l for l in links if any(x in l.get_text().lower() for x in ["concert", "event", "ticket"])]
        print(f"   Event-like links: {len(event_links)}")
        for link in event_links[:5]:
            print(f"   - {link.get_text(strip=True)[:60]} → {link.get('href', '')}\n")

        # Dump full HTML snippet for manual inspection
        print("\n" + "="*100)
        print("📄 FIRST 3000 CHARS OF HTML (after tag removal):")
        print("="*100 + "\n")

        import re
        html_clean = re.sub(r'<[^>]+>', '', html)
        print(html_clean[:3000])


if __name__ == "__main__":
    asyncio.run(main())
