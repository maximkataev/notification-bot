#!/usr/bin/env python3
"""Debug Georgian weather table structure."""

import asyncio
import sys
import logging
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import _fetch_georgian_weather_html


async def debug():
    """Debug Georgian weather table."""
    print("=" * 100)
    print("DEBUGGING GEORGIAN WEATHER TABLE STRUCTURE")
    print("=" * 100)
    print()

    html = await _fetch_georgian_weather_html()
    if not html:
        print("Failed to fetch HTML")
        return

    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", {"class": "table"})
    if not table:
        print("No table found")
        return

    rows = table.find_all("tr")
    print(f"Total rows in table: {len(rows)}")
    print()

    # Show first 10 rows
    for idx, row in enumerate(rows[:10]):
        cells = row.find_all("td")

        print(f"Row {idx}: {len(cells)} cells")

        if len(cells) > 0:
            # Show cell contents
            for cell_idx, cell in enumerate(cells[:5]):
                text = cell.get_text(strip=True)[:50]
                print(f"  Cell {cell_idx}: {text}")

        # Check for rowspan (indicates date rows)
        td_with_rowspan = row.find("td", {"rowspan": True})
        if td_with_rowspan:
            print(f"  >>> DATE ROW (rowspan={td_with_rowspan.get('rowspan')}): {td_with_rowspan.get_text(strip=True)}")

        print()


if __name__ == "__main__":
    asyncio.run(debug())
