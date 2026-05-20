"""Format clothing recommendation for display in digest."""

from typing import Optional, Dict, Any


def format_clothing_recommendation(recommendation: Optional[str]) -> Optional[str]:
    """Format clothing recommendation with emoji and title.

    Args:
        recommendation: Plain text recommendation from ChatGPT

    Returns:
        Formatted string with emoji and title, or None if no recommendation

    Example output:
        👕 Рекомендуемая одежда
        Я вижу дождь и грозу, поэтому надень футболку с длинным рукавом, худи, куртку и удобные закрытые кроссовки
    """
    if not recommendation:
        return None

    return f"👕 Рекомендуемая одежда\n{recommendation}"


def format_clothing_compact(recommendation: Optional[str]) -> Optional[str]:
    """Format clothing recommendation in compact format.

    Args:
        recommendation: Plain text recommendation from ChatGPT

    Returns:
        Formatted string on single line

    Example output:
        👕 Футболка с длинным рукавом, худи, куртка и закрытые кроссовки
    """
    if not recommendation:
        return None

    # Try to extract just the clothing items from the recommendation
    # Usually ChatGPT ends with the clothing suggestion
    # Format: "👕 [extracted clothing items]"

    return f"👕 {recommendation}"


def format_clothing_with_reason(
    recommendation: Optional[str],
    weather: Optional[Dict[str, Dict]]
) -> Optional[str]:
    """Format clothing recommendation with weather reason.

    Args:
        recommendation: Plain text recommendation from ChatGPT
        weather: Weather data dict

    Returns:
        Formatted string with emoji, title, weather reason, and recommendation

    Example output:
        👕 Рекомендуемая одежда

        Погода: 🌧️ идёт дождь, 16°C | 🌧️ идёт дождь, 20°C

        Рекомендация:
        Я вижу дождь и грозу, поэтому надень футболку с длинным рукавом, худи, куртку и удобные закрытые кроссовки
    """
    if not recommendation:
        return None

    lines = ["👕 Рекомендуемая одежда"]

    # Add weather context if available
    if weather:
        # Extract key weather conditions from all periods
        conditions = set()
        for period_data in weather.values():
            conditions.add(period_data.get("condition", ""))

        if conditions and conditions != {""}:
            weather_str = " | ".join(
                f"{weather[p].get('emoji', '🌤️')} {weather[p].get('condition', '')}, {weather[p].get('temperature', 0)}°C"
                for p in ["morning", "day", "evening"] if p in weather
            )
            lines.append("")
            lines.append(f"Погода: {weather_str}")

    lines.append("")
    lines.append("Рекомендация:")
    lines.append(recommendation)

    return "\n".join(lines)
