#!/usr/bin/env python3
"""Test different fallback scenarios."""

import asyncio
import sys
import logging
from unittest.mock import patch, AsyncMock

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(message)s'
)

sys.path.insert(0, '/Users/maximkataev/Desktop/notification-bot')

from src.ai.weather_sources import get_aggregated_weather


async def test_scenario_1():
    """СЦЕНАРИЙ 1: BBC работает (нормальный случай)."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 1: BBC РАБОТАЕТ (нормальный случай)")
    print("=" * 100)
    print()
    print("Ожидание: BBC вернёт данные, fallbacks не вызовутся")
    print("-" * 100)
    print()

    result = await get_aggregated_weather()

    print()
    if result:
        print("✓ УСПЕХ! BBC вернул данные:")
        for period in ["night", "morning", "day", "evening"]:
            if period in result:
                data = result[period]
                print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C")
    else:
        print("✗ НЕУДАЧА")


async def test_scenario_2():
    """СЦЕНАРИЙ 2: BBC падает, WW работает."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 2: BBC ПАДАЕТ, WORLD-WEATHER.RU РАБОТАЕТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC вернёт None → fallback 1 (WW) вернёт данные")
    print("-" * 100)
    print()

    # Mock BBC to return None (simulate failure)
    with patch('src.ai.weather_sources._fetch_bbc_html', new_callable=AsyncMock) as mock_bbc_fetch:
        mock_bbc_fetch.return_value = None

        result = await get_aggregated_weather()

        print()
        if result:
            print("✓ УСПЕХ! WW (fallback 1) вернул данные:")
            for period in ["night", "morning", "day", "evening"]:
                if period in result:
                    data = result[period]
                    print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C")
        else:
            print("✗ НЕУДАЧА")


async def test_scenario_3():
    """СЦЕНАРИЙ 3: BBC и WW падают, wttr работает."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 3: BBC И WORLD-WEATHER ПАДАЮТ, WTTR.IN РАБОТАЕТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC падает → WW падает → wttr (fallback 2) вернёт данные")
    print("-" * 100)
    print()

    # Mock BBC and WW to return None
    with patch('src.ai.weather_sources._fetch_bbc_html', new_callable=AsyncMock) as mock_bbc, \
         patch('src.ai.weather_sources._fetch_worldweather_html', new_callable=AsyncMock) as mock_ww:
        mock_bbc.return_value = None
        mock_ww.return_value = None

        result = await get_aggregated_weather()

        print()
        if result:
            print("✓ УСПЕХ! wttr.in (fallback 2) вернул данные:")
            for period in ["night", "morning", "day", "evening"]:
                if period in result:
                    data = result[period]
                    print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C")
        else:
            print("✗ НЕУДАЧА")


async def test_scenario_4():
    """СЦЕНАРИЙ 4: ВСЕ источники падают."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 4: ВСЕ ИСТОЧНИКИ ПАДАЮТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC падает → WW падает → wttr падает → return None")
    print("-" * 100)
    print()

    # Mock all sources to return None/fail
    with patch('src.ai.weather_sources._fetch_bbc_html', new_callable=AsyncMock) as mock_bbc, \
         patch('src.ai.weather_sources._fetch_worldweather_html', new_callable=AsyncMock) as mock_ww, \
         patch('src.ai.weather_sources._fetch_wttr', new_callable=AsyncMock) as mock_wttr:
        mock_bbc.return_value = None
        mock_ww.return_value = None
        mock_wttr.return_value = None

        result = await get_aggregated_weather()

        print()
        if result is None:
            print("✓ ОЖИДАЕМО: Все источники падают → return None")
            print("   (Digest пропустит погоду, но продолжит работу)")
        else:
            print("✗ НЕОЖИДАННО: Получили данные когда не должны были")


async def test_scenario_5():
    """СЦЕНАРИЙ 5: BBC загружается, но парсинг падает → WW работает."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 5: BBC ЗАГРУЖАЕТСЯ, НО ПАРСИНГ ПАДАЕТ → WW РАБОТАЕТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC._fetch() успех, но _parse() вернёт None → WW работает")
    print("-" * 100)
    print()

    # Mock BBC parse to return None (JSON structure broken)
    with patch('src.ai.weather_sources._parse_bbc', return_value=None):
        result = await get_aggregated_weather()

        print()
        if result:
            print("✓ УСПЕХ! BBC парсинг падает → WW вернул данные:")
            for period in ["night", "morning", "day", "evening"]:
                if period in result:
                    data = result[period]
                    print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C")
        else:
            print("✗ НЕУДАЧА")


async def run_all_tests():
    """Run all scenario tests."""
    print("\n\n")
    print("╔" + "=" * 98 + "╗")
    print("║" + " " * 98 + "║")
    print("║" + "ТЕСТИРОВАНИЕ FALLBACK ЦЕПОЧКИ".center(98) + "║")
    print("║" + " " * 98 + "║")
    print("╚" + "=" * 98 + "╝")

    await test_scenario_1()
    await test_scenario_2()
    await test_scenario_3()
    await test_scenario_4()
    await test_scenario_5()

    print("\n\n")
    print("=" * 100)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 100)
    print()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
