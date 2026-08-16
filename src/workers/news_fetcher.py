"""Fetch and parse news from RSS feeds - organized by 5 category pools."""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any
from html import unescape
import feedparser
import httpx

logger = logging.getLogger(__name__)


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# POOL 1: Politics & Economics
POLITICS_ECONOMY_FEEDS = [
    "https://feeds.bloomberg.com/markets/news.rss",  # Bloomberg Markets
    "https://www.politico.eu/feed/",  # Politico Europe
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News
]

# POOL 2: Sports (football, hockey, tennis, track - NO F1, basketball, baseball)
SPORTS_FEEDS = [
    "https://feeds.bbci.co.uk/sport/rss.xml",  # BBC Sport
    "https://www.espn.com/espn/rss/news",  # ESPN
    "https://www.eurosport.com/rss/eurosport_rss_news.xml",  # Eurosport
    "https://www.goal.com/feeds/news",  # Goal.com (football)
    "https://feeds.sky.com/feed/sports/football",  # Sky Sports Football
    "https://www.marca.com/rss/futbol/",  # Marca (Spanish football)
    "https://www.as.com/rss/futbol/",  # AS.com (Spanish sports)
    "https://feeds.theguardian.com/theguardian/sport/football/rss",  # Guardian Football
]

# POOL 3: Technology & AI
TECHNOLOGY_FEEDS = [
    "https://techcrunch.com/feed/",  # TechCrunch
    "https://feeds.arstechnica.com/arstechnica/index",  # Ars Technica
    "https://news.ycombinator.com/rss",  # Hacker News
    "https://www.theverge.com/rss/index.xml",  # The Verge
    "https://feeds.bloomberg.com/technology/news.rss",  # Bloomberg Technology
]

# POOL 4: Culture & Science
CULTURE_SCIENCE_FEEDS = [
    "https://www.theguardian.com/international/rss",  # The Guardian
    "https://feeds.npr.org/1001/rss.xml",  # NPR News (culture, society)
    "https://feeds.bbci.co.uk/news/rss.xml",  # BBC News (also has culture)
]

# POOL 5: Good News (positive, inspiring stories — animals, kindness, rescues).
# Dedicated good-news / animal feeds so the pool is full of genuinely uplifting
# content instead of general hard-news where political/economic stories dominate
# (this pool feeds the "good-news-only" user, who must NOT get politics/economy/sports).
GOOD_NEWS_FEEDS = [
    "https://www.goodnewsnetwork.org/feed/",  # Good News Network (positive only)
    "https://www.positive.news/feed/",  # Positive News (positive only)
    "https://www.theguardian.com/world/animals/rss",  # Guardian Animals
    "https://www.theguardian.com/world/series/the-upside/rss",  # Guardian "The Upside"
    "https://reasonstobecheerful.world/feed/",  # Reasons to be Cheerful (solutions journalism)
    "https://www.optimistdaily.com/feed/",  # The Optimist Daily (positive only)
    "https://www.sunnyskyz.com/rss_tebow.php",  # Sunnyskyz (good news, feel-good stories)
    "https://www.theguardian.com/science/rss",  # Guardian Science (discoveries, breakthroughs)
]

# POOL 7-9: themed pools for the business/art/fashion/good-news user (Юля)
BUSINESS_FEEDS = [
    "https://feeds.bloomberg.com/markets/news.rss",  # Bloomberg Markets
    "https://www.theguardian.com/uk/business/rss",  # Guardian Business
    "https://feeds.bbci.co.uk/news/business/rss.xml",  # BBC Business
]

ART_FEEDS = [
    "https://www.theguardian.com/artanddesign/rss",  # Guardian Art & Design
    "https://hyperallergic.com/feed/",  # Hyperallergic (contemporary art)
]

FASHION_FEEDS = [
    "https://www.theguardian.com/fashion/rss",  # Guardian Fashion
    "https://www.vogue.com/feed/rss",  # Vogue
    "https://www.businessoffashion.com/arc/outboundfeeds/rss/",  # Business of Fashion
]

# POOL 10: Georgia / Tbilisi (local news — general for Максим, good-news filtered
# for Маша). Civil.ge, OC Media and JAMnews are English; Publika and Netgazeti are
# Georgian-language and much more Tbilisi-focused (city life, culture, everyday
# stories), which is what the good-news slot needs. OC Media / JAMnews also cover
# Armenia, Azerbaijan and the North Caucasus — the selector must keep only
# Georgia/Tbilisi items.
# Only real news outlets — no community/lifestyle portals, no classifieds, and no
# Sputnik-affiliated sites (sputnik-georgia.ru, newsgeorgia.ge): state propaganda
# has no place in the digest.
GEORGIA_FEEDS = [
    "https://civil.ge/feed",  # Civil Georgia (English, independent)
    "https://oc-media.org/feed/",  # OC Media (English, Caucasus-wide)
    "https://jam-news.net/feed/",  # JAMnews (English, Caucasus-wide)
    "https://publika.ge/feed/",  # Publika (Georgian, Tbilisi)
    "https://netgazeti.ge/feed/",  # Netgazeti (Georgian, Tbilisi)
    "https://on.ge/rss",  # On.ge (Georgian news portal)
    "https://batumelebi.netgazeti.ge/feed/",  # Batumelebi (Georgian, Adjara/Batumi)
]

# POOL 11: Vienna (local news for Юля — good-news slot only).
# Established news outlets only: the city public broadcaster, the national quality
# daily (plus its culture desk, which supplies most of the positive Vienna stories)
# and two general news portals. Community/district portals are excluded.
VIENNA_FEEDS = [
    "https://rss.orf.at/wien.xml",  # ORF Wien (German, city public broadcaster)
    "https://www.derstandard.at/rss",  # Der Standard (German, quality daily)
    "https://www.derstandard.at/rss/kultur",  # Der Standard Kultur (German)
    "https://feeds.thelocal.com/rss/at",  # The Local Austria (English)
    "https://www.vienna.at/rss",  # VIENNA.AT (German, news portal)
]

# TradingView news flow (https://ru.tradingview.com/news-flow/) — Russian-language
# markets & crypto wire aggregating Reuters, RBC, Oninvest, ForkLog, Cointelegraph and
# TradingView's own market recaps. There is no RSS: the page is a JS app served by the
# JSON endpoints below (headlines list + per-story body).
TRADINGVIEW_HEADLINES_URL = (
    "https://news-headlines.tradingview.com/v2/headlines?client=web&lang=ru"
)
TRADINGVIEW_STORY_URL = "https://news-headlines.tradingview.com/v2/story"

# Providers routed to the crypto pool; everything else goes to politics/economy.
TRADINGVIEW_CRYPTO_PROVIDERS = {
    "forklog", "cointelegraph", "rbc_crypto", "bitsmedia", "beincrypto", "coindar",
}

# Coins actively traded by the user — TradingView is queried per symbol so the crypto
# pool is dominated by BTC/ETH/SOL stories instead of whatever altcoin is loudest.
TRADINGVIEW_TRADED_SYMBOLS = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT",
}

# US equities & index funds followed by the user (S&P 500, Nasdaq 100).
TRADINGVIEW_STOCK_SYMBOLS = {
    "SPX": "SP:SPX",  # S&P 500 index
    "SPY": "AMEX:SPY",  # S&P 500 ETF
    "QQQ": "NASDAQ:QQQ",  # Nasdaq 100 ETF
}

# POOL 12: US stocks & funds. TradingView's symbol feeds carry the Russian-language
# Reuters/Oninvest wire on Wall Street; these two add English market coverage.
STOCKS_FEEDS = [
    # CNBC Investing
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",  # MarketWatch MarketPulse
]

_TRADINGVIEW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# POOL 6: Crypto (BTC, ETH, SOL, SUI, UNI and other major cryptocurrencies)
CRYPTO_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",  # CoinDesk
    "https://cointelegraph.com/rss",  # Cointelegraph
    "https://decrypt.co/feed",  # Decrypt
    "https://bitcoinmagazine.com/.rss/full/",  # Bitcoin Magazine
]


async def _fetch_from_feeds(
    feed_urls: List[str], hours: int, category: str, limit_per_feed: int = 15
) -> List[Dict[str, Any]]:
    """Generic fetch function for any pool of feeds."""
    logger.info(f"Fetching {category} news from {len(feed_urls)} feeds (last {hours}h)")
    all_items = []
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    successful = 0
    failed = 0

    for feed_url in feed_urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(feed_url)

                # Skip 4xx errors (not found, etc) without retry
                if 400 <= response.status_code < 500:
                    logger.debug(f"{feed_url}: {response.status_code} Not Found")
                    failed += 1
                    continue

                response.raise_for_status()

            feed = feedparser.parse(response.text)
            source_name = feed.feed.get("title", feed_url.split("/")[2])

            items_added = 0
            for entry in feed.entries[:limit_per_feed]:
                pub_time = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_time = datetime(*entry.updated_parsed[:6])

                if pub_time and pub_time < cutoff_time:
                    continue

                url = entry.get("link", "").strip()
                if not url or not url.startswith(("http://", "https://")):
                    continue

                description = entry.get("summary", "")
                description = _clean_html(description)[:800]

                item = {
                    "title": entry.get("title", ""),
                    "description": description,
                    "source": source_name,
                    "url": url,
                    "published": pub_time.isoformat() if pub_time else None,
                    "category": category,  # Tag with category
                }

                if item["title"]:
                    all_items.append(item)
                    items_added += 1

            logger.debug(f"  ✓ {source_name}: {items_added} items")
            successful += 1

        except Exception as e:
            failed += 1
            logger.debug(f"  ✗ {feed_url}: {type(e).__name__}")
            continue

    logger.info(
        f"✓ {category}: {len(all_items)} items ({successful}/{len(feed_urls)} feeds)"
    )
    return all_items


def _flatten_ast(node: Any, out: List[str]) -> None:
    """Collect the text leaves of a TradingView story AST."""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for child in node:
            _flatten_ast(child, out)
    elif isinstance(node, dict):
        for child in node.get("children") or []:
            _flatten_ast(child, out)


async def _fetch_tradingview_story(
    client: httpx.AsyncClient, story_id: str
) -> str:
    """Fetch the body text of one TradingView story. Empty string on any failure."""
    try:
        response = await client.get(
            TRADINGVIEW_STORY_URL, params={"id": story_id, "lang": "ru"}
        )
        if response.status_code != 200:
            return ""
        data = response.json()

        parts: List[str] = []
        _flatten_ast(data.get("astDescription"), parts)
        text = _clean_html(" ".join(parts))
        if not text:
            text = _clean_html(data.get("shortDescription", ""))
        return text[:800]
    except Exception as e:
        logger.debug(f"  ✗ TradingView story {story_id}: {type(e).__name__}")
        return ""


def _tradingview_tickers(entry: Dict[str, Any], watchlist: Dict[str, str]) -> List[str]:
    """Watchlist tickers an entry is tagged with, e.g. ['BTC', 'ETH']."""
    tickers = " ".join(
        s.get("symbol", "") for s in (entry.get("relatedSymbols") or [])
    ).upper()
    return [name for name in watchlist if name in tickers]


def _tradingview_usable(entry: Dict[str, Any], cutoff_ts: float) -> bool:
    """Common filters: has content, is readable, is fresh."""
    # "headline" permission = paywalled stub, there is no body to read.
    if entry.get("permission") == "headline":
        return False
    if not entry.get("title") or not entry.get("id"):
        return False
    published = entry.get("published")
    return not (isinstance(published, (int, float)) and published < cutoff_ts)


async def _tradingview_build_items(
    client: httpx.AsyncClient,
    entries: List[Dict[str, Any]],
    category: str,
    watchlist: Dict[str, str] = None,
) -> List[Dict[str, Any]]:
    """Fetch bodies for the picked headlines and map them to the news schema."""
    bodies = await asyncio.gather(
        *(_fetch_tradingview_story(client, e["id"]) for e in entries),
        return_exceptions=True,
    )

    items = []
    for entry, body in zip(entries, bodies):
        # Prefer the original publisher's URL so the article pass reads the real
        # story; TradingView's own page is JS-rendered and yields no text.
        url = entry.get("link") or (
            f"https://ru.tradingview.com{entry.get('storyPath', '')}"
        )
        if not url.startswith(("http://", "https://")):
            continue

        published = entry.get("published")
        items.append({
            "title": entry.get("title", ""),
            "description": body if isinstance(body, str) else "",
            "source": entry.get("source") or entry.get("provider", "TradingView"),
            "url": url,
            "published": (
                datetime.utcfromtimestamp(published).isoformat()
                if isinstance(published, (int, float))
                else None
            ),
            "category": category,
            "tickers": _tradingview_tickers(entry, watchlist or {}),
        })
    return items


async def get_tradingview_news(
    hours: int = 24, *, crypto: bool, limit: int = 15
) -> List[Dict[str, Any]]:
    """Fetch the TradingView news flow (https://ru.tradingview.com/news-flow/).

    Russian-language markets wire. The page itself is a JS app, so the headlines JSON
    endpoint behind it is used instead; bodies live in a separate story endpoint and
    are fetched only for the items actually kept.

    Args:
        crypto: True returns only items from crypto outlets (for the crypto pool),
            False returns everything else (markets/economy, for the politics pool).

    Returns:
        Items in the standard news schema. Empty list on any failure — TradingView
        is an extra source, never a hard dependency.
    """
    label = "crypto" if crypto else "markets"
    cutoff_ts = (datetime.utcnow() - timedelta(hours=hours)).timestamp()

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_TRADINGVIEW_HEADERS) as client:
            response = await client.get(TRADINGVIEW_HEADLINES_URL)
            response.raise_for_status()
            headlines = response.json().get("items", [])

            picked = []
            for entry in headlines:
                if not _tradingview_usable(entry, cutoff_ts):
                    continue
                if (entry.get("provider") in TRADINGVIEW_CRYPTO_PROVIDERS) != crypto:
                    continue

                picked.append(entry)
                if len(picked) >= limit:
                    break

            if not picked:
                logger.info(f"✓ TradingView {label}: 0 items")
                return []

            items = await _tradingview_build_items(
                client, picked, "crypto" if crypto else "politics"
            )

        logger.info(f"✓ TradingView {label}: {len(items)} items")
        return items

    except Exception as e:
        logger.warning(f"TradingView {label} fetch failed: {type(e).__name__}: {e}")
        return []


async def get_tradingview_symbol_news(
    watchlist: Dict[str, str],
    category: str,
    hours: int = 24,
    per_symbol: int = 6,
) -> List[Dict[str, Any]]:
    """Fetch TradingView news scoped to specific symbols (the user's own positions).

    The general wire is dominated by whatever is loudest that day, so the symbol
    endpoints are queried directly: every item they return is tagged to that symbol.
    Items are deduplicated across symbols and carry a `tickers` tag the selectors use
    to prefer stories about instruments the user actually trades.

    Args:
        watchlist: {display ticker: TradingView symbol}, e.g. {"BTC": "BINANCE:BTCUSDT"}
        category: category tag written onto the produced items
    """
    label = "/".join(watchlist)
    cutoff_ts = (datetime.utcnow() - timedelta(hours=hours)).timestamp()

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_TRADINGVIEW_HEADERS) as client:
            responses = await asyncio.gather(
                *(
                    client.get(TRADINGVIEW_HEADLINES_URL, params={"symbol": symbol})
                    for symbol in watchlist.values()
                ),
                return_exceptions=True,
            )

            picked = []
            seen_ids = set()
            for ticker, response in zip(watchlist, responses):
                if isinstance(response, Exception) or response.status_code != 200:
                    logger.debug(f"  ✗ TradingView {ticker} headlines unavailable")
                    continue

                kept = 0
                for entry in response.json().get("items", []):
                    entry_id = entry.get("id")
                    if not entry_id or entry_id in seen_ids:
                        continue
                    if not _tradingview_usable(entry, cutoff_ts):
                        continue

                    seen_ids.add(entry_id)
                    picked.append(entry)
                    kept += 1
                    if kept >= per_symbol:
                        break

            if not picked:
                logger.info(f"✓ TradingView {label}: 0 items")
                return []

            items = await _tradingview_build_items(client, picked, category, watchlist)

        logger.info(f"✓ TradingView {label}: {len(items)} items")
        return items

    except Exception as e:
        logger.warning(f"TradingView {label} fetch failed: {type(e).__name__}: {e}")
        return []


async def get_politics_economy_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch politics & economics news (RSS feeds + TradingView markets wire)."""
    rss, tradingview = await asyncio.gather(
        _fetch_from_feeds(POLITICS_ECONOMY_FEEDS, hours, "politics"),
        get_tradingview_news(hours, crypto=False),
    )
    return rss + tradingview


async def get_sports_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch sports news (football, hockey, tennis, track - NO F1, basketball, baseball)."""
    items = await _fetch_from_feeds(SPORTS_FEEDS, hours, "sports", limit_per_feed=20)

    # Filter out banned sports
    filtered = []
    for item in items:
        combined = f"{item['title']} {item['description']}".lower()
        if not any(
            ban in combined
            for ban in [
                "formula 1",
                "f1",
                "nascar",
                "motogp",
                "indycar",
                "basketball",
                "nba",
                "baseball",
                "mlb",
                "esports",
            ]
        ):
            filtered.append(item)

    return filtered


async def get_technology_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch technology & AI news."""
    return await _fetch_from_feeds(TECHNOLOGY_FEEDS, hours, "technology")


async def get_culture_science_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch culture, science, and innovation news."""
    return await _fetch_from_feeds(CULTURE_SCIENCE_FEEDS, hours, "culture")


async def get_good_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch positive, inspiring news stories."""
    items = await _fetch_from_feeds(GOOD_NEWS_FEEDS, hours, "goodness")

    # Filter out negative content for good news section
    filtered = []
    negative_keywords = [
        "dead",
        "death",
        "died",
        "war",
        "conflict",
        "tragedy",
        "disaster",
        "accident",
        "crash",
        "killed",
        "missing",
        "crime",
        "murder",
        "attack",
    ]

    for item in items:
        combined = f"{item['title']} {item['description']}".lower()
        if not any(neg in combined for neg in negative_keywords):
            filtered.append(item)

    return filtered


def _dedupe_by_url(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop repeats across merged sources, keeping the first (highest-priority) copy."""
    merged = []
    seen_urls = set()
    for item in items:
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        merged.append(item)
    return merged


async def get_crypto_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch crypto news for an active BTC/ETH/SOL trader.

    Coin-scoped TradingView items come FIRST: the selector only sees the top of this
    pool, so the stories tagged to the traded coins must not be crowded out by the
    general wire.
    """
    coins, rss, tradingview = await asyncio.gather(
        get_tradingview_symbol_news(TRADINGVIEW_TRADED_SYMBOLS, "crypto", hours),
        _fetch_from_feeds(CRYPTO_FEEDS, hours, "crypto"),
        get_tradingview_news(hours, crypto=True),
    )
    return _dedupe_by_url(coins + rss + tradingview)


async def get_stocks_news(hours: int = 72) -> List[Dict[str, Any]]:
    """Fetch US stock market news (S&P 500, Nasdaq, index funds, big single names).

    Symbol-scoped TradingView items (Russian-language Reuters/Oninvest Wall Street
    wire) come first for the same reason as in the crypto pool — the selector only
    sees the top of the list.

    The window defaults to 72h, not 24h: Wall Street is closed at weekends, so a
    Sunday or Monday digest would otherwise find an empty pool. Feeds are newest-first,
    so fresh items still lead the list on weekdays.
    """
    symbols, rss = await asyncio.gather(
        get_tradingview_symbol_news(TRADINGVIEW_STOCK_SYMBOLS, "stocks", hours),
        _fetch_from_feeds(STOCKS_FEEDS, hours, "stocks"),
    )
    return _dedupe_by_url(symbols + rss)


async def get_georgia_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch Georgia / Tbilisi local news (Максим: general, Маша: good-news slot)."""
    return await _fetch_from_feeds(GEORGIA_FEEDS, hours, "georgia", limit_per_feed=20)


async def get_vienna_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch Vienna local news (Юля: good-news slot)."""
    return await _fetch_from_feeds(VIENNA_FEEDS, hours, "vienna", limit_per_feed=20)


async def get_business_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch business & economy news (themed user Юля)."""
    return await _fetch_from_feeds(BUSINESS_FEEDS, hours, "business")


async def get_art_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch art & culture news (themed user Юля)."""
    return await _fetch_from_feeds(ART_FEEDS, hours, "art")


async def get_fashion_news(hours: int = 24) -> List[Dict[str, Any]]:
    """Fetch fashion news (themed user Юля)."""
    return await _fetch_from_feeds(FASHION_FEEDS, hours, "fashion")
