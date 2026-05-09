#!/usr/bin/env python3
"""Test the new rate formatting with emoji changes."""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')


def test_format():
    """Test formatting function."""

    def format_currency(value: float, decimals: int = 2) -> str:
        """Format number with space as thousands separator."""
        if value is None:
            return "N/A"
        if decimals == 5:
            formatted = f"{value:,.5f}".rstrip('0').rstrip('.')
        else:
            formatted = f"{value:,.2f}".rstrip('0').rstrip('.')
        return formatted.replace(',', ' ')

    def format_change(change_24h, change_30d) -> str:
        """Format percentage changes with arrow emojis."""
        if change_24h is None or change_30d is None:
            return ""
        arrow_24h = "↑" if change_24h >= 0 else "↓"
        arrow_30d = "↑" if change_30d >= 0 else "↓"
        return f" ({arrow_24h} {abs(change_24h):.1f}% for 24h, {arrow_30d} {abs(change_30d):.1f} % for 30d)"

    logger.info("\n" + "="*70)
    logger.info("TEST: New Currency Rate Format with Emoji Changes")
    logger.info("="*70 + "\n")

    # Test cases
    test_cases = [
        {
            "name": "BTC (both positive)",
            "symbol": "BTC",
            "rate": 80802.5,
            "decimals": 5,
            "change_24h": 0.8,
            "change_30d": 12.2,
        },
        {
            "name": "ETH (both positive)",
            "symbol": "ETH",
            "rate": 2330.91,
            "decimals": 5,
            "change_24h": 0.8,
            "change_30d": 5.6,
        },
        {
            "name": "EUR/USD (mixed)",
            "symbol": "EUR",
            "rate": 1.17786,
            "decimals": 5,
            "change_24h": -0.5,
            "change_30d": 2.3,
        },
        {
            "name": "USD/RUB (both negative)",
            "symbol": "USD",
            "rate": 74.59,
            "decimals": 2,
            "change_24h": -1.2,
            "change_30d": -3.5,
        },
    ]

    logger.info("Курсы валют:\n")
    for test in test_cases:
        rate_str = format_currency(test["rate"], decimals=test["decimals"])
        change_str = format_change(test["change_24h"], test["change_30d"])

        if test["symbol"] == "EUR":
            output = f"EUR: {rate_str} USD{change_str}"
        elif test["symbol"] == "USD":
            output = f"USD: {rate_str} RUB{change_str}"
        else:
            output = f"{test['symbol']}: {rate_str} USD{change_str}"

        logger.info(output)
        logger.info(f"  Test: {test['name']}")
        logger.info("")

    logger.info("="*70)
    logger.info("✓ Format preview complete!")
    logger.info("="*70)


if __name__ == "__main__":
    test_format()
