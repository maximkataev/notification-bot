"""Parse football matches from football.kulichki.net."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime as dt, timedelta
try:
    from zoneinfo import ZoneInfo
    _TBILISI_TZ = ZoneInfo("Asia/Tbilisi")
except Exception:  # pragma: no cover - fallback if tzdata unavailable
    _TBILISI_TZ = None
import httpx
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


def _tbilisi_now() -> dt:
    """Current time in Tbilisi (naive), independent of server timezone (UTC).

    The digest is for a Tbilisi user, so "today"/"tomorrow"/"yesterday" and match
    times must be anchored to Asia/Tbilisi, not the server clock.
    """
    if _TBILISI_TZ is not None:
        return dt.now(_TBILISI_TZ).replace(tzinfo=None)
    # Fallback: Tbilisi is UTC+4 year-round
    return dt.utcnow() + timedelta(hours=4)

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
    current_year = _tbilisi_now().year
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
        today = _tbilisi_now()
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
        yesterday = _tbilisi_now() - timedelta(days=1)
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


def _parse_match_date(date_cell: str):
    """
    Parse a kulichki date cell into a datetime.date (current year).

    Handles "DD.MM" and "DD месяц" formats. Returns None if unparseable.
    Rolls over to next year if the parsed month is far in the past (Dec vs Jan).
    """
    try:
        from datetime import date as _date

        today = _tbilisi_now()
        date_text = date_cell.strip().lower()

        day = None
        month = None

        # Format 1: "DD.MM"
        dot_match = re.search(r"(\d{1,2})\.(\d{1,2})", date_text)
        if dot_match:
            day = int(dot_match.group(1))
            month = int(dot_match.group(2))
        else:
            # Format 2: "DD месяц"
            parts = date_text.split()
            if parts:
                try:
                    day = int(parts[0])
                except ValueError:
                    return None
                for month_name, month_num in RUSSIAN_MONTHS.items():
                    if month_name in date_text:
                        month = month_num
                        break

        if not day or not month or day > 31 or month > 12:
            return None

        year = today.year
        # Handle year rollover (e.g. parsing January while it's December)
        if month < today.month - 6:
            year += 1

        return _date(year, month, day)

    except Exception as e:
        logger.debug(f"[KULICHKI] Error parsing match date '{date_cell}': {e}")
        return None


def _convert_msk_to_tbilisi(time_str: str) -> str:
    """Convert HH:MM from Moscow time (UTC+3) to Tbilisi time (UTC+4, +1h)."""
    if time_str == "TBD":
        return time_str
    try:
        msk_hour, msk_minute = map(int, time_str.split(":"))
        tbilisi_hour = (msk_hour + 1) % 24
        return f"{tbilisi_hour:02d}:{msk_minute:02d}"
    except (ValueError, AttributeError):
        return time_str


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

                    # Skip 4xx errors (not found, etc) without retry
                    if 400 <= response.status_code < 500:
                        logger.debug(f"[KULICHKI] {league_name}: {response.status_code} Not Found")
                        continue

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

        # Apply display window: UPCOMING matches only — today's matches that have
        # NOT kicked off yet + tomorrow's night matches strictly BEFORE 08:00 Tbilisi.
        #
        # All times here are already Tbilisi (UTC+4); kulichki is Moscow (UTC+3) and
        # was converted in _parse_league_page. "now" is anchored to Tbilisi via
        # _tbilisi_now() so the server's UTC clock never leaks in. A match whose
        # kickoff is already in the past (e.g. a 06:00 night game when the digest is
        # built at 08:00) must NOT appear in the "upcoming matches" section.
        from datetime import timedelta as _timedelta
        now = _tbilisi_now()
        now_hhmm = now.strftime("%H:%M")
        today_iso = now.date().isoformat()
        tomorrow_iso = (now.date() + _timedelta(days=1)).isoformat()
        NIGHT_CUTOFF = "08:00"

        windowed_matches = []
        for match in all_matches:
            md = match.get("match_date")
            time_str = match.get("time", "TBD")

            if md == today_iso:
                # Drop matches that have already started today. Keep TBD (unknown
                # time) so we never silently lose a match with no listed time.
                if time_str == "TBD" or time_str >= now_hhmm:
                    windowed_matches.append(match)
                else:
                    logger.debug(f"[KULICHKI] Today match already kicked off (skip): {match['home']} vs {match['away']} at {time_str} (now {now_hhmm})")
            elif md == tomorrow_iso:
                # Only night games strictly before 08:00; skip TBD (unknown if night)
                if time_str != "TBD" and time_str < NIGHT_CUTOFF:
                    windowed_matches.append(match)
                else:
                    logger.debug(f"[KULICHKI] Tomorrow match outside night window: {match['home']} vs {match['away']} at {time_str}")

        if len(windowed_matches) < len(all_matches):
            logger.info(f"[KULICHKI] Window filter (today + tomorrow night <{NIGHT_CUTOFF}): {len(all_matches)} → {len(windowed_matches)}")
        all_matches = windowed_matches

        if not all_matches:
            logger.info("[KULICHKI] No matches in display window")
            return None

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
        yesterday = (_tbilisi_now() - timedelta(days=1)).strftime("%Y-%m-%d")
        logger.info(f"[KULICHKI] Fetching yesterday's results for {yesterday}")
        logger.debug(f"[KULICHKI] Priority teams: {PRIORITY_TEAMS}")

        all_matches = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for league_name, url in LEAGUE_URLS.items():
                logger.info(f"[KULICHKI] Fetching results {league_name} from {url}")

                try:
                    response = await client.get(url)

                    # Skip 4xx errors (not found, etc) without retry
                    if 400 <= response.status_code < 500:
                        logger.debug(f"[KULICHKI] {league_name}: {response.status_code} Not Found")
                        continue

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
    is_world_cup = "World Cup" in league_name

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
                    date_cell = cells[0].get_text().strip()

                    # Filter by yesterday's date
                    if not _is_yesterday(date_cell):
                        continue

                    if is_world_cup:
                        # World Cup layout: [Date] [Time] [Teams - Score] [Group]
                        teams_cell = " ".join(cells[2].get_text().split())

                        # Must contain a final score
                        score_match = re.search(r"-\s*(\d{1,2}):(\d{1,2})\s*$", teams_cell)
                        if not score_match:
                            continue
                        score = f"{score_match.group(1)}:{score_match.group(2)}"

                        # Teams are everything before the trailing score
                        teams_text = teams_cell[: score_match.start()].strip().rstrip("-").strip()
                        if " - " not in teams_text:
                            continue
                        tparts = teams_text.split(" - ")
                        home = " ".join(tparts[0].split())
                        away = " ".join(" - ".join(tparts[1:]).split())
                        halftime_score = None
                    else:
                        # League layout: [Date] [Teams] [Score] [Status]
                        teams_cell = cells[1].get_text().strip()
                        score_or_time = cells[2].get_text().strip() if len(cells) > 2 else ""

                        if not teams_cell or " - " not in teams_cell:
                            continue
                        if "тур" in teams_cell.lower() or "клуб" in teams_cell.lower():
                            continue

                        parts = teams_cell.split(" - ")
                        if len(parts) < 2:
                            continue
                        home = " ".join(parts[0].split())
                        away = " ".join(" - ".join(parts[1:]).split())

                        # Skip future matches (time format like "14:30")
                        if re.match(r"^\d{1,2}:\d{2}$", score_or_time):
                            continue

                        is_result_format = (
                            re.search(r"^\d{1,2}:\d{1,2}\s", score_or_time)
                            or re.search(r"^\d{1,2}:\d{1,2}$", score_or_time)
                            or re.search(r"\(\d+:\d+\)", score_or_time)
                        )
                        if not is_result_format:
                            continue

                        score = None
                        score_match = re.match(r"^(\d+):(\d+)", score_or_time)
                        if score_match:
                            score = f"{score_match.group(1)}:{score_match.group(2)}"

                        halftime_score = None
                        halftime_match = re.search(r"\((\d+):(\d+)\)", score_or_time)
                        if halftime_match:
                            halftime_score = f"{halftime_match.group(1)}:{halftime_match.group(2)}"

                        if not score:
                            continue

                    # Skip garbage
                    if not home or not away or len(home) < 3 or len(away) < 3:
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
    Parse upcoming matches from a kulichki.net page for today and tomorrow.

    Two distinct table layouts are handled:
      - League pages:    [Date] [Home - Away]   [Time/Result] [Status]
      - World Cup pages: [Date] [Time] [Home - Away (- Score)] [Group]

    Each returned match carries a "match_date" (ISO YYYY-MM-DD). Only matches
    dated today or tomorrow are returned; the caller applies the time window.
    Completed matches (with a score) are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    is_world_cup = "World Cup" in league_name

    from datetime import timedelta as _timedelta
    today = _tbilisi_now().date()
    tomorrow = today + _timedelta(days=1)

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
                    date_cell = cells[0].get_text().strip()

                    # Only keep today's and tomorrow's matches
                    match_date = _parse_match_date(date_cell)
                    if match_date not in (today, tomorrow):
                        continue

                    if is_world_cup:
                        # World Cup layout: [Date] [Time] [Teams (- Score)] [Group]
                        time_cell = cells[1].get_text().strip()
                        teams_cell = " ".join(cells[2].get_text().split())
                        group = None
                        if len(cells) > 3:
                            group_match = re.search(r"[Гг]руппа\s+([A-L])", cells[3].get_text())
                            if group_match:
                                group = f"Группа {group_match.group(1)}"

                        # Skip completed matches (score appended after teams)
                        if re.search(r"-\s*\d{1,2}:\d{1,2}\s*$", teams_cell):
                            logger.debug(f"[KULICHKI] {league_name}: skipping completed WC match: {teams_cell}")
                            continue

                        if " - " not in teams_cell:
                            continue
                        parts = teams_cell.split(" - ")
                        home = " ".join(parts[0].split())
                        away = " ".join(" - ".join(parts[1:]).split())

                        time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_cell)
                        time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else "TBD"
                    else:
                        # League layout: [Date] [Teams] [Time/Result] [Status]
                        teams_cell = cells[1].get_text().strip()
                        time_or_result = cells[2].get_text().strip() if len(cells) > 2 else ""
                        group = None

                        if not teams_cell or " - " not in teams_cell:
                            continue
                        if "тур" in teams_cell.lower() or "клуб" in teams_cell.lower():
                            continue

                        parts = teams_cell.split(" - ")
                        if len(parts) < 2:
                            continue
                        home = " ".join(parts[0].split())
                        away = " ".join(" - ".join(parts[1:]).split())

                        # Skip if team names contain a score (completed match)
                        if re.search(r"\d{1,2}:\d{1,2}$", away) or re.search(r"\d{1,2}:\d{1,2}$", home):
                            continue

                        is_time_format = bool(re.match(r"^\d{1,2}:\d{2}$", time_or_result))
                        is_result_format = (
                            re.search(r"^\d{1,2}:\d{1,2}\s", time_or_result)
                            or re.search(r"^\d{1,2}:\d{1,2}$", time_or_result)
                            or re.search(r"\(\d+:\d+\)", time_or_result)
                        )

                        # Skip completed matches (score, not time)
                        if re.search(r"\d{1,2}:\d{1,2}", time_or_result) and not is_time_format:
                            logger.debug(f"[KULICHKI] {league_name}: skipping completed: {home} vs {away} ({time_or_result})")
                            continue

                        time_str = "TBD"
                        if is_time_format:
                            time_str = time_or_result
                        else:
                            for cell in cells[2:]:
                                tm = re.search(r"(\d{1,2}):(\d{2})", cell.get_text().strip())
                                if tm:
                                    time_str = f"{tm.group(1)}:{tm.group(2)}"
                                    break

                    # Skip garbage team names
                    if not home or not away or len(home) < 3 or len(away) < 3:
                        continue

                    # Convert Moscow Time (UTC+3) to Tbilisi Time (UTC+4)
                    time_str = _convert_msk_to_tbilisi(time_str)

                    match = {
                        "home": home,
                        "away": away,
                        "time": time_str,
                        "match_date": match_date.isoformat(),
                        "league": league_name,
                        "home_flag": "⚽",
                        "away_flag": "⚽",
                    }
                    if group:
                        match["group"] = group

                    matches.append(match)
                    logger.debug(f"[KULICHKI] {league_name}: {home} vs {away} at {time_str} on {match_date}" + (f" ({group})" if group else ""))

                except Exception as e:
                    logger.debug(f"[KULICHKI] Parse error: {e}")
                    continue

    except Exception as e:
        logger.warning(f"[KULICHKI] Error parsing {league_name}: {e}")

    return matches
