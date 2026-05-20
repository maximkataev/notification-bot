"""Format weather data for display in digest."""

from typing import Optional, Dict, Any


# Map English period names to Russian
PERIOD_NAMES_RU = {
    "morning": "Утро",
    "day": "День",
    "evening": "Вечер",
    "night": "Ночь",
}

# Map conditions to Russian descriptions
CONDITION_DESCRIPTIONS_RU = {
    "ясно": "ясно/солнечно",
    "облачно": "пасмурно/облачно",
    "дождь": "идёт дождь",
    "снег": "идёт снег",
    "гроза": "гроза",
    "туман": "туман",
    "переменная облачность": "переменная облачность",
    "морось": "морось",
    "град": "град",
    "ливень": "ливень",
    "ледяной дождь": "ледяной дождь",
}

# Order of periods for display
PERIODS_ORDER = ["morning", "day", "evening", "night"]


def format_weather_for_digest(weather: Optional[Dict[str, Dict]]) -> Optional[str]:
    """Format weather data for morning digest.

    Args:
        weather: Dict with period→data mapping from get_aggregated_weather()

    Returns:
        Formatted weather string or None if no data

    Example output:
        Погода в Тбилиси:
        ☀️ Утро: ясно/солнечно, 15.2°C
        ⛅ День: переменная облачность, 17.7°C
        🌧️ Вечер: идёт дождь, 14.6°C
        ☁️ Ночь: пасмурно/облачно, 12.4°C
    """
    if not weather:
        return None

    lines = ["Погода в Тбилиси:"]

    # Display periods in order: morning → day → evening → night
    for period in PERIODS_ORDER:
        if period not in weather:
            continue

        data = weather[period]
        emoji = data.get("emoji", "🌤️")
        temp = data.get("temperature", 0)
        condition = data.get("condition", "облачно")

        # Get Russian descriptions
        period_ru = PERIOD_NAMES_RU.get(period, period)
        condition_ru = CONDITION_DESCRIPTIONS_RU.get(condition, condition)

        # Format line
        line = f"{emoji} {period_ru}: {condition_ru}, {temp}°C"
        lines.append(line)

    return "\n".join(lines)


def format_weather_compact(weather: Optional[Dict[str, Dict]]) -> Optional[str]:
    """Format weather data in compact one-line format.

    Example output:
        ☀️ Утро 15°C • ⛅ День 18°C • 🌧️ Вечер 16°C • ☁️ Ночь 13°C
    """
    if not weather:
        return None

    parts = []

    for period in PERIODS_ORDER:
        if period not in weather:
            continue

        data = weather[period]
        emoji = data.get("emoji", "🌤️")
        temp = data.get("temperature", 0)
        period_ru = PERIOD_NAMES_RU.get(period, period)

        parts.append(f"{emoji} {period_ru} {temp}°C")

    return " • ".join(parts)


def format_weather_with_details(weather: Optional[Dict[str, Dict]]) -> Optional[str]:
    """Format weather with full details including precipitation.

    Example output:
        Погода в Тбилиси:
        ☀️ Утро: ясно/солнечно
           Температура: 15.2°C | Осадки: 0.0 мм
        ⛅ День: переменная облачность
           Температура: 17.7°C | Осадки: 0.5 мм
        ...
    """
    if not weather:
        return None

    lines = ["Погода в Тбилиси:"]

    for period in PERIODS_ORDER:
        if period not in weather:
            continue

        data = weather[period]
        emoji = data.get("emoji", "🌤️")
        temp = data.get("temperature", 0)
        condition = data.get("condition", "облачно")
        precip = data.get("precipitation_mm", 0.0)

        period_ru = PERIOD_NAMES_RU.get(period, period)
        condition_ru = CONDITION_DESCRIPTIONS_RU.get(condition, condition)

        lines.append(f"{emoji} {period_ru}: {condition_ru}")
        lines.append(f"   Температура: {temp}°C | Осадки: {precip} мм")

    return "\n".join(lines)
