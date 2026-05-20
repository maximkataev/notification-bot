#!/usr/bin/env python3
"""Detailed explanation of how fallback logic works."""

print("=" * 100)
print("HOW FALLBACK CHAIN WORKS")
print("=" * 100)
print()

print("Функция get_aggregated_weather() использует простую логику:")
print()

# Show the logic visually
logic = """
ПОПЫТКА 1: BBC
──────────────
bbc_html = await _fetch_bbc_html()

if bbc_html:                          # Если загрузка успешна
    bbc_weather = _parse_bbc(bbc_html)

    if bbc_weather:                   # Если парсинг успешен
        return bbc_weather            # ✓ УСПЕХ! Вернуть BBC данные

    else:                             # Если парсинг ошибка
        logger.warning("Parse failed, trying fallback 1...")
        # → Переход на FALLBACK 1

else:                                 # Если загрузка ошибка
    logger.warning("Fetch failed, trying fallback 1...")
    # → Переход на FALLBACK 1


FALLBACK 1: World-Weather.ru
─────────────────────────────
ww_html = await _fetch_worldweather_html()

if ww_html:
    ww_weather = _parse_worldweather(ww_html)

    if ww_weather:
        return ww_weather             # ✓ УСПЕХ! Вернуть World-Weather данные
    else:
        logger.warning("Parse failed, trying fallback 2...")
        # → Переход на FALLBACK 2
else:
    logger.warning("Fetch failed, trying fallback 2...")
    # → Переход на FALLBACK 2


FALLBACK 2: wttr.in
───────────────────
wttr_weather = await _fetch_wttr()

if wttr_weather:
    return wttr_weather               # ✓ УСПЕХ! Вернуть wttr.in данные
else:
    logger.warning("Fetch failed, all sources exhausted...")
    # → Продолжить дальше


ВСЕ ИСТОЧНИКИ ИСЧЕРПАНЫ
────────────────────────
logger.error("❌ All weather sources failed")
return None                           # ✗ ОШИБКА! Вернуть None
"""

print(logic)
print()
print("=" * 100)
print("СЦЕНАРИИ")
print("=" * 100)
print()

scenarios = [
    {
        "name": "СЦЕНАРИЙ 1: BBC работает",
        "steps": [
            "BBC._fetch() → успех ✓",
            "BBC._parse() → успех ✓",
            "return BBC data",
            "⏱️ Время: ~2 сек (только BBC)"
        ]
    },
    {
        "name": "СЦЕНАРИЙ 2: BBC загрузка падает, World-Weather работает",
        "steps": [
            "BBC._fetch() → timeout ✗",
            "BBC._parse() → не вызывается (нет HTML)",
            "→ Переход на World-Weather",
            "WW._fetch() → успех ✓",
            "WW._parse() → успех ✓",
            "return WW data",
            "⏱️ Время: ~12 сек (BBC timeout 10s + WW 2s)"
        ]
    },
    {
        "name": "СЦЕНАРИЙ 3: BBC работает, но парсинг падает, wttr.in работает",
        "steps": [
            "BBC._fetch() → успех ✓",
            "BBC._parse() → ошибка ✗ (JSON структура неверна)",
            "→ Переход на World-Weather",
            "WW._fetch() → успех ✓",
            "WW._parse() → ошибка ✗ (HTML изменился)",
            "→ Переход на wttr.in",
            "wttr._fetch() → успех ✓",
            "return wttr data",
            "⏱️ Время: ~4 сек (все быстро, только парсинг падает)"
        ]
    },
    {
        "name": "СЦЕНАРИЙ 4: ВСЕ ИСТОЧНИКИ ПАДАЮТ",
        "steps": [
            "BBC._fetch() → timeout ✗",
            "→ World-Weather",
            "WW._fetch() → timeout ✗",
            "→ wttr.in",
            "wttr._fetch() → timeout ✗",
            "logger.error('All weather sources failed')",
            "return None",
            "⏱️ Время: ~30 сек (3 timeout по 10 сек каждый)"
        ]
    }
]

for idx, scenario in enumerate(scenarios, 1):
    print(f"{scenario['name']}")
    print("-" * 100)
    for step in scenario["steps"]:
        if step.startswith("⏱️"):
            print(f"\n  {step}\n")
        elif "→" in step:
            print(f"  {step}")
        elif "✓" in step or "✗" in step:
            print(f"    {step}")
        else:
            print(f"    {step}")
    print()

print("=" * 100)
print("КЛЮЧЕВЫЕ МОМЕНТЫ")
print("=" * 100)
print()
print("1. РАННИЙ ВЫХОД (early return):")
print("   - Как только один источник вернёт успех, цепочка прерывается")
print("   - Остальные источники не вызываются")
print()
print("2. TIMEOUT ЗАЩИТА:")
print("   - Каждый _fetch() имеет timeout (обычно 10-15 сек)")
print("   - Если источник зависает, мы переходим на следующий")
print()
print("3. ПАРСИНГ ОШИБКИ:")
print("   - Если HTML/JSON загружен, но парсинг падает")
print("   - Мы не пытаемся исправить, просто переходим на fallback")
print()
print("4. GRACEFUL DEGRADATION:")
print("   - Если все источники падают → return None")
print("   - Digest пропускает погоду, но продолжает работать")
print("   - Не крашится и не зависает")
print()
print("=" * 100)
