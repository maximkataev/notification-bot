"""Fetch cryptocurrency and forex rates with historical data."""

import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)

# yfinance is no longer used - Yahoo Finance deprecated EURUSD=X and USDRUB=X symbols
# Historical forex data is not available; graceful degradation in digest
try:
    import yfinance as yf

    YFINANCE_AVAILABLE = False  # Force disable due to deprecated symbols
    logger.info("yfinance available but disabled (Yahoo Finance symbols deprecated)")
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.debug("yfinance not installed")

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
except:
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


def _get_historical_from_yahoo_finance() -> Dict[str, Optional[float]]:
    """Get historical forex rates from Yahoo Finance (free, no API key needed).

    DEPRECATED: Yahoo Finance no longer supports EURUSD=X and USDRUB=X symbols.
    Returns empty dict (graceful degradation).
    """
    logger.debug("Yahoo Finance historical data unavailable (deprecated symbols)")
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


async def get_crypto_and_forex_rates() -> Optional[Dict]:
    """Fetch BTC, ETH, USD/EUR, USD/RUB rates with 24h and 30d changes."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            rates = {}

            # Fetch BTC with full market data (has 24h and 30d changes)
            logger.info("Fetching crypto rates from CoinGecko")
            btc_url = (
                "https://api.coingecko.com/api/v3/coins/bitcoin?"
                "localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
            )
            btc_response = await client.get(btc_url)
            btc_response.raise_for_status()
            btc_data = btc_response.json()

            # Extract BTC rates from market_data with validation
            market_data = btc_data.get("market_data", {})
            btc_price = market_data.get("current_price", {}).get("usd")
            rates["btc_usd"] = btc_price if btc_price and btc_price > 0 else None
            rates["btc_change_24h"] = market_data.get("price_change_percentage_24h")
            rates["btc_change_30d"] = market_data.get("price_change_percentage_30d")

            # Fetch ETH with full market data
            eth_url = (
                "https://api.coingecko.com/api/v3/coins/ethereum?"
                "localization=false&tickers=false&market_data=true&community_data=false&developer_data=false"
            )
            eth_response = await client.get(eth_url)
            eth_response.raise_for_status()
            eth_data = eth_response.json()

            # Extract ETH rates from market_data with validation
            eth_market_data = eth_data.get("market_data", {})
            eth_price = eth_market_data.get("current_price", {}).get("usd")
            rates["eth_usd"] = eth_price if eth_price and eth_price > 0 else None
            rates["eth_change_24h"] = eth_market_data.get("price_change_percentage_24h")
            rates["eth_change_30d"] = eth_market_data.get("price_change_percentage_30d")

            # Safe logging with None checks
            btc_info = f"${rates['btc_usd']}" if rates["btc_usd"] else "N/A"
            if (
                rates["btc_change_24h"] is not None
                and rates["btc_change_30d"] is not None
            ):
                btc_info += f" ({rates['btc_change_24h']:+.1f}% for 24h, {rates['btc_change_30d']:+.1f} % for 30d)"

            eth_info = f"${rates['eth_usd']}" if rates["eth_usd"] else "N/A"
            if (
                rates["eth_change_24h"] is not None
                and rates["eth_change_30d"] is not None
            ):
                eth_info += f" ({rates['eth_change_24h']:+.1f}% for 24h, {rates['eth_change_30d']:+.1f} % for 30d)"

            logger.info(f"✓ Crypto: BTC={btc_info}, ETH={eth_info}")

            # Fetch forex rates from exchangerate-api (primary)
            logger.info("Fetching forex rates from exchangerate-api")
            try:
                forex_url = "https://api.exchangerate-api.com/v4/latest/USD"
                forex_response = await client.get(forex_url)
                forex_response.raise_for_status()
                forex_data = forex_response.json()

                eur_rate = forex_data.get("rates", {}).get("EUR")
                rub_rate = forex_data.get("rates", {}).get("RUB")
                rates["usd_eur"] = eur_rate if eur_rate and eur_rate > 0 else None
                rates["usd_rub"] = rub_rate if rub_rate and rub_rate > 0 else None
            except Exception as e:
                logger.warning(f"exchangerate-api failed, trying ECB fallback: {e}")
                ecb_rates = await _get_rates_from_ecb()
                if ecb_rates:
                    rates["usd_eur"] = ecb_rates.get("usd_eur")
                    rates["usd_rub"] = ecb_rates.get("usd_rub")
                else:
                    rates["usd_eur"] = None
                    rates["usd_rub"] = None

            # Get historical forex rates
            logger.info("Fetching historical forex changes")
            historical_forex = await get_historical_forex_rates()
            logger.debug(f"Historical forex data: {historical_forex}")

            # Use historical data
            rates["eur_change_24h"] = historical_forex.get("eur_usd_24h")
            rates["eur_change_30d"] = historical_forex.get("eur_usd_30d")
            rates["rub_change_24h"] = historical_forex.get("rub_usd_24h")
            rates["rub_change_30d"] = historical_forex.get("rub_usd_30d")
            logger.debug(
                f"Assigned forex changes: eur_24h={rates.get('eur_change_24h')}, eur_30d={rates.get('eur_change_30d')}, rub_24h={rates.get('rub_change_24h')}, rub_30d={rates.get('rub_change_30d')}"
            )

            logger.info(
                f"✓ Forex: 1 USD = {rates['usd_eur']:.5f} EUR, {rates['usd_rub']:.2f} RUB"
            )

            return rates

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch rates: {type(e).__name__}: {e}")
        logger.debug(f"Full error:", exc_info=True)
        return None
