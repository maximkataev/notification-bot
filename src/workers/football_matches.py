"""Fetch football (soccer) matches for today from API-Football."""
import logging
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# API-Football free endpoint (no API key needed for basic requests)
API_FOOTBALL_BASE = "https://api.api-football.com/v3"

# League IDs in API-Football
LEAGUES = {
    "La Liga": 140,           # Spanish La Liga
    "Premier League": 39,     # English Premier League
}

# Teams we care about (for priority checking)
PRIORITY_TEAMS = ["Barcelona", "Real Madrid"]

# Key teams for "Match of the Day" (top teams in each league)
KEY_TEAMS = {
    "La Liga": [
        "Real Madrid", "Barcelona", "Atletico Madrid"
    ],
    "Premier League": [
        "Manchester City", "Manchester United", "Liverpool", "Arsenal"
    ]
}


async def get_today_matches() -> Optional[Dict[str, Any]]:
    """
    Get football matches for today, prioritizing Barcelona/Real Madrid.

    Returns:
        {
            "type": "barcelona" | "real_madrid" | "both" | "la_liga" | "premier_league" | None,
            "matches": [
                {
                    "home": "Team Name",
                    "away": "Team Name",
                    "time": "HH:MM",
                    "league": "La Liga" | "Premier League",
                    "emoji": "🟦" or "🟥"
                }
            ]
        }
        or None if no matches found
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Fetching football matches for {today}")

        all_matches = []
        barcelona_matches = []
        real_madrid_matches = []
        liga_matches = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for league_name, league_id in LEAGUES.items():
                logger.debug(f"Checking {league_name} (ID: {league_id})")

                try:
                    # Use the free endpoint with date parameter
                    response = await client.get(
                        f"{API_FOOTBALL_BASE}/fixtures",
                        params={
                            "date": today,
                            "league": league_id,
                            "season": 2024,
                        },
                        headers={"x-apisports-key": "test"}  # Free tier uses 'test' key
                    )

                    if response.status_code != 200:
                        logger.debug(f"API error for {league_name}: {response.status_code}")
                        continue

                    data = response.json()
                    if not data.get("response"):
                        continue

                    for fixture in data["response"]:
                        match_info = _parse_fixture(fixture, league_name)
                        if match_info:
                            all_matches.append(match_info)

                            # Categorize by team
                            home = match_info["home"]
                            away = match_info["away"]

                            if home == "Barcelona" or away == "Barcelona":
                                barcelona_matches.append(match_info)
                            elif home == "Real Madrid" or away == "Real Madrid":
                                real_madrid_matches.append(match_info)
                            elif league_name in ["La Liga", "Premier League"]:
                                liga_matches.append(match_info)

                except Exception as e:
                    logger.warning(f"Failed to fetch {league_name}: {type(e).__name__}: {e}")
                    continue

        # Prioritize: Barcelona/Real Madrid > Match of the Day > None
        if barcelona_matches and real_madrid_matches:
            return {
                "type": "both",
                "matches": barcelona_matches + real_madrid_matches
            }
        elif barcelona_matches:
            return {
                "type": "barcelona",
                "matches": barcelona_matches
            }
        elif real_madrid_matches:
            return {
                "type": "real_madrid",
                "matches": real_madrid_matches
            }
        else:
            # Find "Match of the Day" - highest quality match with key teams
            match_of_day = _find_match_of_day(all_matches)
            if match_of_day:
                return {
                    "type": "match_of_day",
                    "matches": [match_of_day]
                }
            else:
                logger.info("No football matches found for today")
                return None

    except Exception as e:
        logger.warning(f"Failed to get football matches: {type(e).__name__}: {e}")
        return None


def _find_match_of_day(all_matches: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Find the best match of the day - match between key teams.
    Scores matches based on how many key teams are involved.
    """
    best_match = None
    best_score = 0

    for match in all_matches:
        home = match.get("home", "")
        away = match.get("away", "")
        league = match.get("league", "")

        key_teams = KEY_TEAMS.get(league, [])

        # Score the match: 2 points if both teams are key teams, 1 point if at least one is
        score = 0
        if home in key_teams:
            score += 1
        if away in key_teams:
            score += 1

        # If both key teams and is in top league, this is match of the day
        if score > best_score:
            best_score = score
            best_match = match

    return best_match if best_score > 0 else None


def _parse_fixture(fixture: Dict, league_name: str) -> Optional[Dict[str, Any]]:
    """Parse a single fixture from API response."""
    try:
        fixture_data = fixture.get("fixture", {})
        teams = fixture.get("teams", {})
        status = fixture_data.get("status", {}).get("short", "")

        # Only show scheduled or not-started matches
        if status not in ["NS", "PST", "TBD", ""]:
            return None

        # Extract time
        fixture_time = fixture_data.get("date", "")
        if fixture_time:
            # Extract HH:MM from ISO format (2024-05-10T19:30:00+00:00)
            time_part = fixture_time.split("T")[1][:5] if "T" in fixture_time else "TBD"
        else:
            time_part = "TBD"

        home_team = teams.get("home", {}).get("name", "Unknown")
        away_team = teams.get("away", {}).get("name", "Unknown")

        # Determine emoji based on league
        emoji = "🔵" if league_name == "Premier League" else "🔴"

        return {
            "home": home_team,
            "away": away_team,
            "time": time_part,
            "league": league_name,
            "emoji": emoji
        }

    except Exception as e:
        logger.warning(f"Failed to parse fixture: {e}")
        return None
