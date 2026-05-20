#!/usr/bin/env python3
"""Simulate weather block from morning digest with new sources."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ai.weather_aggregator import get_aggregated_weather, generate_clothing_recommendation

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _format_weather(weather: dict) -> str:
    """Format weather data by periods."""
    if not weather:
        return "неизвестная погода"

    if not isinstance(weather, dict):
        return "неизвестная погода"

    # New format: by periods (with emojis)
    lines = ["📍 Погода в Тбилиси:"]

    periods = {
        "morning": "☀️ Утро",
        "day": "🌞 День",
        "evening": "🌅 Вечер",
        "night": "🌙 Ночь",
    }

    for period_key, period_label in periods.items():
        if period_key in weather:
            p = weather[period_key]
            emoji = p.get("emoji", "🌤️")
            condition = p.get("condition", "переменная облачность")
            temp = p.get("temperature", "?")
            precip = p.get("precipitation_mm", 0)

            precip_str = f" (осадки {precip}мм)" if precip > 0 else ""
            lines.append(f"{emoji} {period_label}: {condition}, {temp}°C{precip_str}")

    return "\n".join(lines)


async def main():
    print("\n" + "=" * 60)
    print("🌤️  WEATHER BLOCK SIMULATION FOR MORNING DIGEST")
    print("=" * 60 + "\n")

    print("⏳ Fetching weather from Gismeteo and Yandex...\n")
    weather = await get_aggregated_weather()

    if not weather:
        print("❌ Failed to fetch weather from all sources")
        return

    print("📊 RAW WEATHER DATA:")
    print("-" * 60)
    import json
    print(json.dumps(weather, indent=2, ensure_ascii=False))

    print("\n" + "-" * 60)
    print("\n📋 FORMATTED WEATHER BLOCK:")
    print("-" * 60)
    formatted = _format_weather(weather)
    print(formatted)

    print("\n" + "-" * 60)
    print("\n👕 CLOTHING RECOMMENDATION:")
    print("-" * 60)
    clothing = await generate_clothing_recommendation(weather)
    if clothing:
        print(f"👔 Рекомендация: {clothing}")
    else:
        print("❌ Failed to generate clothing recommendation")

    print("\n" + "=" * 60)
    print("✅ Weather block simulation complete")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
