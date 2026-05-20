#!/usr/bin/env python3
"""Debug BBC Weather HTML structure to understand how to parse it correctly."""

import asyncio
import sys
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_bbc_html


async def debug_bbc():
    """Fetch and analyze BBC HTML structure."""
    print("=" * 80)
    print("DEBUGGING BBC WEATHER HTML STRUCTURE")
    print("=" * 80)
    print()

    html = await _fetch_bbc_html()
    if not html:
        print("Failed to fetch BBC HTML")
        return

    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Look for data attributes
    print("1. Looking for elements with 'forecast' in data attributes...")
    print("-" * 80)
    forecast_data = soup.find_all(attrs={"data-testid": lambda x: x and "forecast" in (x or "").lower()})
    print(f"   Found {len(forecast_data)} elements with 'forecast' in data-testid")
    if forecast_data:
        for idx, elem in enumerate(forecast_data[:3]):
            print(f"   [{idx}]: {elem.get('data-testid')}")
            print(f"        Content: {elem.get_text(strip=True)[:100]}")
    print()

    # Strategy 2: Look for role="img" elements with weather info
    print("2. Looking for elements with role='img' (weather icons)...")
    print("-" * 80)
    role_img = soup.find_all(attrs={"role": "img"})
    print(f"   Found {len(role_img)} elements with role='img'")
    if role_img:
        for idx, elem in enumerate(role_img[:5]):
            aria_label = elem.get("aria-label", "")
            print(f"   [{idx}]: aria-label='{aria_label[:80]}'")
    print()

    # Strategy 3: Look for aria-label with temperature
    print("3. Looking for elements with aria-label containing '°'...")
    print("-" * 80)
    temp_aria = soup.find_all(attrs={"aria-label": lambda x: x and "°" in (x or "")})
    print(f"   Found {len(temp_aria)} elements with temperature in aria-label")
    if temp_aria:
        for idx, elem in enumerate(temp_aria[:10]):
            aria_label = elem.get("aria-label", "")
            print(f"   [{idx}]: {aria_label}")
    print()

    # Strategy 4: Look for specific forecast structure
    print("4. Looking for forecast-related divs with specific classes...")
    print("-" * 80)
    all_divs = soup.find_all("div")
    forecast_divs = [d for d in all_divs if any(
        cls in (d.get("class", []) or [])
        for cls in ["forecast", "period", "card", "item", "weather"]
    )]
    print(f"   Found {len(forecast_divs)} divs with forecast/period/card/item/weather classes")
    if forecast_divs:
        for idx, div in enumerate(forecast_divs[:5]):
            classes = " ".join(div.get("class", []) or [])
            text = div.get_text(strip=True)[:80]
            print(f"   [{idx}]: classes='{classes}'")
            print(f"           text='{text}'")
    print()

    # Strategy 5: Look for text patterns indicating periods
    print("5. Looking for text patterns (night, day, morning, evening)...")
    print("-" * 80)
    period_keywords = ["night", "morning", "day", "evening", "today", "tomorrow"]
    for keyword in period_keywords:
        elems = [e for e in soup.find_all()
                if keyword.lower() in (e.get_text(strip=True) or "").lower()
                and e.name in ["div", "span", "p", "h3", "h4"]]
        if elems:
            print(f"   '{keyword}': found {len(elems)} elements")
            for idx, elem in enumerate(elems[:2]):
                text = elem.get_text(strip=True)[:80]
                print(f"      [{idx}]: {text}")
    print()

    # Strategy 6: Look at the overall structure
    print("6. Top-level structure analysis...")
    print("-" * 80)
    main_content = soup.find(attrs={"id": "main"}) or soup.find("main")
    if main_content:
        print(f"   Found main content element")
        sections = main_content.find_all(["section", "article"], recursive=False)
        print(f"   Contains {len(sections)} sections/articles at top level")
        for idx, sec in enumerate(sections[:3]):
            heading = sec.find(["h1", "h2", "h3"])
            print(f"   [{idx}]: {heading.get_text(strip=True) if heading else 'no heading'}")
    print()

    # Strategy 7: Look for script tags with JSON data (BBC often embeds data in scripts)
    print("7. Looking for embedded JSON data in script tags...")
    print("-" * 80)
    scripts = soup.find_all("script", type="application/json")
    print(f"   Found {len(scripts)} script tags with application/json type")
    if scripts:
        for idx, script in enumerate(scripts[:2]):
            content = script.string or ""
            if content:
                print(f"   [{idx}]: {content[:150]}...")
    print()

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_bbc())
