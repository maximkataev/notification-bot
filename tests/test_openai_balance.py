#!/usr/bin/env python3
"""Test script for OpenAI balance checking."""
import asyncio
import sys
from src.workers.openai_balance import get_openai_balance, format_balance


async def main():
    print("🔄 Fetching OpenAI account balance...\n")

    balance = await get_openai_balance()

    if balance is not None:
        print("✓ Balance fetched successfully\n")
        formatted = format_balance(balance)
        print(formatted)
        return True
    else:
        print("❌ Failed to fetch balance")
        print("\nPossible reasons:")
        print("1. API key not configured (check OPENAI_API_KEY in Doppler)")
        print("2. API key invalid or expired")
        print("3. Billing API endpoint not accessible")
        print("4. Insufficient permissions on the API key")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
