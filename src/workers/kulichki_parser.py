"""Parse football matches from football.kulichki.net."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# Priority teams in exact order (Russian names as they appear on kulichki.net)
PRIORITY_TEAMS = ["Барселона", "Реал Мадрид", "Арсенал", "ПСЖ", "Атлетико", "Манчестер"]

# Team flags
TEAM_FLAGS = {
    "Барселона": "🇪🇸",
    "Реал Мадрид": "🇪🇸",
    "Атлетико": "🇪🇸",
    "Арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "ПСЖ": "🇫🇷",
}

# League URLs
LEAGUE_URLS = {
    "La Liga": "https://football.kulichki.net/spain/",
    "Premier League": "https://football.kulichki.net/england/",
    "Ligue 1": "https://football.kulichki.net/france/",
}


async def get_today_matches_from_kulichki() -> Optional[List[Dict[str, Any]]]:
    """
    Parse today's football matches from football.kulichki.net.
    Returns up to 3 matches for priority teams with standings context.
    """
    try:
        logger.info(f"[KULICHKI] Fetching matches")

        all_matches = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for league_name, url in LEAGUE_URLS.items():
                logger.info(f"[KULICHKI] Fetching {league_name} from {url}")

                try:
                    response = await client.get(url)
                    response.raise_for_status()

                    matches = _parse_league_page(response.text, league_name)
                    standings = _parse_standings_table(response.text, league_name)

                    logger.info(f"[KULICHKI] {league_name}: found {len(matches)} matches, standings: {len(standings) if standings else 0} teams")

                    # Attach standings to matches from this league
                    for match in matches:
                        match["standings"] = standings

                    all_matches.extend(matches)

                except Exception as e:
                    logger.warning(f"[KULICHKI] Failed to fetch {league_name}: {e}")
                    continue

        if not all_matches:
            logger.info(f"[KULICHKI] No matches found")
            return None

        logger.info(f"[KULICHKI] Total matches: {len(all_matches)}")

        # Filter to priority teams (fuzzy matching)
        priority_matches = []
        for match in all_matches:
            home = match["home"]
            away = match["away"]

            for priority_team in PRIORITY_TEAMS:
                if priority_team.lower() in home.lower():
                    match["priority_idx"] = PRIORITY_TEAMS.index(priority_team)
                    priority_matches.append(match)
                    logger.debug(f"[KULICHKI] Priority: {home} vs {away}")
                    break
                elif priority_team.lower() in away.lower():
                    match["priority_idx"] = PRIORITY_TEAMS.index(priority_team)
                    priority_matches.append(match)
                    logger.debug(f"[KULICHKI] Priority: {home} vs {away}")
                    break

        logger.info(f"[KULICHKI] Priority matches: {len(priority_matches)}")

        # Sort by priority
        priority_matches.sort(key=lambda m: m.get("priority_idx", 999))

        return priority_matches[:3] if priority_matches else None

    except Exception as e:
        logger.warning(f"[KULICHKI] Failed: {type(e).__name__}: {e}")
        return None


def _parse_standings_table(html: str, league_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Parse standings/tournament table from kulichki.net league page HTML.
    Returns list of teams with position, name, played, wins, draws, losses, goals, points.
    """
    soup = BeautifulSoup(html, "html.parser")
    standings = []

    try:
        # Look for tables that contain standings data
        tables = soup.find_all("table")
        logger.debug(f"[KULICHKI] {league_name}: {len(tables)} tables found")

        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue

            # Check if this is a standings table by looking for header indicators
            header_text = ""
            if rows:
                header_text = rows[0].get_text().lower()

            # Look for standings table indicators (position, points, played, etc.)
            if any(keyword in header_text for keyword in ["place", "pos", "team", "p", "w", "d", "l", "pts", "очк", "место", "команда"]):
                # Parse standings rows
                for row in rows[1:]:  # Skip header
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue

                    try:
                        # Try to extract position and team name
                        # Format varies, but typically: [pos] [team] [matches] [wins] [draws] [losses] [goals] [points]
                        pos_text = cells[0].get_text().strip() if len(cells) > 0 else ""
                        team_text = cells[1].get_text().strip() if len(cells) > 1 else ""

                        # Skip if looks like a sub-header or invalid row
                        if not pos_text or not team_text or len(team_text) < 2:
                            continue

                        # Try to extract position as number
                        try:
                            position = int(pos_text)
                        except (ValueError, TypeError):
                            continue

                        # Clean team name
                        team_name = " ".join(team_text.split())

                        # Extract remaining stats
                        stats = {}
                        if len(cells) > 2:
                            stats_text = [c.get_text().strip() for c in cells[2:]]
                            # Try to parse as: [played] [wins] [draws] [losses] [goals] [points]
                            if len(stats_text) >= 2:
                                try:
                                    stats["played"] = int(stats_text[0]) if stats_text[0].isdigit() else None
                                    stats["points"] = int(stats_text[-1]) if stats_text[-1].isdigit() else None
                                except (ValueError, IndexError):
                                    pass

                        standing = {
                            "position": position,
                            "team": team_name,
                            **stats
                        }

                        standings.append(standing)
                        logger.debug(f"[KULICHKI] {league_name}: {position}. {team_name} ({stats.get('points')} pts)")

                    except Exception as e:
                        logger.debug(f"[KULICHKI] Error parsing standings row: {e}")
                        continue

                # If we found standings, return them
                if standings:
                    logger.info(f"[KULICHKI] {league_name}: parsed {len(standings)} standings entries")
                    return standings

    except Exception as e:
        logger.warning(f"[KULICHKI] Error parsing standings for {league_name}: {e}")

    return None


def _parse_league_page(html: str, league_name: str) -> List[Dict[str, Any]]:
    """
    Parse matches from kulichki.net league page HTML.
    Structure: [Date] [Home - Away] [Score]
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []

    try:
        tables = soup.find_all("table")
        logger.debug(f"[KULICHKI] {league_name}: {len(tables)} tables")

        for table in tables:
            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all("td")

                # Match row has format: [Date] [Teams] [Score] [...]
                if len(cells) < 2:
                    continue

                try:
                    # Get teams cell (usually cell[1])
                    teams_cell = cells[1].get_text().strip() if len(cells) > 1 else ""

                    # Skip header/empty rows
                    if not teams_cell or "тур" in teams_cell.lower() or "клуб" in teams_cell.lower():
                        continue

                    # Parse teams from "Home - Away" format
                    if " - " not in teams_cell:
                        continue

                    # Split by " - " carefully
                    parts = teams_cell.split(" - ")
                    if len(parts) < 2:
                        continue

                    home = parts[0].strip()
                    away = " - ".join(parts[1:]).strip()  # In case away team has "-" in name

                    # Clean up team names (remove line breaks, extra spaces)
                    home = " ".join(home.split())
                    away = " ".join(away.split())

                    # Skip garbage
                    if not home or not away or len(home) < 3 or len(away) < 3:
                        continue

                    # Extract time from score cell (if available)
                    time_str = "TBD"
                    score_cell = cells[2].get_text().strip() if len(cells) > 2 else ""

                    # Try to find time in first cell (date/time)
                    date_cell = cells[0].get_text().strip() if len(cells) > 0 else ""
                    time_match = re.search(r"(\d{1,2}):(\d{2})", date_cell)
                    if time_match:
                        time_str = f"{time_match.group(1)}:{time_match.group(2)}"

                    match = {
                        "home": home,
                        "away": away,
                        "time": time_str,
                        "league": league_name,
                        "home_flag": "⚽",  # Default
                        "away_flag": "⚽",
                    }

                    # Set flags for known teams
                    for priority_team in PRIORITY_TEAMS:
                        if priority_team.lower() in home.lower():
                            match["home_flag"] = TEAM_FLAGS.get(priority_team, "⚽")
                        if priority_team.lower() in away.lower():
                            match["away_flag"] = TEAM_FLAGS.get(priority_team, "⚽")

                    matches.append(match)
                    logger.debug(f"[KULICHKI] {league_name}: {home} vs {away} at {time_str}")

                except Exception as e:
                    logger.debug(f"[KULICHKI] Parse error: {e}")
                    continue

    except Exception as e:
        logger.warning(f"[KULICHKI] Error parsing {league_name}: {e}")

    return matches
