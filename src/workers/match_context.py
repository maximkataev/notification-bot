"""Get match context: standings, odds, recent form, injuries."""

import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from src.utils.openai_client import get_client
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
API_FOOTBALL_PRIMARY = "https://api.api-football.com/v3"  # Primary endpoint
API_FOOTBALL_FALLBACK = "https://v3.football.api-sports.io"  # Alternative endpoint


async def _get_match_odds(home_team: str, away_team: str, league_id: int) -> Optional[Dict[str, float]]:
    """Get betting odds from API-Football with fallback endpoint."""
    api_key = get_secret("API_FOOTBALL_KEY")
    if not api_key:
        logger.debug("API_FOOTBALL_KEY not configured")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    endpoints = [API_FOOTBALL_PRIMARY, API_FOOTBALL_FALLBACK]

    for endpoint in endpoints:
        try:
            logger.debug(f"Trying API-Football endpoint: {endpoint}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{endpoint}/fixtures",
                    params={
                        "date": today,
                        "league": league_id,
                        "season": datetime.now().year,
                    },
                    headers={"x-apisports-key": api_key},
                )

                if response.status_code != 200:
                    logger.debug(f"  Status {response.status_code}, trying next endpoint...")
                    continue

                data = response.json()
                fixtures = data.get("response", [])

                # Find matching fixture
                for fixture in fixtures:
                    teams = fixture.get("teams", {})
                    fixture_home = teams.get("home", {}).get("name", "")
                    fixture_away = teams.get("away", {}).get("name", "")

                    if fixture_home == home_team and fixture_away == away_team:
                        odds_data = fixture.get("odds", {})
                        if odds_data:
                            logger.info(f"✓ Got odds from {endpoint}")
                            # Extract main odds from the first bookmaker
                            return {
                                "home": odds_data.get("win", {}).get("home"),
                                "draw": odds_data.get("draw"),
                                "away": odds_data.get("win", {}).get("away"),
                            }

                logger.debug(f"  No matching fixture found at {endpoint}")
                continue

        except Exception as e:
            logger.debug(f"  Failed with {endpoint}: {type(e).__name__}, trying next...")
            continue

    logger.debug(f"Could not get odds from any endpoint for {home_team} vs {away_team}")
    return None


async def _get_standings_info(league_code: str, team_name: str) -> Optional[Dict[str, Any]]:
    """Get team standing info from football-data.org."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{FOOTBALL_DATA_BASE}/competitions/{league_code}/standings",
            )

            if response.status_code != 200:
                return None

            data = response.json()
            standings = data.get("standings", [])

            if not standings:
                return None

            # Get the main standings table
            table = standings[0].get("table", [])

            team_info = None
            for idx, team in enumerate(table):
                if team.get("team", {}).get("name") == team_name:
                    team_info = {
                        "position": idx + 1,
                        "points": team.get("points"),
                        "played": team.get("playedGames"),
                        "won": team.get("won"),
                        "draw": team.get("draw"),
                        "lost": team.get("lost"),
                        "goal_diff": team.get("goalDifference"),
                    }
                    break

            return team_info

    except Exception as e:
        logger.debug(f"Failed to get standings: {type(e).__name__}")
        return None


async def get_match_context(
    home_team: str, away_team: str, league_code: str, league_name: str
) -> Optional[str]:
    """
    Generate match context: standings comparison, odds, form analysis.

    Returns: Brief context text for the match (2-3 sentences)
    """
    try:
        logger.info(f"Getting context for {home_team} vs {away_team} ({league_name})")

        # Get standings for both teams
        home_standing = await _get_standings_info(league_code, home_team)
        away_standing = await _get_standings_info(league_code, away_team)

        if not home_standing or not away_standing:
            logger.debug("Could not get standings data")
            return None

        # Build context string with standings (compact format)
        home_pos = home_standing.get("position", "?")
        away_pos = away_standing.get("position", "?")
        home_pts = home_standing.get("points", 0)
        away_pts = away_standing.get("points", 0)

        point_diff = abs(home_pts - away_pts) if home_pts and away_pts else 0

        # Format: "Barcelona (1 место, +9 очков), Real Madrid (2 место)"
        if home_pts > away_pts:
            standings_str = f"{home_team} ({home_pos} место, +{point_diff} очков), {away_team} ({away_pos} место)"
        elif away_pts > home_pts:
            standings_str = f"{home_team} ({home_pos} место), {away_team} ({away_pos} место, +{point_diff} очков)"
        else:
            standings_str = f"{home_team} ({home_pos} место), {away_team} ({away_pos} место)"

        logger.info(f"✓ Match context: {standings_str}")
        return standings_str

    except Exception as e:
        logger.warning(f"Failed to get match context: {type(e).__name__}: {e}")
        return None


async def get_extended_match_analysis(
    home_team: str, away_team: str, league_name: str, league_code: str, league_id: int = None
) -> Optional[str]:
    """
    Generate compact match context with standings + odds in one line.
    Format: "Team1 (pos, +diff), Team2 (pos). Коэффициенты: X - Y - Z"
    """
    try:
        # Get standings context
        standings = await get_match_context(home_team, away_team, league_code, league_name)

        if not standings:
            logger.debug("No standings context available")
            return None

        # Build final output: standings + odds on one line
        output = standings

        # Get betting odds if league_id provided
        if league_id:
            odds = await _get_match_odds(home_team, away_team, league_id)
            if odds and odds.get("home") and odds.get("away"):
                home_odds = odds.get("home", 0)
                away_odds = odds.get("away", 0)
                draw_odds = odds.get("draw", 0)

                # Format odds as: home - draw - away
                odds_str = f"{home_odds:.2f} - {draw_odds:.2f} - {away_odds:.2f}"
                output += f" Коэффициенты: {odds_str}."

                logger.info(f"✓ Got odds: {odds_str} ({home_team} vs {away_team})")
            else:
                logger.debug("No odds available")
        else:
            logger.debug("No league_id provided, skipping odds")

        logger.info(f"✓ Context generated: {output}")
        return output

    except Exception as e:
        logger.warning(f"Failed to generate match context: {type(e).__name__}: {e}")
        return None
