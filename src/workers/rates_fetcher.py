"""Fetch cryptocurrency and forex rates with historical data."""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)

# Cache for historical forex rates (updated by background worker every 1 hour)
_historical_forex_cache = {
    "data": None,
    "timestamp": None,
}

# Open Exchange Rates API key for historical forex data
# Get free key at: https://openexchangerates.org/ (1000 requests/month free tier)
# If set in Doppler, will fetch historical 24h and 30d changes
from src.utils.doppler import get_secret

try:
    OPEN_EXCHANGE_RATES_API_KEY = get_secret("OPEN_EXCHANGE_RATES_API_KEY")
except (ValueError, TypeError):
    OPEN_EXCHANGE_RATES_API_KEY = None


async def _get_historical_from_open_exchange_rates(
    api_key: str,
) -> Dict[str, Optional[float]]:
    """Try to fetch historical data from Open Exchange Rates API.

    Free tier (1000 requests/month) supports historical data for dates up to 1 year.
    Get free API key: https://openexchangerates.org/
    """
    try:
        from datetime import datetime, timedelta

        async with httpx.AsyncClient(timeout=10.0) as client:
            today = datetime.now().date()
            day_ago = today - timedelta(days=1)
            days_30_ago = today - timedelta(days=30)

            # Fetch rates for different dates
            urls = {
                "today": f"https://openexchangerates.org/api/historical/{today}.json?base=USD&symbols=EUR,RUB&app_id={api_key}",
                "1d_ago": f"https://openexchangerates.org/api/historical/{day_ago}.json?base=USD&symbols=EUR,RUB&app_id={api_key}",
                "30d_ago": f"https://openexchangerates.org/api/historical/{days_30_ago}.json?base=USD&symbols=EUR,RUB&app_id={api_key}",
            }

            responses = {}
            for key, url in urls.items():
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        responses[key] = resp.json().get("rates", {})
                except Exception as e:
                    logger.debug(f"Failed to fetch {key}: {e}")

            if len(responses) < 3:
                logger.debug("Insufficient Open Exchange Rates data")
                return {}

            result = {}

            # Calculate EUR/USD changes
            eur_today = responses["today"].get("EUR")
            eur_1d = responses["1d_ago"].get("EUR")
            eur_30d = responses["30d_ago"].get("EUR")

            if eur_today and eur_1d:
                eur_usd_today = 1.0 / eur_today
                eur_usd_1d = 1.0 / eur_1d
                change = ((eur_usd_today - eur_usd_1d) / eur_usd_1d) * 100
                result["eur_usd_24h"] = round(change, 1)

            if eur_today and eur_30d:
                eur_usd_today = 1.0 / eur_today
                eur_usd_30d = 1.0 / eur_30d
                change = ((eur_usd_today - eur_usd_30d) / eur_usd_30d) * 100
                result["eur_usd_30d"] = round(change, 1)

            # Calculate RUB/USD changes
            rub_today = responses["today"].get("RUB")
            rub_1d = responses["1d_ago"].get("RUB")
            rub_30d = responses["30d_ago"].get("RUB")

            if rub_today and rub_1d:
                rub_usd_today = 1.0 / rub_today
                rub_usd_1d = 1.0 / rub_1d
                change = ((rub_usd_today - rub_usd_1d) / rub_usd_1d) * 100
                result["rub_usd_24h"] = round(change, 1)

            if rub_today and rub_30d:
                rub_usd_today = 1.0 / rub_today
                rub_usd_30d = 1.0 / rub_30d
                change = ((rub_usd_today - rub_usd_30d) / rub_usd_30d) * 100
                result["rub_usd_30d"] = round(change, 1)

            return result

    except Exception as e:
        logger.debug(f"Open Exchange Rates failed: {e}")
        return {}


async def _update_historical_forex_cache():
    """Background worker: fetch and cache historical forex rates (called every 1 hour).

    This is called by a background scheduler to update the cache.
    Does NOT log "unavailable" - just updates cache if API available.
    """
    if not OPEN_EXCHANGE_RATES_API_KEY:
        logger.debug(
            "Open Exchange Rates API key not set, skipping historical forex update"
        )
        return

    try:
        logger.info("Updating historical forex rates from Open Exchange Rates API")
        result = await _get_historical_from_open_exchange_rates(
            OPEN_EXCHANGE_RATES_API_KEY
        )
        if result:
            _historical_forex_cache["data"] = result
            _historical_forex_cache["timestamp"] = datetime.now()
            logger.info(f"✓ Cached historical forex: {result}")
        else:
            logger.warning("Open Exchange Rates returned no data")
    except Exception as e:
        logger.warning(f"Failed to update forex cache: {type(e).__name__}: {e}")


async def get_historical_forex_rates() -> Dict[str, Optional[float]]:
    """Return cached historical forex rates (updated by background worker every 1 hour).

    Does NOT make API calls - uses data cached by _update_historical_forex_cache().
    Returns empty dict if cache is empty.
    """
    if _historical_forex_cache["data"] is not None:
        logger.debug(
            f"✓ Using cached historical forex: {_historical_forex_cache['data']}"
        )
        return _historical_forex_cache["data"]

    logger.debug("Historical forex cache is empty")
    return {}


async def _get_crypto_from_binance() -> Optional[Dict[str, Optional[float]]]:
    """Fallback crypto source: Binance public API (used when CoinGecko 429s).

    24h change comes from the /ticker/24hr endpoint; 30d change is computed from
    daily klines (close 30 days ago vs latest close). No API key required.
    """
    result: Dict[str, Optional[float]] = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for coin, symbol in (("btc", "BTCUSDT"), ("eth", "ETHUSDT")):
                # Price + 24h change
                ticker = await client.get(
                    f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
                )
                ticker.raise_for_status()
                tdata = ticker.json()
                price = float(tdata["lastPrice"])
                result[f"{coin}_usd"] = price if price > 0 else None
                result[f"{coin}_change_24h"] = round(float(tdata["priceChangePercent"]), 1)

                # 30d change from daily klines (31 candles → close ~30 days ago)
                try:
                    klines = await client.get(
                        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=31"
                    )
                    klines.raise_for_status()
                    candles = klines.json()
                    if len(candles) >= 2:
                        close_30d_ago = float(candles[0][4])
                        latest_close = float(candles[-1][4])
                        if close_30d_ago > 0:
                            result[f"{coin}_change_30d"] = round(
                                (latest_close - close_30d_ago) / close_30d_ago * 100, 1
                            )
                except Exception as e:
                    logger.debug(f"Binance 30d klines for {symbol} failed: {e}")

        logger.info(
            f"✓ Crypto (Binance fallback): BTC=${result.get('btc_usd')}, ETH=${result.get('eth_usd')}"
        )
        return result
    except Exception as e:
        logger.warning(f"Binance crypto fallback failed: {type(e).__name__}: {e}")
        return None


async def _get_crypto_from_coinbase() -> Optional[Dict[str, Optional[float]]]:
    """Last-resort crypto source: Coinbase spot price (used if CoinGecko AND Binance fail).

    Price only — no 24h/30d change (those will simply be omitted from the digest).
    """
    result: Dict[str, Optional[float]] = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for coin, pair in (("btc", "BTC-USD"), ("eth", "ETH-USD")):
                resp = await client.get(f"https://api.coinbase.com/v2/prices/{pair}/spot")
                resp.raise_for_status()
                amount = resp.json().get("data", {}).get("amount")
                if amount:
                    price = float(amount)
                    result[f"{coin}_usd"] = price if price > 0 else None
        if result.get("btc_usd") or result.get("eth_usd"):
            logger.info(f"✓ Crypto (Coinbase fallback): BTC=${result.get('btc_usd')}, ETH=${result.get('eth_usd')}")
            return result
        return None
    except Exception as e:
        logger.warning(f"Coinbase crypto fallback failed: {type(e).__name__}: {e}")
        return None


async def _get_rates_from_ecb() -> Optional[Dict[str, float]]:
    """Fetch forex rates from European Central Bank (official, reliable fallback).

    ECB provides daily rates for all major currencies via free XML feed.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            ecb_url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
            response = await client.get(ecb_url)
            response.raise_for_status()

            import xml.etree.ElementTree as ET

            root = ET.fromstring(response.content)

            rates = {}
            for cube in root.iter(
                "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}Cube"
            ):
                currency = cube.get("currency")
                rate = cube.get("rate")
                if currency and rate:
                    try:
                        rates[currency] = float(rate)
                    except ValueError:
                        pass

            if "USD" in rates:
                eur_per_usd = 1.0 / rates["USD"]
                return {"usd_eur": eur_per_usd, "usd_rub": rates.get("RUB")}
        return None
    except Exception as e:
        logger.debug(f"ECB fallback failed: {e}")
        return None


# S&P 500 quote. TradingView's scanner is primary — it returns level, session change
# and 1-month performance in one call. Yahoo is the fallback and rate-limits hard
# (429) when called often, so it is only touched when TradingView fails. Stooq sits
# behind a JS challenge and cannot be used server-side at all.
_SP500_TRADINGVIEW_URL = (
    "https://scanner.tradingview.com/symbol"
    "?symbol=SP%3ASPX&fields=close,change,Perf.1M"
)
_SP500_YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=2mo&interval=1d"
)
_SP500_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


async def _get_sp500_from_tradingview(
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Optional[float]]]:
    """S&P 500 level + changes from the TradingView scanner. None on failure."""
    try:
        response = await client.get(_SP500_TRADINGVIEW_URL, headers=_SP500_HEADERS)
        response.raise_for_status()
        data = response.json()

        level = data.get("close")
        if not level:
            return None
        return {
            "sp500": level,
            "sp500_change_24h": data.get("change"),
            "sp500_change_30d": data.get("Perf.1M"),
        }
    except Exception as e:
        logger.debug(f"TradingView S&P 500 failed: {type(e).__name__}: {e}")
        return None


async def _get_sp500_from_yahoo(
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Optional[float]]]:
    """S&P 500 level + changes computed from Yahoo daily closes. None on failure."""
    try:
        response = await client.get(_SP500_YAHOO_URL, headers=_SP500_HEADERS)
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]

        meta = result.get("meta", {})
        closes = [c for c in result["indicators"]["quote"][0].get("close") or [] if c]

        level = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        if not level:
            return None

        quote = {"sp500": level, "sp500_change_24h": None, "sp500_change_30d": None}

        # Previous close: the session before the latest one.
        prev_close = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose")
        if prev_close:
            quote["sp500_change_24h"] = (level - prev_close) / prev_close * 100

        # ~30 calendar days back = ~21 trading sessions.
        if len(closes) >= 22:
            month_ago = closes[-22]
            quote["sp500_change_30d"] = (level - month_ago) / month_ago * 100

        return quote
    except Exception as e:
        logger.debug(f"Yahoo S&P 500 failed: {type(e).__name__}: {e}")
        return None


async def get_sp500_quote(client: httpx.AsyncClient) -> Dict[str, Optional[float]]:
    """Fetch the S&P 500 level with its last-session and 30-day changes.

    Returns {"sp500": level, "sp500_change_24h": %, "sp500_change_30d": %} — all None
    if every source failed, in which case the digest simply omits the line. The "24h"
    change is the move versus the previous close; over a weekend that is Friday's
    session, which is what an index quote means anyway.
    """
    quote = await _get_sp500_from_tradingview(client)
    if not quote:
        logger.info("TradingView S&P 500 unavailable, trying Yahoo")
        quote = await _get_sp500_from_yahoo(client)

    if not quote:
        logger.warning("⚠️  S&P 500 quote unavailable from all sources")
        return {"sp500": None, "sp500_change_24h": None, "sp500_change_30d": None}

    logger.info(f"✓ S&P 500: {quote['sp500']:,.2f}")
    return quote


async def get_crypto_and_forex_rates() -> Optional[Dict]:
    """Fetch BTC, ETH, USD/EUR, USD/RUB rates with 24h and 30d changes.

    Crypto and forex are fetched independently: a failure in one (e.g. CoinGecko
    429) must NOT drop the other from the digest. Returns whatever succeeded, or
    None only if every source failed.
    """
    rates = {
        "btc_usd": None, "btc_change_24h": None, "btc_change_30d": None,
        "eth_usd": None, "eth_change_24h": None, "eth_change_30d": None,
        "usd_eur": None, "usd_rub": None,
        "eur_change_24h": None, "eur_change_30d": None,
        "rub_change_24h": None, "rub_change_30d": None,
        "sp500": None, "sp500_change_24h": None, "sp500_change_30d": None,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # ---- Crypto (CoinGecko) — isolated so a 429 doesn't kill forex ----
        try:
            logger.info("Fetching crypto rates from CoinGecko")
            btc_url = (
                "https://api.coingecko.com/api/v3/coins/bitcoin?"
                "localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
            )
            btc_response = await client.get(btc_url)
            btc_response.raise_for_status()
            market_data = btc_response.json().get("market_data", {})
            btc_price = market_data.get("current_price", {}).get("usd")
            rates["btc_usd"] = btc_price if btc_price and btc_price > 0 else None
            rates["btc_change_24h"] = market_data.get("price_change_percentage_24h")
            rates["btc_change_30d"] = market_data.get("price_change_percentage_30d")

            eth_url = (
                "https://api.coingecko.com/api/v3/coins/ethereum?"
                "localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
            )
            eth_response = await client.get(eth_url)
            eth_response.raise_for_status()
            eth_market_data = eth_response.json().get("market_data", {})
            eth_price = eth_market_data.get("current_price", {}).get("usd")
            rates["eth_usd"] = eth_price if eth_price and eth_price > 0 else None
            rates["eth_change_24h"] = eth_market_data.get("price_change_percentage_24h")
            rates["eth_change_30d"] = eth_market_data.get("price_change_percentage_30d")

            logger.info(f"✓ Crypto: BTC=${rates['btc_usd']}, ETH=${rates['eth_usd']}")
        except Exception as e:
            logger.warning(f"⚠️  CoinGecko failed ({type(e).__name__}), trying Binance fallback...")
            crypto_fallback = await _get_crypto_from_binance()
            if not crypto_fallback:
                logger.warning("⚠️  Binance failed too, trying Coinbase fallback...")
                crypto_fallback = await _get_crypto_from_coinbase()
            if crypto_fallback:
                for k, v in crypto_fallback.items():
                    if v is not None:
                        rates[k] = v
            else:
                logger.warning("⚠️  Crypto rates unavailable from all sources (forex unaffected)")

        # ---- Forex (exchangerate-api → ECB fallback) — isolated ----
        try:
            logger.info("Fetching forex rates from exchangerate-api")
            forex_url = "https://api.exchangerate-api.com/v4/latest/USD"
            forex_response = await client.get(forex_url)
            forex_response.raise_for_status()
            forex_rates = forex_response.json().get("rates", {})
            eur_rate = forex_rates.get("EUR")
            rub_rate = forex_rates.get("RUB")
            rates["usd_eur"] = eur_rate if eur_rate and eur_rate > 0 else None
            rates["usd_rub"] = rub_rate if rub_rate and rub_rate > 0 else None
        except Exception as e:
            logger.warning(f"exchangerate-api failed, trying ECB fallback: {e}")
            try:
                ecb_rates = await _get_rates_from_ecb()
                if ecb_rates:
                    rates["usd_eur"] = ecb_rates.get("usd_eur")
                    rates["usd_rub"] = ecb_rates.get("usd_rub")
            except Exception as e2:
                logger.warning(f"⚠️  Forex rates unavailable: {type(e2).__name__}: {e2}")

        # ---- S&P 500 (Yahoo) — isolated, never fatal ----
        rates.update(await get_sp500_quote(client))

        # ---- Historical forex changes (cached, never fatal) ----
        try:
            historical_forex = await get_historical_forex_rates()
            rates["eur_change_24h"] = historical_forex.get("eur_usd_24h")
            rates["eur_change_30d"] = historical_forex.get("eur_usd_30d")
            rates["rub_change_24h"] = historical_forex.get("rub_usd_24h")
            rates["rub_change_30d"] = historical_forex.get("rub_usd_30d")
        except Exception as e:
            logger.debug(f"Historical forex changes unavailable: {e}")

    # Log forex with None-safe formatting
    eur_log = f"{rates['usd_eur']:.5f}" if rates["usd_eur"] is not None else "N/A"
    rub_log = f"{rates['usd_rub']:.2f}" if rates["usd_rub"] is not None else "N/A"
    logger.info(f"✓ Forex: 1 USD = {eur_log} EUR, {rub_log} RUB")

    # Return partial data if anything succeeded; None only if everything failed
    if any(rates.get(k) for k in ("btc_usd", "eth_usd", "usd_eur", "usd_rub", "sp500")):
        return rates

    logger.warning("⚠️  All rate sources failed (crypto + forex)")
    return None
