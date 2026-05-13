"""Fetch football (soccer) matches for today from multiple sources."""

import logging
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
from src.utils.doppler import get_secret

logger = logging.getLogger(__name__)

# API endpoints for multiple sources
API_FOOTBALL_PRIMARY = "https://api.api-football.com/v3"
API_FOOTBALL_FALLBACK = "https://v3.football.api-sports.io"
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
ESPN_SPORTS_API = "http://www.espn.com/apis/site/v2/sports/soccer"
SOFASCORE_BASE = "https://www.sofascore.com/api/v1"

# League IDs for different APIs
LEAGUES_API_FOOTBALL = {
    "La Liga": 140,  # Spanish La Liga
    "Premier League": 39,  # English Premier League
    "Ligue 1": 61,  # French Ligue 1
}

LEAGUES_FOOTBALL_DATA = {
    "La Liga": "LA",
    "Premier League": "PL",
    "Ligue 1": "FL1",
}

LEAGUES_ESPN = {
    "La Liga": "esp.laliga",
    "Premier League": "eng.premier",
    "Ligue 1": "fra.ligue1",
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

# Team to country flag mapping
TEAM_FLAGS = {
    # Spain
    "Barcelona": "🇪🇸",
    "Real Madrid": "🇪🇸",
    "Atletico Madrid": "🇪🇸",
    "Sevilla": "🇪🇸",
    "Valencia": "🇪🇸",
    "Villarreal": "🇪🇸",
    "Real Sociedad": "🇪🇸",
    "Betis": "🇪🇸",
    # England
    "Manchester City": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Manchester United": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Liverpool": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Arsenal": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Chelsea": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Tottenham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Newcastle": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Brighton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Aston Villa": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "West Ham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Fulham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Bournemouth": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Everton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Ipswich": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Nottingham": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Luton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Brentford": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Wolverhampton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Southampton": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Crystal Palace": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    # France
    "Paris Saint-Germain": "🇫🇷",
    "AS Monaco": "🇫🇷",
    "Marseille": "🇫🇷",
    "Lille": "🇫🇷",
    "Lyon": "🇫🇷",
    "Nice": "🇫🇷",
    "Toulouse": "🇫🇷",
    "Lens": "🇫🇷",
    # Germany
    "Bayern Munich": "🇩🇪",
    "Borussia Dortmund": "🇩🇪",
    "RB Leipzig": "🇩🇪",
    "Leverkusen": "🇩🇪",
    "Schalke": "🇩🇪",
    # Italy
    "Juventus": "🇮🇹",
    "AC Milan": "🇮🇹",
    "Inter Milan": "🇮🇹",
    "Roma": "🇮🇹",
    "Napoli": "🇮🇹",
}


def _get_team_flag(team_name: str) -> str:
    """Get flag emoji for team, fallback to ⚽."""
    return TEAM_FLAGS.get(team_name, "⚽")


async def _try_espn_api() -> Optional[Dict[str, Any]]:
    """Try ESPN API for match schedules."""
    try:
        today_formatted = datetime.now().strftime("%Y%m%d")
        all_matches = []
        priority_matches = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for league_name, league_code in LEAGUES_ESPN.items():
                try:
                    # ESPN scoreboard endpoint
                    response = await client.get(
                        f"{ESPN_SPORTS_API}/{league_code}/scoreboard",
                        params={"dates": today_formatted},
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    events = data.get("events", [])

                    for event in events:
                        match_info = _parse_espn_event(event, league_name)
                        if match_info:
                            all_matches.append(match_info)
                            home = match_info["home"]
                            away = match_info["away"]

                            if home in PRIORITY_TEAMS or away in PRIORITY_TEAMS:
                                priority_matches.append(match_info)
                except Exception:
                    continue

        result_matches = _sort_priority_matches(priority_matches)

        if len(result_matches) < 3 and all_matches:
            match_of_day = _find_match_of_day(all_matches)
            if match_of_day and match_of_day not in result_matches:
                result_matches.append(match_of_day)

        if result_matches:
            return {"type": "priority", "matches": result_matches[:3]}

        return None

    except Exception as e:
        logger.debug(f"ESPN API failed: {type(e).__name__}")
        return None


async def _try_football_data_org() -> Optional[Dict[str, Any]]:
    """Try football-data.org source (more reliable, free tier available)."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        all_matches = []
        priority_matches = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for league_name, league_code in LEAGUES_FOOTBALL_DATA.items():
                try:
                    # football-data.org uses dateFrom and dateTo as date range
                    response = await client.get(
                        f"{FOOTBALL_DATA_BASE}/competitions/{league_code}/matches",
                        params={"status": "SCHEDULED", "dateFrom": today, "dateTo": today},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        if not data.get("matches"):
                            continue

                        for match in data["matches"]:
                            match_info = _parse_football_data_match(match, league_name)
                            if match_info:
                                all_matches.append(match_info)
                                home = match_info["home"]
                                away = match_info["away"]

                                if home in PRIORITY_TEAMS or away in PRIORITY_TEAMS:
                                    priority_matches.append(match_info)
                except Exception:
                    continue

        # Build result: priority matches + match of day (up to 3 total)
        result_matches = _sort_priority_matches(priority_matches)

        if len(result_matches) < 3 and all_matches:
            match_of_day = _find_match_of_day(all_matches)
            if match_of_day and match_of_day not in result_matches:
                result_matches.append(match_of_day)

        if result_matches:
            return {"type": "priority", "matches": result_matches[:3]}

        return None

    except Exception as e:
        logger.debug(f"football-data.org failed: {type(e).__name__}")
        return None


async def _try_api_football() -> Optional[Dict[str, Any]]:
    """Try API-Football with fallback endpoint."""
    api_key = get_secret("API_FOOTBALL_KEY")
    if not api_key:
        logger.debug("API_FOOTBALL_KEY not configured, skipping")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    current_year = datetime.now().year
    endpoints = [API_FOOTBALL_PRIMARY, API_FOOTBALL_FALLBACK]

    for endpoint in endpoints:
        try:
            logger.debug(f"Trying API-Football: {endpoint}")
            all_matches = []
            priority_matches = []

            async with httpx.AsyncClient(timeout=10.0) as client:
                for league_name, league_id in LEAGUES_API_FOOTBALL.items():
                    try:
                        response = await client.get(
                            f"{endpoint}/fixtures",
                            params={
                                "date": today,
                                "league": league_id,
                                "season": current_year,
                            },
                            headers={"x-apisports-key": api_key},
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

                                if home in PRIORITY_TEAMS or away in PRIORITY_TEAMS:
                                    priority_matches.append(match_info)

                    except Exception:
                        continue

            result_matches = _sort_priority_matches(priority_matches)

            if len(result_matches) < 3 and all_matches:
                match_of_day = _find_match_of_day(all_matches)
                if match_of_day and match_of_day not in result_matches:
                    result_matches.append(match_of_day)

            if result_matches:
                logger.info(f"✓ Got matches from API-Football ({endpoint})")
                return {"type": "priority", "matches": result_matches[:3]}

        except Exception as e:
            logger.debug(f"  Failed with {endpoint}: {type(e).__name__}, trying next...")
            continue

    logger.debug("Could not get matches from any API-Football endpoint")
    return None


async def _try_alternative_football_source() -> Optional[Dict[str, Any]]:
    """Try alternative sources as final fallback."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        all_matches = []
        priority_matches = []

        # Try multiple alternative endpoints
        alternative_sources = [
            ("https://www.api-football.com/demo/fixtures", "API-Football Demo"),
            ("https://api.worldfootball.net/api", "WorldFootball API"),
        ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            for url, source_name in alternative_sources:
                try:
                    logger.debug(f"Trying alternative source: {source_name}")
                    response = await client.get(url, params={"date": today}, timeout=5.0)

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    if not data or (isinstance(data, list) and len(data) == 0):
                        continue

                    # Handle different response formats
                    items = data if isinstance(data, list) else data.get("response", [])

                    for item in items[:10]:  # Limit to 10 items
                        # Try to extract match info (format varies by source)
                        if isinstance(item, dict):
                            home = item.get("home_team", item.get("homeTeam", {}).get("name", "Unknown"))
                            away = item.get("away_team", item.get("awayTeam", {}).get("name", "Unknown"))
                            time = item.get("time", item.get("utcDate", "TBD"))

                            if isinstance(time, str) and "T" in time:
                                time = time.split("T")[1][:5]

                            match_info = {
                                "home": home,
                                "away": away,
                                "time": time,
                                "league": "Mixed",
                                "home_flag": _get_team_flag(home),
                                "away_flag": _get_team_flag(away),
                            }

                            if home != "Unknown" and away != "Unknown":
                                all_matches.append(match_info)

                                if home in PRIORITY_TEAMS or away in PRIORITY_TEAMS:
                                    priority_matches.append(match_info)

                    if all_matches:
                        logger.info(f"✓ Got {len(all_matches)} matches from {source_name}")
                        break

                except Exception:
                    continue

        # Build result
        if priority_matches:
            result_matches = _sort_priority_matches(priority_matches)
            if len(result_matches) < 3 and all_matches:
                match_of_day = _find_match_of_day(all_matches)
                if match_of_day and match_of_day not in result_matches:
                    result_matches.append(match_of_day)
            return {"type": "alternative", "matches": result_matches[:3]}

        return None

    except Exception as e:
        logger.debug(f"Alternative source failed: {type(e).__name__}")
        return None


async def get_today_matches() -> Optional[Dict[str, Any]]:
    """
    Get football matches for today with quadruple fallback chain.
    Tries in order:
    1. ESPN API (most reliable for current season)
    2. football-data.org (stable, free tier)
    3. API-Football with dual endpoints (if API_FOOTBALL_KEY configured)
    4. Alternative sources (final fallback)
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"Fetching football matches for {today}")

        # Try ESPN first (has most up-to-date live data)
        result = await _try_espn_api()
        if result and result.get("matches"):
            logger.info(
                f"✓ Got {len(result.get('matches', []))} match(es) from ESPN API"
            )
            return result

        # Try football-data.org (free, reliable, no API key needed)
        result = await _try_football_data_org()
        if result and result.get("matches"):
            logger.info(
                f"✓ Got {len(result.get('matches', []))} match(es) from football-data.org"
            )
            return result

        # Try API-Football if configured (requires valid API key, uses dual endpoints)
        result = await _try_api_football()
        if result and result.get("matches"):
            logger.info(
                f"✓ Got {len(result.get('matches', []))} match(es) from API-Football"
            )
            return result

        # Try alternative sources (final fallback)
        result = await _try_alternative_football_source()
        if result and result.get("matches"):
            logger.info(
                f"✓ Got {len(result.get('matches', []))} match(es) from alternative source"
            )
            return result

        logger.info("No football matches found for today from any source")
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


def _parse_espn_event(event: Dict, league_name: str) -> Optional[Dict[str, Any]]:
    """Parse a single event from ESPN API."""
    try:
        competition = event.get("competitions", [{}])[0]
        status = competition.get("status", {}).get("type", "")

        # Only show scheduled or not-started matches (status = "pre")
        if status not in ["pre", ""]:
            return None

        competitors = competition.get("competitors", [])
        if len(competitors) < 2:
            return None

        home = competitors[0].get("team", {}).get("displayName", "Unknown")
        away = competitors[1].get("team", {}).get("displayName", "Unknown")

        # Extract time
        utc_date = event.get("date", "")
        if utc_date:
            time_part = utc_date.split("T")[1][:5] if "T" in utc_date else "TBD"
        else:
            time_part = "TBD"

        return {
            "home": home,
            "away": away,
            "time": time_part,
            "league": league_name,
            "home_flag": _get_team_flag(home),
            "away_flag": _get_team_flag(away),
        }

    except Exception as e:
        logger.debug(f"Failed to parse ESPN event: {e}")
        return None


def _parse_football_data_match(match: Dict, league_name: str) -> Optional[Dict[str, Any]]:
    """Parse a single match from football-data.org API."""
    try:
        utc_date = match.get("utcDate", "")
        home_team = match.get("homeTeam", {}).get("name", "Unknown")
        away_team = match.get("awayTeam", {}).get("name", "Unknown")

        # Extract time from ISO format (2026-05-14T19:30:00Z)
        if utc_date:
            time_part = utc_date.split("T")[1][:5] if "T" in utc_date else "TBD"
        else:
            time_part = "TBD"

        return {
            "home": home_team,
            "away": away_team,
            "time": time_part,
            "league": league_name,
            "home_flag": _get_team_flag(home_team),
            "away_flag": _get_team_flag(away_team),
        }

    except Exception as e:
        logger.warning(f"Failed to parse football-data.org match: {e}")
        return None


def _parse_fixture(fixture: Dict, league_name: str) -> Optional[Dict[str, Any]]:
    """Parse a single fixture from API-Football API response."""
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

        return {
            "home": home_team,
            "away": away_team,
            "time": time_part,
            "league": league_name,
            "home_flag": _get_team_flag(home_team),
            "away_flag": _get_team_flag(away_team),
        }

    except Exception as e:
        logger.warning(f"Failed to parse fixture: {e}")
        return None
