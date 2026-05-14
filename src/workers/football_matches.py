"""Fetch football matches for priority teams today via kulichki.net parser."""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from src.utils.openai_client import get_client
from src.workers.pari_odds import get_pari_odds
from src.workers.kulichki_parser import get_today_matches_from_kulichki

logger = logging.getLogger(__name__)

# Priority teams in exact order (Russian names as they appear on kulichki.net)
PRIORITY_TEAMS = ["Барселона", "Реал Мадрид", "Арсенал", "ПСЖ", "Атлетико", "Манчестер"]

# Team to league mapping
TEAM_TO_LEAGUE = {
    "Барселона": "La Liga",
    "Реал Мадрид": "La Liga",
    "Атлетико": "La Liga",
    "Арсенал": "Premier League",
    "Манчестер": "Premier League",
    "ПСЖ": "Ligue 1",
}

# Team flags
TEAM_FLAGS = {
    "Барселона": "🇪🇸",
    "Реал Мадрид": "🇪🇸",
    "Атлетико": "🇪🇸",
    "Арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "ПСЖ": "🇫🇷",
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

    # Get flags with fuzzy matching
    home_flag = "⚽"
    away_flag = "⚽"
    for team in PRIORITY_TEAMS:
        if team.lower() in home.lower():
            home_flag = TEAM_FLAGS.get(team, "⚽")
        if team.lower() in away.lower():
            away_flag = TEAM_FLAGS.get(team, "⚽")

    # Convert time from UTC to Tbilisi time (GMT+4)
    # If time is HH:MM in UTC, add 4 hours
    if time_str != "TBD":
        try:
            hour, minute = map(int, time_str.split(":"))
            hour = (hour + 4) % 24
            tbilisi_time = f"{hour:02d}:{minute:02d}"
        except:
            tbilisi_time = time_str
    else:
        tbilisi_time = "TBD"

    # Format standings context from league table
    standings_str = ""
    standings_info = ""
    standings = match.get("standings")

    if standings and isinstance(standings, list) and len(standings) > 0:
        # Find positions of home and away teams in standings
        home_pos = None
        away_pos = None

        for standing in standings:
            team_name = standing.get("team", "").lower()
            if team_name and team_name in home.lower():
                home_pos = standing.get("position")
            if team_name and team_name in away.lower():
                away_pos = standing.get("position")

        # Build standings context
        if home_pos and away_pos:
            standings_info = f"Таблица: {home} на месте {home_pos}, {away} на месте {away_pos}."
            standings_str = standings_info

    # Fetch odds from pari.ru (non-blocking, optional, with timeout)
    odds_str = ""
    odds_info = ""
    try:
        # Use timeout to prevent Playwright from hanging
        try:
            if hasattr(asyncio, "timeout"):  # Python 3.11+
                async with asyncio.timeout(5):
                    odds = await get_pari_odds(home, away)
            else:
                odds = await asyncio.wait_for(get_pari_odds(home, away), timeout=5.0)

            if odds:
                home_odd, draw_odd, away_odd = odds
                # Format: "1.25 - 3.00 - 7.01"
                odds_str = f" Коэффициенты: {home_odd:.2f} - {draw_odd:.2f} - {away_odd:.2f}."
                odds_info = f"Коэффициенты: {home_odd:.2f} (победа {home}), {draw_odd:.2f} (ничья), {away_odd:.2f} (победа {away})."
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug(f"Pari.ru parser timeout for {home} vs {away}")
            odds_str = ""
            odds_info = ""
    except Exception as e:
        logger.debug(f"Failed to get odds for {home} vs {away}: {e}")
        odds_str = ""
        odds_info = ""

    # Generate AI commentary (2 sentences with context)
    prompt = f"""Напиши комментарий к предстоящему матчу футбола (1-2 предложения).

МАТЧ:
{home} vs {away} ({league}) в {tbilisi_time}

КОНТЕКСТ:
{standings_info}
{odds_info}

ТРЕБОВАНИЯ:
- 1-2 предложения (не более 25 слов)
- Информативно и интересно
- Используй контекст (таблица, коэффициенты)
- На русском языке
- Без вводных фраз типа "Это матч" или "Будет интересно"

Примеры:
- "Барселона может стать чемпионом при победе с коэффициентом 1.25. Рилм будет защищаться с куда худшими шансами."
- "Классическое противостояние: лидер таблицы против второго. Букмекеры явно верят в фаворита."

Ответ - только комментарий без пояснений:"""

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
        if odds_str:
            lines.append(standings_str.rstrip(".") + odds_str)
        else:
            lines.append(standings_str)
    elif odds_str:
        lines.append(f"📊{odds_str}")

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
