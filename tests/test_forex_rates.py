#!/usr/bin/env python3
"""Test script for forex rate fetching with historical data."""
import asyncio
import sys
from src.workers.rates_fetcher import get_crypto_and_forex_rates


async def main():
    print("🔄 Fetching crypto and forex rates with historical data...\n")

    rates = await get_crypto_and_forex_rates()

    if not rates:
        print("❌ Failed to fetch rates")
        return False

    print("✓ Rates fetched successfully:\n")

    # Display BTC
    if rates.get("btc_usd"):
        btc_24h = rates.get("btc_change_24h")
        btc_30d = rates.get("btc_change_30d")
        print(f"BTC: ${rates['btc_usd']:,.2f} USD")
        if btc_24h is not None and btc_30d is not None:
            arrow_24h = "↑" if btc_24h >= 0 else "↓"
            arrow_30d = "↑" if btc_30d >= 0 else "↓"
            print(
                f"  Change: {arrow_24h}{abs(btc_24h):.1f}% (24h) | {arrow_30d}{abs(btc_30d):.1f}% (30d)"
            )
        else:
            print(f"  Change: N/A")

    # Display ETH
    if rates.get("eth_usd"):
        eth_24h = rates.get("eth_change_24h")
        eth_30d = rates.get("eth_change_30d")
        print(f"ETH: ${rates['eth_usd']:,.2f} USD")
        if eth_24h is not None and eth_30d is not None:
            arrow_24h = "↑" if eth_24h >= 0 else "↓"
            arrow_30d = "↑" if eth_30d >= 0 else "↓"
            print(
                f"  Change: {arrow_24h}{abs(eth_24h):.1f}% (24h) | {arrow_30d}{abs(eth_30d):.1f}% (30d)"
            )
        else:
            print(f"  Change: N/A")

    # Display EUR/USD
    if rates.get("usd_eur"):
        eur_usd = 1.0 / rates["usd_eur"]
        eur_24h = rates.get("eur_change_24h")
        eur_30d = rates.get("eur_change_30d")
        print(f"\nEUR: ${eur_usd:.5f} USD")
        if eur_24h is not None and eur_30d is not None:
            arrow_24h = "↑" if eur_24h >= 0 else "↓"
            arrow_30d = "↑" if eur_30d >= 0 else "↓"
            # Show more precision for small changes
            eur_24h_display = eur_24h if abs(eur_24h) >= 0.1 else f"{eur_24h:.2f}"
            eur_30d_display = eur_30d if abs(eur_30d) >= 0.1 else f"{eur_30d:.2f}"
            print(
                f"  Change: {arrow_24h}{abs(eur_24h_display)}% (24h) | {arrow_30d}{abs(eur_30d_display)}% (30d)"
            )
        else:
            print(
                f"  Change: NOT AVAILABLE (will use historical data from DB once available)"
            )

    # Display RUB/USD
    if rates.get("usd_rub"):
        rub_usd = 1.0 / rates["usd_rub"]
        rub_24h = rates.get("rub_change_24h")
        rub_30d = rates.get("rub_change_30d")
        print(f"RUB: {rub_usd:.2f} USD")
        if rub_24h is not None and rub_30d is not None:
            arrow_24h = "↑" if rub_24h >= 0 else "↓"
            arrow_30d = "↑" if rub_30d >= 0 else "↓"
            print(
                f"  Change: {arrow_24h}{abs(rub_24h):.1f}% (24h) | {arrow_30d}{abs(rub_30d):.1f}% (30d)"
            )
        else:
            print(
                f"  Change: NOT AVAILABLE (will use historical data from DB once available)"
            )

    # Check if EUR/RUB have changes
    has_eur_changes = (
        rates.get("eur_change_24h") is not None
        and rates.get("eur_change_30d") is not None
    )
    has_rub_changes = (
        rates.get("rub_change_24h") is not None
        and rates.get("rub_change_30d") is not None
    )

    print(f"\n✓ EUR/USD changes available: {has_eur_changes}")
    print(f"✓ RUB/USD changes available: {has_rub_changes}")

    # Show raw rates dict for debugging
    print(f"\nRaw rates dict (for debugging):")
    for key in sorted(rates.keys()):
        print(f"  {key}: {rates[key]}")

    return True  # Success if we got any rates


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
