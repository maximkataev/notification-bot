"""Parse football matches from football.kulichki.net."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime as dt, timedelta
import httpx
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)

# Russian month names to numbers
RUSSIAN_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Priority teams in exact order (Russian names as they appear on kulichki.net)
PRIORITY_TEAMS = ["Барселона", "Реал Мадрид", "Арсенал", "ПСЖ", "Атлетико", "Манчестер Сити", "Манчестер Юнайтед"]

# Team flags
TEAM_FLAGS = {
    "Барселона": "🇪🇸",
    "Реал Мадрид": "🇪🇸",
    "Атлетико": "🇪🇸",
    "Арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер Сити": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер Юнайтед": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "ПСЖ": "🇫🇷",
}

# Generate dynamic league URLs based on current year
def _get_league_urls() -> Dict[str, str]:
    """
    Generate league URLs with dynamic years for cups and world tournaments.
    For regular seasons (La Liga, Premier League, Ligue 1) use base URL.
    For cups and international, check current and next year.
    """
    current_year = dt.now().year
    next_year = current_year + 1

    urls = {
        # Regular league seasons
        "La Liga": "https://football.kulichki.net/spain/",
        "Premier League": "https://football.kulichki.net/england/",
        "Ligue 1": "https://football.kulichki.net/france/",

        # European competitions
        "UEFA Cup": "https://football.kulichki.net/uefa_cup/",
        "Champions League": "https://football.kulichki.net/league/",  # European league matches

        # World Cup (check multiple years)
        f"World Cup {current_year}": f"https://football.kulichki.net/world/{current_year}/",
        f"World Cup {next_year}": f"https://football.kulichki.net/world/{next_year}/",

        # National cups (check multiple years)
        f"Copa del Rey {current_year}": f"https://football.kulichki.net/spain/{current_year}/cup/",
        f"Copa del Rey {next_year}": f"https://football.kulichki.net/spain/{next_year}/cup/",
        f"FA Cup {current_year}": f"https://football.kulichki.net/england/{current_year}/cup/",
        f"FA Cup {next_year}": f"https://football.kulichki.net/england/{next_year}/cup/",
        f"Coupe de France {current_year}": f"https://football.kulichki.net/france/{current_year}/cup/",
        f"Coupe de France {next_year}": f"https://football.kulichki.net/france/{next_year}/cup/",
    }
    return urls

# Initialize URLs on module load
LEAGUE_URLS = _get_league_urls()


def _is_today(date_cell: str) -> bool:
    """
    Check if date_cell contains today's date in various formats:
    - "14 мая" (day month in Russian)
    - "14.05" (DD.MM format)
    - "30 мая" with teams/time mixed in

    Returns True only if date matches today's date (day and month).
    """
    try:
        today = dt.now()
        today_day = today.day
        today_month = today.month

        date_text = date_cell.strip().lower()
        logger.debug(f"[KULICHKI] Parsing date: '{date_text}' (today: {today_day}.{today_month:02d})")

        # Format 1: "DD.MM" (e.g., "05.05" or "30.05")
        dot_match = re.search(r"(\d{1,2})\.(\d{1,2})", date_text)
        if dot_match:
            day = int(dot_match.group(1))
            month = int(dot_match.group(2))
            is_match = day == today_day and month == today_month
            logger.debug(f"[KULICHKI]   Format DD.MM: day={day}, month={month} → {is_match}")
            return is_match

        # Format 2: "DD месяц" (e.g., "14 мая", "30 мая")
        parts = date_text.split()
        if len(parts) >= 1:
            try:
                day = int(parts[0])

                # Look for Russian month name in the entire text
                month = None
                for month_name, month_num in RUSSIAN_MONTHS.items():
                    if month_name in date_text:
                        month = month_num
                        break

                if month is not None:
                    is_match = day == today_day and month == today_month
                    logger.debug(f"[KULICHKI]   Format DD месяц: day={day}, month={month} → {is_match}")
                    return is_match
                else:
                    # Only day found, no month - can't determine
                    logger.debug(f"[KULICHKI]   No month found, only day={day}")
                    return False

            except ValueError:
                pass

        logger.debug(f"[KULICHKI]   Could not parse date from: '{date_text}'")
        return False

    except Exception as e:
        logger.debug(f"[KULICHKI] Error parsing date '{date_cell}': {e}")
        return False


def _is_yesterday(date_cell: str) -> bool:
    """
    Check if date_cell contains yesterday's date in various formats.
    Returns True only if date matches yesterday's date (day and month).
    """
    try:
        yesterday = dt.now() - timedelta(days=1)
        yesterday_day = yesterday.day
        yesterday_month = yesterday.month

        date_text = date_cell.strip().lower()
        logger.debug(f"[KULICHKI] Parsing yesterday date: '{date_text}' (yesterday: {yesterday_day}.{yesterday_month:02d})")

        # Format 1: "DD.MM" (e.g., "05.05" or "30.05")
        dot_match = re.search(r"(\d{1,2})\.(\d{1,2})", date_text)
        if dot_match:
            day = int(dot_match.group(1))
            month = int(dot_match.group(2))
            is_match = day == yesterday_day and month == yesterday_month
            logger.debug(f"[KULICHKI]   Format DD.MM: day={day}, month={month} → {is_match}")
            return is_match

        # Format 2: "DD месяц" (e.g., "14 мая", "30 мая")
        parts = date_text.split()
        if len(parts) >= 1:
            try:
                day = int(parts[0])

                # Look for Russian month name in the entire text
                month = None
                for month_name, month_num in RUSSIAN_MONTHS.items():
                    if month_name in date_text:
                        month = month_num
                        break

                if month is not None:
                    is_match = day == yesterday_day and month == yesterday_month
                    logger.debug(f"[KULICHKI]   Format DD месяц: day={day}, month={month} → {is_match}")
                    return is_match
                else:
                    logger.debug(f"[KULICHKI]   No month found, only day={day}")
                    return False

            except ValueError:
                pass

        logger.debug(f"[KULICHKI]   Could not parse yesterday date from: '{date_text}'")
        return False

    except Exception as e:
        logger.debug(f"[KULICHKI] Error parsing yesterday date '{date_cell}': {e}")
        return False


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

        # Deduplicate matches (same home/away/league/time)
        seen = set()
        unique_matches = []
        for match in all_matches:
            key = (match["home"], match["away"], match["league"], match["time"])
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)

        if len(unique_matches) < len(all_matches):
            logger.info(f"[KULICHKI] Deduplicated: {len(all_matches)} → {len(unique_matches)}")
            all_matches = unique_matches

        # Filter out past matches (time in future)
        from datetime import datetime as dt
        now_time = dt.now().strftime("%H:%M")
        future_matches = []

        for match in all_matches:
            if match["time"] == "TBD":
                # Keep matches with unknown time, but check for hidden scores in team names
                # (completed matches may have score embedded in away team name)
                home = match.get("home", "")
                away = match.get("away", "")

                # Skip if team names contain score patterns (shouldn't happen, but be defensive)
                if re.search(r"\d{1,2}:\d{1,2}$", away) or re.search(r"\d{1,2}:\d{1,2}$", home):
                    logger.debug(f"[KULICHKI] Filtering out TBD match with embedded score: {home} vs {away}")
                    continue

                future_matches.append(match)
            else:
                try:
                    match_time = match["time"]
                    # Simple time comparison (assumes same day)
                    if match_time >= now_time:
                        future_matches.append(match)
                    else:
                        logger.debug(f"[KULICHKI] Filtering out past match: {match['home']} vs {match['away']} at {match['time']}")
                except Exception as e:
                    logger.debug(f"[KULICHKI] Error filtering by time: {e}, keeping match")
                    future_matches.append(match)

        if len(future_matches) < len(all_matches):
            logger.info(f"[KULICHKI] Filtered past matches: {len(all_matches)} → {len(future_matches)}")
            all_matches = future_matches

        # Separate World Cup matches from regular league matches
        world_cup_matches = [m for m in all_matches if "World Cup" in m.get("league", "")]
        league_matches = [m for m in all_matches if "World Cup" not in m.get("league", "")]

        logger.info(f"[KULICHKI] World Cup matches: {len(world_cup_matches)}, League matches: {len(league_matches)}")

        # For World Cup: return all matches (no priority filter)
        if world_cup_matches:
            logger.info(f"[KULICHKI] ✓ Returning all {len(world_cup_matches)} World Cup match(es)")
            for m in world_cup_matches:
                logger.debug(f"[KULICHKI]   - {m['home']} vs {m['away']}")
            return world_cup_matches

        # For regular leagues: filter to priority teams (fuzzy matching)
        priority_matches = []
        for match in league_matches:
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

        logger.info(f"[KULICHKI] League priority matches: {len(priority_matches)}")

        # Sort by priority and take top 3
        priority_matches.sort(key=lambda m: m.get("priority_idx", 999))

        return priority_matches[:3] if priority_matches else None

    except Exception as e:
        logger.warning(f"[KULICHKI] Failed: {type(e).__name__}: {e}")
        return None


async def get_yesterday_results_from_kulichki() -> Optional[List[Dict[str, Any]]]:
    """
    Parse yesterday's completed football matches from football.kulichki.net.
    Returns up to 3 matches for priority teams.
    """
    try:
        yesterday = (dt.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"[KULICHKI] Fetching yesterday's results for {yesterday}")
        logger.debug(f"[KULICHKI] Priority teams: {PRIORITY_TEAMS}")

        all_matches = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for league_name, url in LEAGUE_URLS.items():
                logger.info(f"[KULICHKI] Fetching results {league_name} from {url}")

                try:
                    response = await client.get(url)
                    response.raise_for_status()

                    matches = _parse_league_page_for_results(response.text, league_name)
                    standings = _parse_standings_table(response.text, league_name)

                    logger.info(f"[KULICHKI] {league_name}: found {len(matches)} results, standings: {len(standings) if standings else 0} teams")

                    # Attach standings to matches from this league
                    for match in matches:
                        match["standings"] = standings

                    all_matches.extend(matches)

                except Exception as e:
                    logger.warning(f"[KULICHKI] Failed to fetch {league_name} results: {e}")
                    continue

        if not all_matches:
            logger.info(f"[KULICHKI] No results found for yesterday")
            return None

        logger.info(f"[KULICHKI] Total results: {len(all_matches)}")

        # Deduplicate matches (same home/away/league/score)
        seen = set()
        unique_matches = []
        for match in all_matches:
            key = (match["home"], match["away"], match["league"], match["score"])
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)

        if len(unique_matches) < len(all_matches):
            logger.info(f"[KULICHKI] Deduplicated results: {len(all_matches)} → {len(unique_matches)}")
            all_matches = unique_matches

        # Separate World Cup matches from regular league matches
        world_cup_matches = [m for m in all_matches if "World Cup" in m.get("league", "")]
        league_matches = [m for m in all_matches if "World Cup" not in m.get("league", "")]

        logger.info(f"[KULICHKI] World Cup results: {len(world_cup_matches)}, League results: {len(league_matches)}")

        # For World Cup: return all matches (no priority filter)
        if world_cup_matches:
            logger.info(f"[KULICHKI] ✓ Returning all {len(world_cup_matches)} World Cup result(s)")
            for m in world_cup_matches:
                logger.debug(f"[KULICHKI]   - {m['home']} vs {m['away']} ({m['score']})")
            return world_cup_matches

        # For regular leagues: filter to priority teams (fuzzy matching)
        priority_matches = []
        for match in league_matches:
            home = match["home"]
            away = match["away"]

            for priority_team in PRIORITY_TEAMS:
                if priority_team.lower() in home.lower():
                    match["priority_idx"] = PRIORITY_TEAMS.index(priority_team)
                    priority_matches.append(match)
                    logger.debug(f"[KULICHKI] Priority result: {home} vs {away} ({match['score']})")
                    break
                elif priority_team.lower() in away.lower():
                    match["priority_idx"] = PRIORITY_TEAMS.index(priority_team)
                    priority_matches.append(match)
                    logger.debug(f"[KULICHKI] Priority result: {home} vs {away} ({match['score']})")
                    break

        logger.info(f"[KULICHKI] League priority results: {len(priority_matches)}")

        # Sort by priority and take top 3
        priority_matches.sort(key=lambda m: m.get("priority_idx", 999))

        return priority_matches[:3] if priority_matches else None

    except Exception as e:
        logger.warning(f"[KULICHKI] Failed to get yesterday results: {type(e).__name__}: {e}")
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


def _parse_league_page_for_results(html: str, league_name: str) -> List[Dict[str, Any]]:
    """
    Parse completed matches from yesterday from kulichki.net league page HTML.
    Structure: [Date] [Home - Away] [Score] [Status]
    Returns only completed matches from yesterday (score in X:Y format)
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []

    try:
        tables = soup.find_all("table")
        logger.debug(f"[KULICHKI] {league_name}: {len(tables)} tables for results parsing")

        for table in tables:
            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all("td")

                # Skip rows with too few cells (headers, spacers)
                if len(cells) < 3:
                    continue

                try:
                    # Structure: [Date] [Teams] [Score] [Status]
                    date_cell = cells[0].get_text().strip()
                    teams_cell = cells[1].get_text().strip()
                    score_or_time = cells[2].get_text().strip() if len(cells) > 2 else ""

                    # Filter by yesterday's date
                    if not _is_yesterday(date_cell):
                        logger.debug(f"[KULICHKI] {league_name}: Skipping non-yesterday date: {date_cell}")
                        continue

                    # Skip header/empty rows
                    if not teams_cell or " - " not in teams_cell:
                        continue
                    if "тур" in teams_cell.lower() or "клуб" in teams_cell.lower():
                        continue

                    # Parse teams from "Home - Away" format
                    parts = teams_cell.split(" - ")
                    if len(parts) < 2:
                        continue

                    home = parts[0].strip()
                    away = " - ".join(parts[1:]).strip()

                    # Clean up team names
                    home = " ".join(home.split())
                    away = " ".join(away.split())

                    # Skip garbage
                    if not home or not away or len(home) < 3 or len(away) < 3:
                        continue

                    # Check if this is a completed match (score format) or future match (time format)
                    is_time_format = re.match(r"^\d{1,2}:\d{2}$", score_or_time) and ":" in score_or_time

                    # Skip future matches (time format like "14:30")
                    if is_time_format:
                        logger.debug(f"[KULICHKI] {league_name}: Skipping future match: {home} vs {away} at {score_or_time}")
                        continue

                    # Check if it looks like a score (digits:digits format with optional halftime score)
                    # Score formats: "1:0", "2:1", "1:0 (1:0)", "2:1(1:0)"
                    is_result_format = (
                        re.search(r"^\d{1,2}:\d{1,2}\s", score_or_time) or  # "1:0 " format
                        re.search(r"^\d{1,2}:\d{1,2}$", score_or_time) or   # "1:0" format
                        re.search(r"\(\d+:\d+\)", score_or_time)             # "X:Y (A:B)" format
                    )

                    # Skip if doesn't look like a result
                    if not is_result_format:
                        logger.debug(f"[KULICHKI] {league_name}: Skipping non-result format: {home} vs {away} ({score_or_time})")
                        continue

                    # Extract score and halftime score
                    score = None
                    halftime_score = None

                    score_match = re.match(r"^(\d+):(\d+)", score_or_time)
                    if score_match:
                        score = f"{score_match.group(1)}:{score_match.group(2)}"

                    halftime_match = re.search(r"\((\d+):(\d+)\)", score_or_time)
                    if halftime_match:
                        halftime_score = f"{halftime_match.group(1)}:{halftime_match.group(2)}"

                    if not score:
                        logger.debug(f"[KULICHKI] {league_name}: Could not extract score from: {score_or_time}")
                        continue

                    match = {
                        "home": home,
                        "away": away,
                        "score": score,
                        "halftime_score": halftime_score,
                        "league": league_name,
                        "home_flag": "⚽",
                        "away_flag": "⚽",
                    }

                    matches.append(match)
                    logger.debug(f"[KULICHKI] {league_name}: {home} vs {away} ({score})")

                except Exception as e:
                    logger.debug(f"[KULICHKI] Parse error: {e}")
                    continue

    except Exception as e:
        logger.warning(f"[KULICHKI] Error parsing {league_name} results: {e}")

    return matches


def _parse_league_page(html: str, league_name: str) -> List[Dict[str, Any]]:
    """
    Parse matches from kulichki.net league page HTML.
    Structure: [Date] [Home - Away] [Time/Result] [Status]
    Returns only future matches (time in HH:MM format, not score format X:Y)
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

                # Skip rows with too few cells (headers, spacers)
                if len(cells) < 3:
                    continue

                try:
                    # Structure: [Date] [Teams] [Time/Result] [Status]
                    # Cell 0: Date like "14 мая"
                    # Cell 1: Teams like "Реал Мадрид - Овьедо"
                    # Cell 2: Time like "22:30" or Result like "1:0 (1:0)"
                    # Cell 3+: Status like "Онлайн"

                    date_cell = cells[0].get_text().strip()
                    teams_cell = cells[1].get_text().strip()
                    time_or_result = cells[2].get_text().strip() if len(cells) > 2 else ""

                    # Filter by today's date (strict check - must match day and month)
                    if not _is_today(date_cell):
                        logger.debug(f"[KULICHKI] {league_name}: Skipping non-today date: {date_cell}")
                        continue

                    # Skip header/empty rows
                    if not teams_cell or " - " not in teams_cell:
                        continue
                    if "тур" in teams_cell.lower() or "клуб" in teams_cell.lower():
                        continue

                    # Parse teams from "Home - Away" format
                    parts = teams_cell.split(" - ")
                    if len(parts) < 2:
                        continue

                    home = parts[0].strip()
                    away = " - ".join(parts[1:]).strip()

                    # Clean up team names (remove line breaks, tabs, extra spaces)
                    home = " ".join(home.split())
                    away = " ".join(away.split())

                    # Skip garbage
                    if not home or not away or len(home) < 3 or len(away) < 3:
                        continue

                    # Skip if team names contain score format (e.g., "Team - 1:2" or "Team 4:3")
                    # This indicates a completed match incorrectly parsed
                    if re.search(r"\d{1,2}:\d{1,2}$", away) or re.search(r"\d{1,2}:\d{1,2}$", home):
                        logger.debug(f"[KULICHKI] {league_name}: Skipping match with score in team name: {home} vs {away}")
                        continue
                    if re.search(r"\s-\s\d{1,2}:\d{1,2}$", away) or re.search(r"\s-\s\d{1,2}:\d{1,2}$", home):
                        logger.debug(f"[KULICHKI] {league_name}: Skipping match with score in name: {home} vs {away}")
                        continue

                    # Distinguish future matches from completed matches
                    # Future: "22:30" format (HH:MM with 2 digits for minutes)
                    # Completed: "1:0" or "1:0 (1:0)" format (score format - usually 1 digit:1 digit or with halftime)
                    time_str = "TBD"

                    # Check if this is time format (HH:MM) vs result format (X:Y)
                    # Time: must have HH:MM with exactly 2 minute digits
                    is_time_format = re.match(r"^\d{1,2}:\d{2}$", time_or_result) and ":" in time_or_result

                    # Result formats: "1:0", "2:1", "1:0 (1:0)", etc - usually single/double digit scores
                    # Check if it looks like a score (digits:digits without leading zero in hours part that would suggest HH:MM)
                    is_result_format = (
                        re.search(r"^\d{1,2}:\d{1,2}\s", time_or_result) or  # "1:0 " format
                        re.search(r"^\d{1,2}:\d{1,2}$", time_or_result) or   # "1:0" format
                        re.search(r"\(\d+:\d+\)", time_or_result)             # "X:Y (A:B)" format
                    )

                    # Skip completed matches
                    if is_result_format and not is_time_format:
                        logger.debug(f"[KULICHKI] {league_name}: Skipping completed: {home} vs {away} ({time_or_result})")
                        continue

                    # Also skip if time_or_result looks like ANY score format, even if we couldn't extract time
                    if re.search(r"\d{1,2}:\d{1,2}", time_or_result) and not is_time_format:
                        logger.debug(f"[KULICHKI] {league_name}: Skipping match with score format: {home} vs {away} ({time_or_result})")
                        continue

                    # Extract time from time_or_result or other cells
                    # Note: kulichki.net uses Moscow Time (UTC+3), convert to Tbilisi (UTC+4) = +1 hour
                    if is_time_format:
                        time_str = time_or_result
                    else:
                        # Try to find time in this cell or others
                        time_match = re.search(r"(\d{1,2}):(\d{2})", time_or_result)
                        if time_match:
                            time_str = f"{time_match.group(1)}:{time_match.group(2)}"
                        else:
                            # Try other cells
                            for cell in cells[3:]:
                                cell_text = cell.get_text().strip()
                                time_match = re.search(r"(\d{1,2}):(\d{2})", cell_text)
                                if time_match:
                                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"
                                    break

                    # Convert from Moscow Time (UTC+3) to Tbilisi Time (UTC+4)
                    if time_str != "TBD":
                        try:
                            msk_hour, msk_minute = map(int, time_str.split(":"))
                            tbilisi_hour = (msk_hour + 1) % 24  # +1 hour for timezone conversion
                            time_str = f"{tbilisi_hour:02d}:{msk_minute:02d}"
                        except (ValueError, AttributeError):
                            pass  # Keep original if conversion fails

                    match = {
                        "home": home,
                        "away": away,
                        "time": time_str,
                        "league": league_name,
                        "home_flag": "⚽",
                        "away_flag": "⚽",
                    }

                    matches.append(match)
                    logger.debug(f"[KULICHKI] {league_name}: {home} vs {away} at {time_str}")

                except Exception as e:
                    logger.debug(f"[KULICHKI] Parse error: {e}")
                    continue

    except Exception as e:
        logger.warning(f"[KULICHKI] Error parsing {league_name}: {e}")

    return matches
