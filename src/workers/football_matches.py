"""Fetch football matches for priority teams today via kulichki.net parser."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from html import unescape
import re
import feedparser
import httpx
from src.utils.openai_client import get_client
from src.workers.kulichki_parser import get_today_matches_from_kulichki, get_yesterday_results_from_kulichki

logger = logging.getLogger(__name__)

# Sport RSS feeds (from news_fetcher.py)
SPORTS_FEEDS = [
    # Premium football sources
    "https://feeds.bbci.co.uk/sport/rss.xml",  # BBC Sport
    "https://www.espn.com/espn/rss/news",  # ESPN
    "https://www.eurosport.com/rss/eurosport_rss_news.xml",  # Eurosport
    "https://www.goal.com/feeds/news",  # Goal.com (football)
    "https://feeds.sky.com/feed/sports/football",  # Sky Sports Football

    # La Liga, Premier League specific
    "https://www.marca.com/rss/futbol/",  # Marca (Spanish football)
    "https://www.as.com/rss/futbol/",  # AS.com (Spanish sports)
    "https://www.mundodeportivo.com/feed.xml",  # Mundo Deportivo (La Liga)
    "https://feeds.theguardian.com/theguardian/sport/football/rss",  # Guardian Football

    # Additional European coverage
    "https://www.football-italia.net/rss.xml",  # Serie A
    "https://www.sport1.de/fussball/rss.xml",  # Sport1 (Bundesliga)
    "https://www.l1.fr/rss.xml",  # Ligue 1 official
    "https://www.football-esp.com/feed",  # Spanish football focus
]

# Country translations: Russian name → English name for World Cup matches
COUNTRY_TRANSLATIONS = {
    "Испания": "Spain",
    "Франция": "France",
    "Англия": "England",
    "Германия": "Germany",
    "Нидерланды": "Netherlands",
    "Португалия": "Portugal",
    "Бельгия": "Belgium",
    "Бразилия": "Brazil",
    "Аргентина": "Argentina",
    "Мексика": "Mexico",
    "Канада": "Canada",
    "США": "USA",
    "Япония": "Japan",
    "Австралия": "Australia",
    "Южная Корея": "South Korea",
    "Марокко": "Morocco",
    "Уэльс": "Wales",
    "Шотландия": "Scotland",
    "Швейцария": "Switzerland",
    "Дания": "Denmark",
    "Норвегия": "Norway",
    "Швеция": "Sweden",
    "Греция": "Greece",
    "Чехия": "Czech Republic",
    "Венгрия": "Hungary",
    "Польша": "Poland",
    "Украина": "Ukraine",
    "Турция": "Turkey",
    "Иран": "Iran",
    "Саудовская Аравия": "Saudi Arabia",
    "Ирак": "Iraq",
    "Катар": "Qatar",
    "ОАЭ": "UAE",
    "Австрия": "Austria",
    "Хорватия": "Croatia",
    "Сербия": "Serbia",
    "Россия": "Russia",
    "Новая Зеландия": "New Zealand",
    "Косово": "Kosovo",
    "Грузия": "Georgia",
    "Киргизия": "Kyrgyzstan",
    "Узбекистан": "Uzbekistan",
    "Казахстан": "Kazakhstan",
    "Монголия": "Mongolia",
    "Таиланд": "Thailand",
    "Вьетнам": "Vietnam",
    "Индия": "India",
    "Чили": "Chile",
    "Парагвай": "Paraguay",
    "Коста-Рика": "Costa Rica",
    "Панама": "Panama",
    "Гондурас": "Honduras",
    "Сальвадор": "El Salvador",
}


def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_football_article(title: str, description: str) -> bool:
    """Check if article is about football/soccer."""
    text = f"{title} {description}".lower()

    # Core football keywords (at least one of these required)
    core_football_keywords = [
        "football", "soccer", "match", "goal", "goalkeeper",
        "striker", "midfielder", "defender", "offside", "penalty",
        "corner", "freekick", "free kick", "half-time", "halftime",
        "premier league", "la liga", "ligue 1", "serie a", "bundesliga",
        "champions league", "europa league", "world cup", "worldcup",
        "football club", "football team", "soccer team",
        "scored", "conceded", "assist", "tackle",
        "футбол", "матч", "гол", "вратарь", "защитник",
        "нападающий", "полузащитник", "офсайд", "пенальти",
        "чемпионат", "лига", "кубок", "мировой кубок"
    ]

    # Check if any core football keyword is in the text
    for keyword in core_football_keywords:
        if keyword in text:
            return True

    return False


async def _find_match_news_from_rss(home: str, away: str, match_date: str, is_world_cup: bool = False) -> Optional[str]:
    """
    Find sport news article about a specific match from RSS feeds.
    Searches SPORTS_FEEDS for articles mentioning both teams.

    Args:
        home: Home team name (Russian or English)
        away: Away team name (Russian or English)
        match_date: Match date in YYYY-MM-DD format
        is_world_cup: If True, translate Russian country names to English for RSS search

    Returns:
        Match news text or None if not found
    """
    # Team name mappings (Russian → English alternatives)
    TEAM_MAPPINGS = {
        "Манчестер": ["Manchester", "Man City", "Man Utd"],
        "Борнмут": ["Bournemouth", "AFC Bournemouth"],
        "Барселона": ["Barcelona", "Barça"],
        "Реал Мадрид": ["Real Madrid"],
        "Атлетико": ["Atlético Madrid", "Atletico"],
        "Арсенал": ["Arsenal"],
        "ПСЖ": ["PSG", "Paris"],
        "Манчестер Сити": ["Manchester City", "Man City"],
        "Манчестер Юнайтед": ["Manchester United", "Man Utd"],
    }

    # For World Cup matches, translate Russian country names to English
    search_home = home
    search_away = away

    if is_world_cup:
        search_home = COUNTRY_TRANSLATIONS.get(home, home)
        search_away = COUNTRY_TRANSLATIONS.get(away, away)
        logger.debug(f"World Cup match: translating {home} → {search_home}, {away} → {search_away}")

    # Build search alternatives
    home_alts = TEAM_MAPPINGS.get(search_home, [])
    away_alts = TEAM_MAPPINGS.get(search_away, [])
    logger.debug(f"Searching {len(SPORTS_FEEDS)} feeds for: '{search_home}'{f' (+{home_alts})' if home_alts else ''} vs '{search_away}'{f' (+{away_alts})' if away_alts else ''}")

    cutoff_time = datetime.strptime(match_date, "%Y-%m-%d")
    all_items = []
    feed_success_count = 0

    # Fetch from all sports feeds
    for feed_url in SPORTS_FEEDS:
        feed_name = feed_url.split('/')[2] if '/' in feed_url else feed_url
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(feed_url)
                response.raise_for_status()

            feed = feedparser.parse(response.text)
            feed_success_count += 1

            # Count matching articles in this feed
            feed_match_count = 0

            for entry in feed.entries[:20]:  # Check first 20 items per feed
                # Check publication date
                pub_time = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_time = datetime(*entry.updated_parsed[:6])

                # Only include articles from match date (or 1 day after for delayed reports)
                if pub_time:
                    # Check if date matches (match date or 1 day after for delayed reports)
                    days_diff = (pub_time.date() - cutoff_time.date()).days
                    if days_diff < 0 or days_diff > 1:
                        continue

                title = entry.get("title", "").lower()
                description = entry.get("summary", "")
                description = _clean_html(description)

                # Check if both team names are mentioned (with alternative names)
                def team_mentioned(team: str, text: str) -> bool:
                    """Check if team is mentioned in text (primary name or alternatives)."""
                    text_lower = text.lower()
                    if team.lower() in text_lower:
                        return True
                    # Check alternative names
                    alternatives = TEAM_MAPPINGS.get(team, [])
                    return any(alt.lower() in text_lower for alt in alternatives)

                home_mentioned = team_mentioned(search_home, title) or team_mentioned(search_home, description)
                away_mentioned = team_mentioned(search_away, title) or team_mentioned(search_away, description)
                is_football = _is_football_article(title, description)

                # Log matching attempts for first few non-matching entries
                if len(all_items) == 0 and len([x for x in [home_mentioned, away_mentioned, is_football] if x]) > 0:
                    logger.debug(f"  Partial match: home={home_mentioned}, away={away_mentioned}, football={is_football} | {entry.get('title', '')[:50]}")

                # Verify this is actually a football article
                if home_mentioned and away_mentioned and is_football:
                    url = entry.get("link", "")
                    all_items.append({
                        "title": entry.get("title", ""),
                        "description": description[:300],
                        "url": url,
                        "source": feed.feed.get("title", "Unknown")
                    })
                    feed_match_count += 1
                    logger.debug(f"  ✓ Match article found: {entry.get('title', '')[:60]}")

            # Log per-feed results if found matches
            if feed_match_count > 0:
                logger.debug(f"  {feed_name}: {feed_match_count} match article(s) found")

        except Exception as e:
            logger.debug(f"Failed to fetch {feed_name}: {type(e).__name__}: {str(e)[:50]}")
            continue

    # Return the first matching article's description
    logger.info(f"[RSS] Checked {feed_success_count}/{len(SPORTS_FEEDS)} feeds for '{search_home}' vs '{search_away}' on {match_date}")
    logger.debug(f"[RSS] Found {len(all_items)} matching articles across all feeds")

    if all_items:
        best = all_items[0]
        logger.info(f"✓ Found match news: {best['title'][:60]}... ({best['source']})")
        return best["description"]

    logger.info(f"[RSS] No match articles found for {search_home} vs {search_away} (checked {feed_success_count} feeds)")
    return None

# Priority teams in exact order (Russian names as they appear on kulichki.net)
PRIORITY_TEAMS = ["Барселона", "Реал Мадрид", "Арсенал", "ПСЖ", "Атлетико", "Манчестер"]

# Team flags for priority teams
TEAM_FLAGS = {
    "Барселона": "🇪🇸",
    "Реал Мадрид": "🇪🇸",
    "Атлетико": "🇪🇸",
    "Арсенал": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Манчестер": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "ПСЖ": "🇫🇷",
}

# National team flags for World Cup matches
NATIONAL_FLAGS = {
    "Испания": "🇪🇸",
    "Франция": "🇫🇷",
    "Англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Германия": "🇩🇪",
    "Нидерланды": "🇳🇱",
    "Португалия": "🇵🇹",
    "Бельгия": "🇧🇪",
    "Бразилия": "🇧🇷",
    "Аргентина": "🇦🇷",
    "Мексика": "🇲🇽",
    "Канада": "🇨🇦",
    "США": "🇺🇸",
    "Япония": "🇯🇵",
    "Австралия": "🇦🇺",
    "Южная Корея": "🇰🇷",
    "Марокко": "🇲🇦",
    "Англия": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Уэльс": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Шотландия": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Швейцария": "🇨🇭",
    "Дания": "🇩🇰",
    "Норвегия": "🇳🇴",
    "Швеция": "🇸🇪",
    "Греция": "🇬🇷",
    "Чехия": "🇨🇿",
    "Венгрия": "🇭🇺",
    "Польша": "🇵🇱",
    "Украина": "🇺🇦",
    "Турция": "🇹🇷",
    "Иран": "🇮🇷",
    "Саудовская Аравия": "🇸🇦",
    "Ирак": "🇮🇶",
    "Катар": "🇶🇦",
    "ОАЭ": "🇦🇪",
    "Австрия": "🇦🇹",
    "Хорватия": "🇭🇷",
    "Сербия": "🇷🇸",
    "Россия": "🇷🇺",
    "Новая Зеландия": "🇳🇿",
    "Косово": "🇽🇰",
    "Грузия": "🇬🇪",
    "Киргизия": "🇰🇬",
    "Узбекистан": "🇺🇿",
    "Казахстан": "🇰🇿",
    "Монголия": "🇲🇳",
    "Таиланд": "🇹🇭",
    "Вьетнам": "🇻🇳",
    "Индия": "🇮🇳",
    "Чили": "🇨🇱",
    "Парагвай": "🇵🇾",
    "Коста-Рика": "🇨🇷",
    "Панама": "🇵🇦",
    "Гондурас": "🇭🇳",
    "Сальвадор": "🇸🇻",
}

# League to country flag mapping
LEAGUE_FLAGS = {
    "La Liga": "🇪🇸",
    "Premier League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Ligue 1": "🇫🇷",
}





async def get_today_matches() -> Optional[List[Dict[str, Any]]]:
    """
    Get football matches for priority teams today via kulichki.net parser.
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

        # Check if these are World Cup matches
        is_world_cup = any("World Cup" in m.get("league", "") for m in all_matches)

        if is_world_cup:
            # For World Cup: return all matches (already filtered by kulichki_parser)
            logger.info(f"[FOOTBALL] ✓ World Cup detected - returning all {len(all_matches)} match(es)")
            for m in all_matches:
                logger.debug(f"[FOOTBALL]   - {m['home']} vs {m['away']}")
            return all_matches
        else:
            # For regular leagues: filter to only priority teams and sort by priority order
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

    # Get flags: check for national teams (World Cup) first, then club teams, then league
    home_flag = LEAGUE_FLAGS.get(league, "⚽")
    away_flag = LEAGUE_FLAGS.get(league, "⚽")

    # For World Cup: check national flags first
    if "World Cup" in league:
        for country, flag in NATIONAL_FLAGS.items():
            if country.lower() in home.lower():
                home_flag = flag
            if country.lower() in away.lower():
                away_flag = flag
    else:
        # For regular leagues: check club team flags
        for team in PRIORITY_TEAMS:
            if team.lower() in home.lower():
                home_flag = TEAM_FLAGS.get(team, home_flag)
            if team.lower() in away.lower():
                away_flag = TEAM_FLAGS.get(team, away_flag)

    # Time is already converted to Tbilisi in kulichki_parser (Moscow UTC+3 → Tbilisi UTC+4)
    tbilisi_time = time_str

    # Format standings context from league table or group info (for World Cup)
    standings_str = ""
    standings_info = ""
    group = match.get("group")

    # For World Cup matches: show group information
    if "World Cup" in league and group:
        standings_str = f"🏆 {group}"
        standings_info = f"Матч чемпионата мира в {group}"
    else:
        standings = match.get("standings")

        if standings and isinstance(standings, list) and len(standings) > 0:
            # Find full information for home and away teams in standings
            home_standing = None
            away_standing = None

            for standing in standings:
                team_name = standing.get("team", "").lower()
                if team_name and team_name in home.lower():
                    home_standing = standing
                if team_name and team_name in away.lower():
                    away_standing = standing

            # Build comprehensive standings context
            if home_standing and away_standing:
                home_pos = home_standing.get("position")
                away_pos = away_standing.get("position")

                # Get additional stats if available
                home_played = home_standing.get("played")
                away_played = away_standing.get("played")
                home_points = home_standing.get("points")
                away_points = away_standing.get("points")

                standings_str = f"Таблица: {home} на месте {home_pos}, {away} на месте {away_pos}."

                # Build detailed context for GPT
                standings_parts = []
                if home_pos and away_pos:
                    standings_parts.append(f"{home}: {home_pos} место")
                    if home_points:
                        standings_parts.append(f"{away}: {away_pos} место с {away_points} очками")
                    else:
                        standings_parts.append(f"{away}: {away_pos} место")

                standings_info = " | ".join(standings_parts) if standings_parts else standings_str
        else:
            # For playoff matches or tournaments without standings, show tournament name
            if league and any(keyword in league.lower() for keyword in ["cup", "playoff", "champions", "europa", "final", "league"]):
                standings_str = f"🏆 {league}"
                standings_info = f"Матч турнира: {league}"

    # Generate AI commentary (1-2 sentences with maximum context)
    prompt = f"""Напиши комментарий к предстоящему матчу футбола (1-2 предложения). Используй ВСЕ доступные данные для создания наиболее информативного описания.

МАТЧ:
{home} vs {away}

ТУРНИР:
{league}

ВРЕМЯ:
{tbilisi_time} Tbilisi (GMT+4)

КОНТЕКСТ И СТАТИСТИКА:
{standings_info}

ТРЕБОВАНИЯ:
- 1-2 предложения (максимум 30 слов)
- Максимально информативно и интересно
- Укажи позиции команд в таблице, если доступно
- Упомяни турнир, если это кубок/плей-офф
- Дай оценку силе сторон (фаворит/аутсайдер/равные шансы)
- На русском языке
- Без вводных фраз типа "Это матч" или "Будет интересно"
- Естественный, информативный язык

ПРИМЕРЫ ХОРОШИХ КОММЕНТАРИЕВ:
- "Лидер таблицы против 20-го места - явный фаворит. Реал Мадрид предпочитает контролировать мяч."
- "Матч чемпионата мира: столкновение фаворитов. Обе команды в боевом настроении."
- "Финал кубка сулит напряженную борьбу. Реал едет на выезд без особых преимуществ."
- "Третий и четвертый в таблице - баланс сил примерно равен, матч обещает быть интересным."

Ответ - только комментарий без пояснений, без кавычек:"""

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
        lines.append(standings_str)

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


async def get_yesterday_results() -> Optional[List[Dict[str, Any]]]:
    """
    Get yesterday's football results for priority teams via kulichki.net parser.
    Returns up to 3 completed matches in priority team order.
    """
    try:
        yesterday = (datetime.now()).strftime("%Y-%m-%d")
        logger.info(f"[FOOTBALL] Fetching yesterday's results")
        logger.debug(f"[FOOTBALL] Priority teams: {PRIORITY_TEAMS}")

        # Get results from kulichki.net
        logger.info(f"[FOOTBALL] Parsing kulichki.net for yesterday's results...")
        all_results = await get_yesterday_results_from_kulichki()

        if not all_results:
            logger.info(f"[FOOTBALL] No yesterday results found on kulichki.net")
            return None

        logger.info(f"[FOOTBALL] Found {len(all_results)} total results")

        # Filter to only priority teams (already done in parser, but keep for safety)
        priority_results = []

        for match in all_results:
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
                priority_results.append(match)
                logger.debug(f"[FOOTBALL] Found priority result: {home} vs {away} ({match['score']})")

        logger.info(f"[FOOTBALL] Priority results found: {len(priority_results)}")

        # Sort by priority index and take top 3
        priority_results.sort(key=lambda m: m["priority_idx"])
        result = priority_results[:3]

        if result:
            logger.info(f"[FOOTBALL] ✓ Returning {len(result)} top priority result(s)")
            for m in result:
                logger.debug(f"[FOOTBALL]   - {m['home']} vs {m['away']} ({m['score']})")
        else:
            logger.info(f"[FOOTBALL] No priority results found for yesterday")

        return result if result else None

    except Exception as e:
        logger.error(f"[FOOTBALL] Failed to get yesterday results: {type(e).__name__}: {e}", exc_info=True)
        return None


async def format_result_with_ai(result: Dict[str, Any]) -> str:
    """Format a yesterday's result with AI-generated commentary enhanced with match report."""
    home = result.get("home", "Unknown")
    away = result.get("away", "Unknown")
    score = result.get("score", "?:?")
    halftime_score = result.get("halftime_score")
    league = result.get("league", "")

    # Get flags with fuzzy matching, fallback to league flag
    home_flag = LEAGUE_FLAGS.get(league, "⚽")
    away_flag = LEAGUE_FLAGS.get(league, "⚽")

    for team in PRIORITY_TEAMS:
        if team.lower() in home.lower():
            home_flag = TEAM_FLAGS.get(team, home_flag)
        if team.lower() in away.lower():
            away_flag = TEAM_FLAGS.get(team, away_flag)

    # Format standings context from league table
    standings_str = ""
    standings_info = ""
    standings = result.get("standings")

    if standings and isinstance(standings, list) and len(standings) > 0:
        # Find full information for home and away teams in standings
        home_standing = None
        away_standing = None

        for standing in standings:
            team_name = standing.get("team", "").lower()
            if team_name and team_name in home.lower():
                home_standing = standing
            if team_name and team_name in away.lower():
                away_standing = standing

        # Build comprehensive standings context
        if home_standing and away_standing:
            home_pos = home_standing.get("position")
            away_pos = away_standing.get("position")
            home_points = home_standing.get("points")
            away_points = away_standing.get("points")

            standings_str = f"Таблица: {home} на месте {home_pos}, {away} на месте {away_pos}."

            # Build detailed context for GPT
            standings_parts = []
            if home_pos and away_pos:
                standings_parts.append(f"{home}: {home_pos} место")
                if away_points:
                    standings_parts.append(f"{away}: {away_pos} место с {away_points} очками")
                else:
                    standings_parts.append(f"{away}: {away_pos} место")

            standings_info = " | ".join(standings_parts) if standings_parts else standings_str
    else:
        # For playoff matches or tournaments without standings, show tournament name
        if league and any(keyword in league.lower() for keyword in ["cup", "playoff", "champions", "europa", "final", "league"]):
            standings_str = f"🏆 {league}"
            standings_info = f"Матч турнира: {league}"

    # Fetch match news from RSS feeds (yesterday's date)
    match_report = ""
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        is_world_cup = "World Cup" in league

        # First try to find news on match date (yesterday)
        news = await _find_match_news_from_rss(home, away, yesterday, is_world_cup=is_world_cup)

        # Fallback: if no news found, try 2 days ago (in case of delay)
        if not news:
            two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            logger.info(f"No match news on {yesterday}, trying {two_days_ago}...")
            news = await _find_match_news_from_rss(home, away, two_days_ago, is_world_cup=is_world_cup)

        if news:
            match_report = f"\nСПОРТИВНАЯ НОВОСТЬ О МАТЧЕ:\n{news}"
            logger.info(f"✓ Found match news for {home} vs {away} ({len(news)} chars)")
        else:
            logger.info(f"⚠️  No match news found for {home} vs {away} in last 2 days (will use standings only)")
    except Exception as e:
        logger.warning(f"Failed to fetch match news: {type(e).__name__}: {str(e)[:100]}")

    # Generate AI commentary (1-2 sentences)
    halftime_context = f" (перерыв: {halftime_score})" if halftime_score else ""
    prompt = f"""Напиши краткий обзор прошедшего матча (1-2 предложения). Используй ВСЕ доступные данные для максимальной информативности.

МАТЧ:
{home} vs {away}

ТУРНИР:
{league}

СЧЁТ:
{score}{halftime_context}

КОНТЕКСТ И СТАТИСТИКА:
{standings_info}{match_report}

ТРЕБОВАНИЯ:
- 1-2 предложения (максимум 30 слов)
- Укажи, кто победил и почему (разница класса, тактика, счёт)
- Используй информацию из спортивной новости если доступна
- Укажи позиции в таблице, если доступно, или кто прошёл дальше если кубок
- На русском языке
- Без вводных фраз типа "Это был матч"
- Информативный, естественный язык

ПРИМЕРЫ ХОРОШИХ КОММЕНТАРИЕВ:
- "Барселона одержала дерби с Реалом 2:1, сохраняя лидерство в La Liga."
- "Арсенал проиграл дома ПСЖ в полуфинале кубка, финальный счёт 1:0."
- "Атлетико прошёл дальше в Кубке - отработал на выезде, счёт 2:1."

Ответ - только комментарий без пояснений, без кавычек:"""

    commentary = None
    try:
        response = await get_client().chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=100,
            messages=[
                {"role": "system", "content": "You are a sports analyst in Russian. Provide brief match summaries based on available information."},
                {"role": "user", "content": prompt},
            ],
        )

        commentary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Failed to generate AI result commentary: {e}")
        commentary = None

    # Build result text
    lines = [f"{home_flag} {home} vs {away} {away_flag}"]
    lines.append(f"{league} • Счёт: {score}{halftime_context}")

    if standings_str:
        lines.append(standings_str)

    if commentary:
        lines.append(f"💭 {commentary}")

    return "\n".join(lines)


async def get_formatted_results(results: List[Dict[str, Any]]) -> Optional[str]:
    """Format all yesterday results for digest display."""
    if not results:
        return None

    try:
        message_lines = ["⚽ <b>Результаты вчерашних матчей:</b>", ""]

        for result in results:
            formatted = await format_result_with_ai(result)
            message_lines.append(formatted)
            message_lines.append("")

        return "\n".join(message_lines).rstrip()

    except Exception as e:
        logger.error(f"Failed to format results: {e}")
        return None
