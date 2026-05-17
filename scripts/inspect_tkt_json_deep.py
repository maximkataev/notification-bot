#!/usr/bin/env python3
"""Deep inspect tkt.ge JSON structure."""

import asyncio
import json
import sys
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://tkt.ge/en/events", wait_until="networkidle")
        html = await page.content()

        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script")

        for script in scripts:
            content = script.string
            if not content or len(content) < 1000:
                continue

            if content.strip().startswith('{'):
                try:
                    data = json.loads(content)

                    print("\n" + "="*100)
                    print("📊 JSON STRUCTURE ANALYSIS")
                    print("="*100 + "\n")

                    def analyze_structure(obj, level=0, max_level=5):
                        indent = "  " * level
                        if level > max_level:
                            return

                        if isinstance(obj, dict):
                            print(f"{indent}Dict with {len(obj)} keys:")
                            for key, value in list(obj.items())[:10]:
                                val_type = type(value).__name__
                                if isinstance(value, (dict, list)):
                                    if isinstance(value, dict):
                                        print(f"{indent}  ✓ {key}: Dict[{len(value)}]")
                                    else:
                                        print(f"{indent}  ✓ {key}: List[{len(value)}]")
                                    if len(value) > 0:
                                        analyze_structure(list(value)[0] if isinstance(value, list) else value, level+2, max_level)
                                else:
                                    val_str = str(value)[:60]
                                    print(f"{indent}  - {key}: {val_type} = {val_str}")

                        elif isinstance(obj, list):
                            print(f"{indent}List with {len(obj)} items:")
                            if obj:
                                first = obj[0]
                                if isinstance(first, dict):
                                    print(f"{indent}  First item keys: {list(first.keys())}")
                                else:
                                    print(f"{indent}  Type: {type(first).__name__}")

                    analyze_structure(data)

                    # Also dump first few properties
                    print("\n\n📄 Full Top-Level Keys:")
                    for key in data.keys():
                        val = data[key]
                        print(f"  {key}: {type(val).__name__} ", end="")
                        if isinstance(val, (dict, list)):
                            print(f"({len(val)} items)")
                        else:
                            print(f"= {str(val)[:50]}")

                    break

                except json.JSONDecodeError:
                    pass

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
