"""Fetch football matches for priority teams today via kulichki.net parser."""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from src.utils.openai_client import get_client
from src.workers.kulichki_parser import get_today_matches_from_kulichki

logger = logging.getLogger(__name__)

# Priority teams in exact order (Russian names as they appear on kulichki.net)
PRIORITY_TEAMS = ["Барселона", "Реал Мадрид", "Арсенал", "ПСЖ", "Атлетико", "Манчестер"]

# Team flags for priority teams
TEAM_FLAGS = {
    "Барселона": "🇪🇸",
    "Реал Мадрид": "🇪🇸",
    "Атлетико": "🇪🇸",
    "Арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "ПСЖ": "🇫🇷",
}

# League to country flag mapping
LEAGUE_FLAGS = {
    "La Liga": "🇪🇸",
    "Premier League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Ligue 1": "🇫🇷",
}





async def get_today_matches() -> Optional[List[Dict[str, Any]]]:
    """
    Get football matches for priority teams today via championat.com parser.
    Returns up to 3 matches in priority team order.
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"[FOOTBALL] Fetching matches for {today}")
        logger.debug(f"[FOOTBALL] Priority teams: {PRIORITY_TEAMS}")

        # Get matches from kulichki.net
        logger.info(f"[FOOTBALL] Parsing kulichki.net...")
        all_matches = await get_today_matches_from_kulichki()

        if not all_matches:
            logger.info(f"[FOOTBALL] No matches found on kulichki.net")
            return None

        logger.info(f"[FOOTBALL] Found {len(all_matches)} total matches")

        # Filter to only priority teams and sort by priority order
        priority_matches = []

        for match in all_matches:
            home = match["home"]
            away = match["away"]

            # Check if either team is in priority list (fuzzy matching)
            priority_team = None
            for team in PRIORITY_TEAMS:
                if team.lower() in home.lower():
                    priority_team = team
                    break
                elif team.lower() in away.lower():
                    priority_team = team
                    break

            if priority_team:
                priority_idx = PRIORITY_TEAMS.index(priority_team)
                match["priority_idx"] = priority_idx
                priority_matches.append(match)
                logger.debug(f"[FOOTBALL] Found priority match: {home} vs {away}")

        logger.info(f"[FOOTBALL] Priority matches found: {len(priority_matches)}")

        # Sort by priority index and take top 3
        priority_matches.sort(key=lambda m: m["priority_idx"])
        result = priority_matches[:3]

        if result:
            logger.info(f"[FOOTBALL] ✓ Returning {len(result)} top priority match(es)")
            for m in result:
                logger.debug(f"[FOOTBALL]   - {m['home']} vs {m['away']}")
        else:
            logger.info(f"[FOOTBALL] No priority matches found for today")

        return result if result else None

    except Exception as e:
        logger.error(f"[FOOTBALL] Failed to get matches: {type(e).__name__}: {e}", exc_info=True)
        return None


async def format_match_with_ai(match: Dict[str, Any]) -> str:
    """Format a single match with AI-generated commentary and odds."""
    home = match.get("home", "Unknown")
    away = match.get("away", "Unknown")
    time_str = match.get("time", "TBD")
    league = match.get("league", "")

    # Get flags with fuzzy matching, fallback to league flag
    home_flag = LEAGUE_FLAGS.get(league, "⚽")
    away_flag = LEAGUE_FLAGS.get(league, "⚽")

    for team in PRIORITY_TEAMS:
        if team.lower() in home.lower():
            home_flag = TEAM_FLAGS.get(team, home_flag)
        if team.lower() in away.lower():
            away_flag = TEAM_FLAGS.get(team, away_flag)

    # Time is already converted to Tbilisi in kulichki_parser (Moscow UTC+3 → Tbilisi UTC+4)
    tbilisi_time = time_str

    # Format standings context from league table
    standings_str = ""
    standings_info = ""
    standings = match.get("standings")

    if standings and isinstance(standings, list) and len(standings) > 0:
        # Find full information for home and away teams in standings
        home_standing = None
        away_standing = None

        for standing in standings:
            team_name = standing.get("team", "").lower()
            if team_name and team_name in home.lower():
                home_standing = standing
            if team_name and team_name in away.lower():
                away_standing = standing

        # Build comprehensive standings context
        if home_standing and away_standing:
            home_pos = home_standing.get("position")
            away_pos = away_standing.get("position")

            # Get additional stats if available
            home_played = home_standing.get("played")
            away_played = away_standing.get("played")
            home_points = home_standing.get("points")
            away_points = away_standing.get("points")

            standings_str = f"Таблица: {home} на месте {home_pos}, {away} на месте {away_pos}."

            # Build detailed context for GPT
            standings_parts = []
            if home_pos and away_pos:
                standings_parts.append(f"{home}: {home_pos} место")
                if home_points:
                    standings_parts.append(f"{away}: {away_pos} место с {away_points} очками")
                else:
                    standings_parts.append(f"{away}: {away_pos} место")

            standings_info = " | ".join(standings_parts) if standings_parts else standings_str
    else:
        # For playoff matches or tournaments without standings, show tournament name
        if league and any(keyword in league.lower() for keyword in ["cup", "playoff", "champions", "europa", "final", "league"]):
            standings_str = f"🏆 {league}"
            standings_info = f"Матч турнира: {league}"

    # Generate AI commentary (1-2 sentences with maximum context)
    prompt = f"""Напиши комментарий к предстоящему матчу футбола (1-2 предложения). Используй ВСЕ доступные данные для создания наиболее информативного описания.

МАТЧ:
{home} vs {away}

ТУРНИР:
{league}

ВРЕМЯ:
{tbilisi_time} Tbilisi (GMT+4)

КОНТЕКСТ И СТАТИСТИКА:
{standings_info}

ТРЕБОВАНИЯ:
- 1-2 предложения (максимум 30 слов)
- Максимально информативно и интересно
- Укажи позиции команд в таблице, если доступно
- Упомяни турнир, если это кубок/плей-офф
- Дай оценку силе сторон (фаворит/аутсайдер/равные шансы)
- На русском языке
- Без вводных фраз типа "Это матч" или "Будет интересно"
- Естественный, информативный язык

ПРИМЕРЫ ХОРОШИХ КОММЕНТАРИЕВ:
- "Лидер таблицы против 20-го места - явный фаворит. Реал Мадрид предпочитает контролировать мяч."
- "Матч чемпионата мира: столкновение фаворитов. Обе команды в боевом настроении."
- "Финал кубка сулит напряженную борьбу. Реал едет на выезд без особых преимуществ."
- "Третий и четвертый в таблице - баланс сил примерно равен, матч обещает быть интересным."

Ответ - только комментарий без пояснений, без кавычек:"""

    commentary = None
    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=100,
            messages=[
                {"role": "system", "content": "You are a sports analyst in Russian."},
                {"role": "user", "content": prompt},
            ],
        )

        commentary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Failed to generate AI commentary: {e}")
        commentary = None

    # Build match text
    lines = [f"{home_flag} {home} vs {away} {away_flag}"]
    lines.append(f"{league} • {tbilisi_time} Tbilisi (GMT+4)")

    if standings_str:
        lines.append(standings_str)

    if commentary:
        lines.append(f"💭 {commentary}")

    return "\n".join(lines)


async def get_formatted_matches(matches: List[Dict[str, Any]]) -> Optional[str]:
    """Format all matches for digest display."""
    if not matches:
        return None

    try:
        message_lines = ["⚽ <b>Матчи сегодня:</b>", ""]

        for match in matches:
            formatted = await format_match_with_ai(match)
            message_lines.append(formatted)
            message_lines.append("")

        return "\n".join(message_lines).rstrip()

    except Exception as e:
        logger.error(f"Failed to format matches: {e}")
        return None
