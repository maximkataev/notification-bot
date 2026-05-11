#!/usr/bin/env python3
"""Test GWP parser to see current water cuts."""
import asyncio
import logging
from bs4 import BeautifulSoup
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_all_water_cuts():
    """Fetch all water cuts from GWP website (all streets)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        urls = {
            "https://www.gwp.ge/en/news/scheduled-works/": "Scheduled Works",
            "https://www.gwp.ge/en/news/nonscheduled-works/": "Unscheduled Works",
        }

        for url, work_type in urls.items():
            print(f"\n{'='*60}")
            print(f"🔍 Checking: {work_type}")
            print(f"{'='*60}")

            try:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                print(f"✓ Successfully fetched {url}\n")
            except Exception as e:
                print(f"✗ Error fetching {url}: {e}\n")
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            # Try different selectors to find articles
            articles = (
                soup.find_all("div", class_="item-news")
                or soup.find_all("article")
                or soup.find_all("div", class_="news-item")
                or soup.find_all("div", class_="news")
                or soup.find_all("li", class_="news")
            )

            print(f"Found {len(articles)} article(s)\n")

            if not articles:
                print("⚠️  No articles found. Dumping first 2000 chars of HTML:\n")
                print(response.text[:2000])
                print("\n...")
            else:
                for i, article in enumerate(articles[:10], 1):
                    article_text = article.get_text(separator=" ", strip=True)

                    # Try to extract title
                    title = None
                    for tag in ["h2", "h3", "h4"]:
                        heading = article.find(tag)
                        if heading:
                            title = heading.get_text(strip=True)
                            break

                    if not title:
                        title_elem = article.find("a", class_="title") or article.find(
                            "a"
                        )
                        if title_elem:
                            title = title_elem.get_text(strip=True)

                    if not title:
                        title = article_text[:100]

                    print(f"{i}. {title}")
                    print(f"   Full text: {article_text[:200]}...")
                    print()


async def check_vazha_iverievi():
    """Check specifically for Vazha Iverievi street."""
    print(f"\n{'='*60}")
    print("🏠 Checking specifically for VAZHA IVERIEVI street")
    print(f"{'='*60}\n")

    try:
        from src.workers.gwp_checker import check_gwp_works, check_water_cuts_today

        result = await check_gwp_works()
        print(f"Result from check_gwp_works():")
        print(f"  {result}\n")

        result2 = await check_water_cuts_today()
        print(f"Result from check_water_cuts_today():")
        print(f"  {result2}\n")

    except Exception as e:
        print(f"✗ Error running GWP functions: {e}\n")


async def main():
    print("\n" + "=" * 60)
    print("GWP PARSER TEST")
    print("=" * 60)

    await get_all_water_cuts()
    await check_vazha_iverievi()


if __name__ == "__main__":
    asyncio.run(main())
