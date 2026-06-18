"""Parse football matches from football.kulichki.net."""

import asyncio
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

# kulichki.net is the sole football source. Header-less requests from datacenter IPs
# can get anti-bot / empty / stale responses (the parser then silently shows nothing),
# so mirror content_parser.py and always send a real browser User-Agent. A single retry
# absorbs transient hiccups before we give up on a league page.
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ru,en;q=0.9",
}


async def _fetch_league_page(client: "httpx.AsyncClient", url: str) -> "Optional[httpx.Response]":
    """GET a kulichki league page with one retry. Returns None on 4xx or repeated failure.

    Logs response diagnostics (status, byte size, detected encoding, retry attempts) so
    production failures — where the server gets a different/empty page than we do locally —
    are visible in the digest logs instead of silently parsing to zero matches.
    """
    last_exc = None
    for attempt in range(2):
        tag = f"attempt {attempt + 1}/2"
        try:
            response = await client.get(url)
            size = len(response.content)
            logger.info(
                f"[KULICHKI] GET {url} → HTTP {response.status_code}, {size} bytes, "
                f"encoding={response.encoding}, content-type={response.headers.get('content-type')} ({tag})"
            )
            # 4xx (not found, etc) won't change on retry — give up immediately.
            if 400 <= response.status_code < 500:
                return response
            response.raise_for_status()
            # A 200 that's suspiciously small is almost certainly an anti-bot / error
            # interstitial rather than a real league page — flag it loudly.
            if size < 2000:
                logger.warning(
                    f"[KULICHKI] ⚠️  Suspiciously small page from {url}: {size} bytes "
                    f"(likely anti-bot/error page, not real content)"
                )
            return response
        except Exception as e:  # noqa: BLE001 - transient network/5xx, retry once
            last_exc = e
            logger.warning(
                f"[KULICHKI] GET {url} failed ({tag}): {type(e).__name__}: {str(e)[:120]}"
            )
            if attempt == 0:
                await asyncio.sleep(1.0)
    if last_exc is not None:
        raise last_exc
    return None


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


def _tbilisi_kickoff(match_date, msk_time_str: str):
    """Build the full Tbilisi kickoff datetime from a match date + Moscow time.

    kulichki lists Moscow time (UTC+3); Tbilisi is UTC+4. Adding the hour can roll
    the date over (e.g. 23:30 MSK → 00:30 next day Tbilisi), which a plain HH:MM
    string conversion silently loses — that is why a "tomorrow 00:00" game was really
    the night *after* tomorrow. Returning a real datetime lets the caller apply an
    exact rolling 24h window and sort chronologically across the midnight boundary.

    Returns a naive Tbilisi datetime, or None when the time is unknown (TBD).
    """
    if not match_date or not msk_time_str or msk_time_str == "TBD":
        return None
    try:
        hour, minute = map(int, msk_time_str.split(":"))
    except (ValueError, AttributeError):
        return None
    msk_dt = dt(match_date.year, match_date.month, match_date.day, hour, minute)
    return msk_dt + timedelta(hours=1)


def _kickoff_sort_key(match: Dict[str, Any]) -> str:
    """Sort key for chronological (earliest-first) match ordering.

    Uses the ISO kickoff datetime so a 00:30 game tomorrow correctly sorts AFTER a
    23:00 game today (a plain HH:MM compare would wrongly put 00:30 first). Matches
    with an unknown kickoff (TBD) sort last.
    """
    return match.get("kickoff") or "9999-12-31T23:59"


async def get_today_matches_from_kulichki() -> Optional[List[Dict[str, Any]]]:
    """
    Parse today's football matches from football.kulichki.net.
    Returns up to 3 matches for priority teams with standings context.
    """
    try:
        logger.info(f"[KULICHKI] Fetching matches")

        all_matches = []

        async with httpx.AsyncClient(timeout=15.0, headers=_BROWSER_HEADERS, follow_redirects=True) as client:
            for league_name, url in LEAGUE_URLS.items():
                logger.info(f"[KULICHKI] Fetching {league_name} from {url}")

                try:
                    response = await _fetch_league_page(client, url)

                    # Skip 4xx errors (not found, etc) without retry
                    if response is None or 400 <= response.status_code < 500:
                        logger.debug(f"[KULICHKI] {league_name}: not available ({getattr(response, 'status_code', 'no response')})")
                        continue

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

        # Apply the UPCOMING window: kickoff in the next 24h from the digest prep time.
        #
        # "now" is anchored to Tbilisi via _tbilisi_now() (the server runs UTC), and
        # every match carries a real Tbilisi "kickoff" datetime (rolled across midnight
        # in _parse_league_page). So:
        #   - a game that already started (e.g. 06:00 night game, prep at 08:00) → past → skip
        #   - a genuine "day after next" 00:00 game (a 23:xx MSK game that rolled past
        #     midnight) has kickoff > now+24h → skip; it belongs in tomorrow's digest
        # A TBD (unknown time) match is kept only if it is listed for today, so we never
        # silently lose a match that simply has no published kickoff time.
        from datetime import timedelta as _timedelta
        now = _tbilisi_now()
        window_end = now + _timedelta(hours=24)
        today_iso = now.date().isoformat()

        windowed_matches = []
        for match in all_matches:
            kickoff_iso = match.get("kickoff")
            if kickoff_iso:
                kickoff = dt.fromisoformat(kickoff_iso)
                if now <= kickoff < window_end:
                    windowed_matches.append(match)
                else:
                    logger.debug(f"[KULICHKI] Match outside next-24h window (skip): {match['home']} vs {match['away']} at {kickoff} (now {now})")
            elif match.get("match_date") == today_iso:
                windowed_matches.append(match)
            else:
                logger.debug(f"[KULICHKI] TBD match not today (skip): {match['home']} vs {match['away']}")

        if len(windowed_matches) < len(all_matches):
            logger.info(f"[KULICHKI] Window filter (next 24h from {now:%Y-%m-%d %H:%M}): {len(all_matches)} → {len(windowed_matches)}")
        all_matches = windowed_matches

        if not all_matches:
            logger.info("[KULICHKI] No matches in display window")
            return None

        # Separate World Cup matches from regular league matches
        world_cup_matches = [m for m in all_matches if "World Cup" in m.get("league", "")]
        league_matches = [m for m in all_matches if "World Cup" not in m.get("league", "")]

        logger.info(f"[KULICHKI] World Cup matches: {len(world_cup_matches)}, League matches: {len(league_matches)}")

        # For World Cup: return all matches (no priority filter), earliest kickoff first
        if world_cup_matches:
            world_cup_matches.sort(key=_kickoff_sort_key)
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

        # Pick the 3 most important by priority, then display them earliest-first.
        priority_matches.sort(key=lambda m: m.get("priority_idx", 999))
        top = priority_matches[:3]
        top.sort(key=_kickoff_sort_key)

        return top if top else None

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

        async with httpx.AsyncClient(timeout=15.0, headers=_BROWSER_HEADERS, follow_redirects=True) as client:
            for league_name, url in LEAGUE_URLS.items():
                logger.info(f"[KULICHKI] Fetching results {league_name} from {url}")

                try:
                    response = await _fetch_league_page(client, url)

                    # Skip 4xx errors (not found, etc) without retry
                    if response is None or 400 <= response.status_code < 500:
                        logger.debug(f"[KULICHKI] {league_name}: not available ({getattr(response, 'status_code', 'no response')})")
                        continue

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

        # Trailing 24h window: keep matches that kicked off within the last 24h from the
        # digest prep time. When a kickoff time is known (World Cup results carry one) we
        # apply the cutoff exactly; league results have no published time, so we keep them
        # (they are already constrained to yesterday/today by the parser).
        now = _tbilisi_now()
        window_start = now - timedelta(hours=24)
        windowed = []
        for match in all_matches:
            kickoff_iso = match.get("kickoff")
            if kickoff_iso:
                kickoff = dt.fromisoformat(kickoff_iso)
                if window_start <= kickoff < now:
                    windowed.append(match)
                else:
                    logger.debug(f"[KULICHKI] Result outside last-24h window (skip): {match['home']} vs {match['away']} at {kickoff}")
            else:
                windowed.append(match)
        if len(windowed) < len(all_matches):
            logger.info(f"[KULICHKI] Result window filter (last 24h from {now:%Y-%m-%d %H:%M}): {len(all_matches)} → {len(windowed)}")
        all_matches = windowed

        if not all_matches:
            logger.info("[KULICHKI] No results in last-24h window")
            return None

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
    Parse recently-completed matches from kulichki.net league page HTML.
    Structure: [Date] [Home - Away] [Score] [Status]

    Returns completed matches (score in X:Y) dated YESTERDAY or TODAY. Today's already
    finished games (e.g. a 02:00 night match) must be included so the "past results"
    section covers the full trailing 24h, not just the calendar yesterday — the caller
    applies the precise 24h cutoff using each match's kickoff (when a time is available).
    """
    soup = BeautifulSoup(html, "html.parser")
    matches = []
    is_world_cup = "World Cup" in league_name

    from datetime import timedelta as _timedelta
    today = _tbilisi_now().date()
    yesterday = today - _timedelta(days=1)

    # Diagnostic counters (mirror _parse_league_page) so an empty results list can be
    # traced to a stage rather than guessed at.
    stats = {"rows": 0, "cells_ok": 0, "date_parsed": 0, "in_window": 0}

    try:
        tables = soup.find_all("table")
        logger.info(f"[KULICHKI] {league_name}: parsing {len(tables)} tables for results (yesterday={yesterday}, today={today})")

        for table in tables:
            rows = table.find_all("tr")

            for row in rows:
                stats["rows"] += 1
                cells = row.find_all("td")

                # Skip rows with too few cells (headers, spacers)
                if len(cells) < 3:
                    continue
                stats["cells_ok"] += 1

                try:
                    date_cell = cells[0].get_text().strip()

                    # Keep yesterday's and today's matches (trailing 24h candidates)
                    match_date = _parse_match_date(date_cell)
                    if match_date is not None:
                        stats["date_parsed"] += 1
                    if match_date not in (yesterday, today):
                        continue
                    stats["in_window"] += 1

                    kickoff = None
                    if is_world_cup:
                        # World Cup layout: [Date] [Time] [Teams - Score] [Group]
                        time_cell = cells[1].get_text().strip()
                        time_match = re.match(r"^(\d{1,2}):(\d{2})$", time_cell)
                        if time_match:
                            kickoff = _tbilisi_kickoff(
                                match_date, f"{time_match.group(1)}:{time_match.group(2)}"
                            )

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
                        "match_date": match_date.isoformat(),
                        "kickoff": kickoff.isoformat() if kickoff else None,
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

    logger.info(
        f"[KULICHKI] {league_name} results funnel: rows={stats['rows']} → "
        f"≥3cells={stats['cells_ok']} → date-parsed={stats['date_parsed']} → "
        f"yesterday/today={stats['in_window']} → results={len(matches)}"
    )
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

    # Diagnostic counters: trace how rows are filtered out so a "0 matches" result
    # in production can be attributed to a stage (no tables / no dated rows / all
    # outside today-tomorrow / all already-completed) rather than guessed at.
    stats = {"rows": 0, "cells_ok": 0, "date_parsed": 0, "in_window": 0, "completed": 0}

    try:
        tables = soup.find_all("table")
        logger.info(f"[KULICHKI] {league_name}: parsing {len(tables)} tables for upcoming matches (today={today}, tomorrow={tomorrow})")

        for table in tables:
            rows = table.find_all("tr")

            for row in rows:
                stats["rows"] += 1
                cells = row.find_all("td")

                # Skip rows with too few cells (headers, spacers)
                if len(cells) < 3:
                    continue
                stats["cells_ok"] += 1

                try:
                    date_cell = cells[0].get_text().strip()

                    # Only keep today's and tomorrow's matches
                    match_date = _parse_match_date(date_cell)
                    if match_date is not None:
                        stats["date_parsed"] += 1
                    if match_date not in (today, tomorrow):
                        continue
                    stats["in_window"] += 1

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
                            stats["completed"] += 1
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
                            stats["completed"] += 1
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

                    # Build the full Tbilisi kickoff datetime from the Moscow date+time.
                    # This rolls the date across midnight (23:xx MSK → 00:xx next day),
                    # so match_date/time below are the real Tbilisi values, not the
                    # Moscow-day label. kickoff drives the 24h window and time sort.
                    kickoff = _tbilisi_kickoff(match_date, time_str)
                    if kickoff is not None:
                        tb_date = kickoff.date()
                        time_str = kickoff.strftime("%H:%M")
                    else:
                        tb_date = match_date  # unknown time (TBD), keep the listed date

                    match = {
                        "home": home,
                        "away": away,
                        "time": time_str,
                        "match_date": tb_date.isoformat(),
                        "kickoff": kickoff.isoformat() if kickoff else None,
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

    # Funnel summary: when matches is empty this pinpoints WHERE rows were lost.
    logger.info(
        f"[KULICHKI] {league_name} upcoming funnel: rows={stats['rows']} → "
        f"≥3cells={stats['cells_ok']} → date-parsed={stats['date_parsed']} → "
        f"today/tomorrow={stats['in_window']} (completed-skipped={stats['completed']}) "
        f"→ matches={len(matches)}"
    )
    return matches
