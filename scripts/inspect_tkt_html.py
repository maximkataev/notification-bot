#!/usr/bin/env python3
"""Inspect tkt.ge HTML structure with Playwright."""

import asyncio
import sys
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 INSPECTING TKT.GE HTML STRUCTURE")
    print("="*100 + "\n")

    async with async_playwright() as p:
        print("🎬 Launching Playwright...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("📡 Loading https://tkt.ge/en/events...")
        await page.goto("https://tkt.ge/en/events", wait_until="networkidle")

        html = await page.content()
        print(f"✅ HTML loaded: {len(html)} bytes\n")

        soup = BeautifulSoup(html, "html.parser")

        # Look for all div and a tags with content
        print("🔎 SEARCHING FOR ELEMENTS:\n")

        # Search for divs with data attributes
        data_divs = soup.find_all("div", attrs={"data-": True})
        print(f"1. Divs with data-* attributes: {len(data_divs)}")

        # Search for all divs
        all_divs = soup.find_all("div", limit=20)
        print(f"2. First 20 divs:\n")
        for i, div in enumerate(all_divs[:10], 1):
            classes = div.get('class', [])
            data_attrs = {k: v for k, v in div.attrs.items() if k.startswith('data-')}
            if classes or data_attrs:
                print(f"   {i}. Classes: {classes}, Data: {data_attrs}")

        # Look for specific selectors
        print("\n3. Testing selectors:\n")
        selectors = [
            "[class*='card']",
            "[class*='event']",
            "[class*='item']",
            ".event",
            ".card",
            ".product",
            ".show",
            "a[href*='event']",
            "a[href*='show']",
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"   ✅ Selector '{selector}': {len(elements)} elements")
                # Show first element
                if elements[0].name in ['a', 'div', 'article']:
                    text = elements[0].get_text(strip=True)[:60]
                    print(f"      First: {text}")
            else:
                print(f"   ⏭️  Selector '{selector}': 0 elements")

        # Look for links to events
        print("\n4. Looking for event links:\n")
        all_links = soup.find_all("a", href=True)
        event_links = [
            l for l in all_links
            if any(x in l.get('href', '').lower() for x in ['event', 'show', 'ticket', 'buy'])
        ]
        print(f"   Total links: {len(all_links)}")
        print(f"   Event-related links: {len(event_links)}")

        if event_links:
            print(f"   First 5 event links:")
            for link in event_links[:5]:
                href = link.get('href', '')
                text = link.get_text(strip=True)[:50]
                print(f"      - {text} → {href}")

        # Look for JSON data in page
        print("\n5. Looking for JSON data:\n")
        scripts = soup.find_all("script")
        print(f"   Found {len(scripts)} script tags")

        for script in scripts:
            content = script.string
            if content and ("event" in content.lower() or "data" in content.lower()):
                if len(content) < 500:
                    print(f"   📄 Script: {content[:100]}...")
                else:
                    # Check if it has event data
                    if "event" in content.lower():
                        print(f"   ✅ Script contains 'event': {len(content)} bytes")
                        # Try to find JSON
                        if "{" in content:
                            print(f"      (Contains JSON-like data)")

        await browser.close()

    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
