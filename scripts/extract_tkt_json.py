#!/usr/bin/env python3
"""Extract event data from tkt.ge JSON."""

import asyncio
import json
import sys
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    print("\n" + "="*100)
    print("🔍 EXTRACTING TKT.GE EVENT JSON")
    print("="*100 + "\n")

    async with async_playwright() as p:
        print("🎬 Loading tkt.ge...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://tkt.ge/en/events", wait_until="networkidle")
        html = await page.content()

        soup = BeautifulSoup(html, "html.parser")

        # Find script with event data
        scripts = soup.find_all("script")
        print(f"Found {len(scripts)} scripts\n")

        event_data = None
        for i, script in enumerate(scripts):
            content = script.string
            if content and len(content) > 1000 and "event" in content.lower():
                print(f"Script {i}: {len(content)} bytes")

                # Try to extract JSON
                # Look for patterns like: window.data = {...}
                patterns = [
                    r'window\.data\s*=\s*({.*?});',
                    r'window\.events\s*=\s*({.*?});',
                    r'var\s+events\s*=\s*({.*?});',
                    r'"events"\s*:\s*\[',
                ]

                for pattern in patterns:
                    match = re.search(pattern, content, re.DOTALL)
                    if match:
                        print(f"   ✅ Found pattern: {pattern[:50]}...")
                        break

                # Try direct JSON parse if it starts with {
                if content.strip().startswith('{'):
                    try:
                        event_data = json.loads(content)
                        print(f"   ✅ Successfully parsed as JSON")
                        break
                    except json.JSONDecodeError:
                        pass

        if event_data:
            print(f"\n📊 JSON Structure:")
            print(f"   Keys: {list(event_data.keys())[:10]}")

            # Try to find events in various places
            if isinstance(event_data, dict):
                for key in ['events', 'data', 'content', 'items', 'shows']:
                    if key in event_data:
                        items = event_data[key]
                        if isinstance(items, list):
                            print(f"\n   ✅ Found '{key}': {len(items)} items")
                            if items:
                                print(f"      First item keys: {list(items[0].keys())}")
                                print(f"      Sample: {json.dumps(items[0], indent=2)[:300]}")
                            event_data = items
                            break

        # Try alternative: look for items selector
        print(f"\n🔎 Looking for 'item' elements:")
        items = soup.select("[class*='item']")
        print(f"   Found {len(items)} elements with class containing 'item'")

        if items:
            print(f"\n   Analyzing first 3 items:\n")
            for i, item in enumerate(items[:3], 1):
                print(f"   Item {i}:")
                print(f"      Tag: {item.name}")
                print(f"      Classes: {item.get('class', [])}")
                print(f"      Text (first 100): {item.get_text(strip=True)[:100]}")

                # Check for nested data
                for child in item.children:
                    if hasattr(child, 'name') and child.name:
                        print(f"      - {child.name}: {str(child)[:60]}")

        await browser.close()

    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
