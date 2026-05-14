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
    Returns up to 3 matches for priority teams.
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
                    logger.info(f"[KULICHKI] {league_name}: found {len(matches)} matches")
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
