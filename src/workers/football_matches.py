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
    "La Liga": 140,  # Spanish La Liga
    "Premier League": 39,  # English Premier League
    "Ligue 1": 61,  # French Ligue 1
}

# Priority teams (sorted by importance for display)
PRIORITY_TEAMS = ["Barcelona", "Real Madrid", "Paris Saint-Germain"]

# Key teams for "Match of the Day" (top teams in each league, sorted by priority)
KEY_TEAMS = {
    "La Liga": ["Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla", "Valencia"],
    "Premier League": [
        "Manchester City",
        "Manchester United",
        "Liverpool",
        "Arsenal",
        "Chelsea",
    ],
    "Ligue 1": ["Paris Saint-Germain", "AS Monaco", "Marseille", "Lille"],
}


async def _try_api_football() -> Optional[Dict[str, Any]]:
    """Try API-Football.com source. Returns up to 3 matches: priority teams first, then match of day."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year
        all_matches = []
        priority_matches = []  # Matches with Barcelona, Real Madrid, or PSG

        async with httpx.AsyncClient(timeout=10.0) as client:
            for league_name, league_id in LEAGUES.items():
                try:
                    response = await client.get(
                        f"{API_FOOTBALL_BASE}/fixtures",
                        params={
                            "date": today,
                            "league": league_id,
                            "season": current_year,
                        },
                        headers={"x-apisports-key": "test"},
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    if not data.get("response"):
                        continue

                    for fixture in data["response"]:
                        match_info = _parse_fixture(fixture, league_name)
                        if match_info:
                            all_matches.append(match_info)
                            home = match_info["home"]
                            away = match_info["away"]

                            # Check if match involves a priority team
                            if home in PRIORITY_TEAMS or away in PRIORITY_TEAMS:
                                priority_matches.append(match_info)

                except Exception:
                    continue

        # Build result: priority matches + match of day (up to 3 total)
        result_matches = _sort_priority_matches(priority_matches)

        # If we have room, add match of day
        if len(result_matches) < 3 and all_matches:
            match_of_day = _find_match_of_day(all_matches)
            if match_of_day and match_of_day not in result_matches:
                result_matches.append(match_of_day)

        if result_matches:
            return {"type": "priority", "matches": result_matches[:3]}  # Max 3 matches

        return None

    except Exception as e:
        logger.debug(f"API-Football failed: {type(e).__name__}")
        return None


async def _try_alternative_football_source() -> Optional[Dict[str, Any]]:
    """Try alternative source (ESPN-like data)."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        # Try to fetch from alternative endpoint (if available)
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fallback: try a different API endpoint structure
            response = await client.get(
                "https://www.api-football.com/demo/fixtures",
                params={"date": today},
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return {"type": "demo_api", "matches": []}

        return None
    except Exception as e:
        logger.debug(f"Alternative source failed: {type(e).__name__}")
        return None


async def get_today_matches() -> Optional[Dict[str, Any]]:
    """
    Get football matches for today with fallback chain.

    Returns:
        {
            "type": "barcelona" | "real_madrid" | "both" | "la_liga" | "match_of_day" | None,
            "matches": [...]
        }
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Fetching football matches for {today}")

        # Try main source first
        result = await _try_api_football()
        if result:
            logger.info(
                f"✓ Got matches from API-Football: {len(result.get('matches', []))} match(es)"
            )
            return result

        # Try alternative source
        result = await _try_alternative_football_source()
        if result:
            logger.info(f"✓ Got matches from alternative source")
            return result

        logger.info("No football matches found for today")
        return None

    except Exception as e:
        logger.warning(f"Failed to get football matches: {type(e).__name__}: {e}")
        return None


def _sort_priority_matches(
    priority_matches: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Sort priority matches by PRIORITY_TEAMS order.

    If both teams are in PRIORITY_TEAMS, sort by home team position.
    If one team is priority, sort by that team position.
    """

    def get_priority_score(match: Dict[str, Any]) -> tuple:
        home = match.get("home", "")
        away = match.get("away", "")

        home_idx = PRIORITY_TEAMS.index(home) if home in PRIORITY_TEAMS else 999
        away_idx = PRIORITY_TEAMS.index(away) if away in PRIORITY_TEAMS else 999

        # Sort by minimum index (earliest priority team in the match)
        min_idx = min(home_idx, away_idx)
        return (min_idx, home_idx)

    return sorted(priority_matches, key=get_priority_score)


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
            "emoji": emoji,
        }

    except Exception as e:
        logger.warning(f"Failed to parse fixture: {e}")
        return None
