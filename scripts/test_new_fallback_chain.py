#!/usr/bin/env python3
"""Test new fallback chain: BBC → Georgian Weather."""

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
    """СЦЕНАРИЙ 1: BBC работает."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 1: BBC РАБОТАЕТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC вернёт данные, Georgian fallback не вызовется")
    print("-" * 100)
    print()

    result = await get_aggregated_weather()

    print()
    if result:
        print("✓ УСПЕХ! BBC вернул данные:")
        for period in ["night", "morning", "day", "evening"]:
            if period in result:
                data = result[period]
                print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C, {data['condition']}")
        return True
    else:
        print("✗ НЕУДАЧА")
        return False


async def test_scenario_2():
    """СЦЕНАРИЙ 2: BBC падает, Georgian работает."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 2: BBC ПАДАЕТ, GEORGIAN WEATHER РАБОТАЕТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC вернёт None → Georgian вернёт данные")
    print("-" * 100)
    print()

    # Mock BBC to return None
    with patch('src.ai.weather_sources._fetch_bbc_html', new_callable=AsyncMock) as mock_bbc:
        mock_bbc.return_value = None

        result = await get_aggregated_weather()

        print()
        if result:
            print("✓ УСПЕХ! Georgian Weather вернул данные:")
            for period in ["night", "morning", "day", "evening"]:
                if period in result:
                    data = result[period]
                    print(f"  {period:>8}: {data['emoji']} {data['temperature']:>5.1f}°C, {data['condition']}")
            return True
        else:
            print("✗ НЕУДАЧА")
            return False


async def test_scenario_3():
    """СЦЕНАРИЙ 3: ВСЕ падают."""
    print("\n" + "=" * 100)
    print("СЦЕНАРИЙ 3: ВСЕ ИСТОЧНИКИ ПАДАЮТ")
    print("=" * 100)
    print()
    print("Ожидание: BBC падает → Georgian падает → return None (graceful degradation)")
    print("-" * 100)
    print()

    # Mock both to return None
    with patch('src.ai.weather_sources._fetch_bbc_html', new_callable=AsyncMock) as mock_bbc, \
         patch('src.ai.weather_sources._fetch_georgian_weather_html', new_callable=AsyncMock) as mock_georgian:
        mock_bbc.return_value = None
        mock_georgian.return_value = None

        result = await get_aggregated_weather()

        print()
        if result is None:
            print("✓ ОЖИДАЕМО: Все источники падают → return None")
            print("   (Digest пропустит погоду, но продолжит работу)")
            return True
        else:
            print("✗ НЕОЖИДАННО: Получили данные когда не должны были")
            return False


async def run_all_tests():
    """Run all scenario tests."""
    print("\n\n")
    print("╔" + "=" * 98 + "╗")
    print("║" + " " * 98 + "║")
    print("║" + "НОВАЯ ЦЕПОЧКА FALLBACKS: BBC → GEORGIAN WEATHER".center(98) + "║")
    print("║" + " " * 98 + "║")
    print("╚" + "=" * 98 + "╝")

    results = []
    results.append(await test_scenario_1())
    results.append(await test_scenario_2())
    results.append(await test_scenario_3())

    print("\n\n")
    print("=" * 100)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 100)
    print()
    print(f"✓ Сценарий 1 (BBC работает): {'ПРОЙДЕН' if results[0] else 'НЕ ПРОЙДЕН'}")
    print(f"✓ Сценарий 2 (BBC падает, Georgian работает): {'ПРОЙДЕН' if results[1] else 'НЕ ПРОЙДЕН'}")
    print(f"✓ Сценарий 3 (Все падают): {'ПРОЙДЕН' if results[2] else 'НЕ ПРОЙДЕН'}")
    print()

    if all(results):
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")

    print()
    print("=" * 100)
    print()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
