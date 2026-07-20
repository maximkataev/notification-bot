"""National team matches (Россия, Грузия, Испания, Аргентина) via TheSportsDB.

The World Cup 2026 scraping was removed when the tournament ended; this worker
covers everything national teams play OUTSIDE a running World Cup: qualifiers,
UEFA Nations League, friendlies, continental cups. kulichki.net has no clean
machine-readable pages for these (the Nations League page is prose-formatted),
so we use TheSportsDB — a free JSON API (test key "123") that tracks national
sides including friendlies. 2 requests per tracked team per digest.

Events are returned in the SAME dict shape as kulichki club matches, so the
existing digest formatting (format_match_with_ai / format_result_with_ai) works
unchanged: upcoming matches join the "Ближайшие матчи" section, finished ones
join "Результаты вчерашних матчей".
"""

import asyncio
import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# TheSportsDB team id → Russian team name. Add a team here to start tracking it.
TRACKED_TEAMS: Dict[int, str] = {
    133903: "Россия",
    135930: "Грузия",
    133909: "Испания",
    134509: "Аргентина",
}

_API_BASE = "https://www.thesportsdb.com/api/v1/json/123"

# TheSportsDB league names → Russian labels for the digest.
_LEAGUE_RU = {
    "UEFA Nations League": "Лига наций УЕФА",
    "International Friendlies": "Товарищеский матч",
    "World Cup Qualifying UEFA": "Отбор ЧМ (УЕФА)",
    "World Cup Qualifying CONMEBOL": "Отбор ЧМ (Юж. Америка)",
    "UEFA European Championship Qualifying": "Отбор Евро",
    "UEFA European Championship": "Чемпионат Европы",
    "FIFA World Cup": "Чемпионат мира",
    "Copa America": "Кубок Америки",
}

# English country name (as TheSportsDB sends it, incl. common aliases) → (Russian
# name, flag). Unknown opponents keep their English name with a neutral flag.
NATIONS: Dict[str, Tuple[str, str]] = {
    "Albania": ("Албания", "🇦🇱"),
    "Algeria": ("Алжир", "🇩🇿"),
    "Angola": ("Ангола", "🇦🇴"),
    "Argentina": ("Аргентина", "🇦🇷"),
    "Armenia": ("Армения", "🇦🇲"),
    "Australia": ("Австралия", "🇦🇺"),
    "Austria": ("Австрия", "🇦🇹"),
    "Azerbaijan": ("Азербайджан", "🇦🇿"),
    "Bahrain": ("Бахрейн", "🇧🇭"),
    "Belarus": ("Беларусь", "🇧🇾"),
    "Belgium": ("Бельгия", "🇧🇪"),
    "Benin": ("Бенин", "🇧🇯"),
    "Bolivia": ("Боливия", "🇧🇴"),
    "Bosnia": ("Босния", "🇧🇦"),
    "Bosnia and Herzegovina": ("Босния", "🇧🇦"),
    "Brazil": ("Бразилия", "🇧🇷"),
    "Bulgaria": ("Болгария", "🇧🇬"),
    "Burkina Faso": ("Буркина-Фасо", "🇧🇫"),
    "Cameroon": ("Камерун", "🇨🇲"),
    "Canada": ("Канада", "🇨🇦"),
    "Cape Verde": ("Кабо-Верде", "🇨🇻"),
    "Chile": ("Чили", "🇨🇱"),
    "China": ("Китай", "🇨🇳"),
    "Colombia": ("Колумбия", "🇨🇴"),
    "Congo": ("Конго", "🇨🇬"),
    "Costa Rica": ("Коста-Рика", "🇨🇷"),
    "Cote d'Ivoire": ("Кот-д'Ивуар", "🇨🇮"),
    "Croatia": ("Хорватия", "🇭🇷"),
    "Curacao": ("Кюрасао", "🇨🇼"),
    "Curaçao": ("Кюрасао", "🇨🇼"),
    "Cyprus": ("Кипр", "🇨🇾"),
    "Czech Republic": ("Чехия", "🇨🇿"),
    "Czechia": ("Чехия", "🇨🇿"),
    "DR Congo": ("ДР Конго", "🇨🇩"),
    "Denmark": ("Дания", "🇩🇰"),
    "Ecuador": ("Эквадор", "🇪🇨"),
    "Egypt": ("Египет", "🇪🇬"),
    "El Salvador": ("Сальвадор", "🇸🇻"),
    "England": ("Англия", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    "Equatorial Guinea": ("Экваториальная Гвинея", "🇬🇶"),
    "Estonia": ("Эстония", "🇪🇪"),
    "Ethiopia": ("Эфиопия", "🇪🇹"),
    "Fiji": ("Фиджи", "🇫🇯"),
    "Finland": ("Финляндия", "🇫🇮"),
    "France": ("Франция", "🇫🇷"),
    "Gabon": ("Габон", "🇬🇦"),
    "Georgia": ("Грузия", "🇬🇪"),
    "Germany": ("Германия", "🇩🇪"),
    "Ghana": ("Гана", "🇬🇭"),
    "Greece": ("Греция", "🇬🇷"),
    "Guatemala": ("Гватемала", "🇬🇹"),
    "Guinea": ("Гвинея", "🇬🇳"),
    "Guinea-Bissau": ("Гвинея-Бисау", "🇬🇼"),
    "Haiti": ("Гаити", "🇭🇹"),
    "Honduras": ("Гондурас", "🇭🇳"),
    "Hungary": ("Венгрия", "🇭🇺"),
    "Iceland": ("Исландия", "🇮🇸"),
    "India": ("Индия", "🇮🇳"),
    "Indonesia": ("Индонезия", "🇮🇩"),
    "Iran": ("Иран", "🇮🇷"),
    "Iraq": ("Ирак", "🇮🇶"),
    "Ireland": ("Ирландия", "🇮🇪"),
    "Italy": ("Италия", "🇮🇹"),
    "Ivory Coast": ("Кот-д'Ивуар", "🇨🇮"),
    "Jamaica": ("Ямайка", "🇯🇲"),
    "Japan": ("Япония", "🇯🇵"),
    "Jordan": ("Иордания", "🇯🇴"),
    "Kazakhstan": ("Казахстан", "🇰🇿"),
    "Kenya": ("Кения", "🇰🇪"),
    "Korea DPR": ("Северная Корея", "🇰🇵"),
    "Korea Republic": ("Южная Корея", "🇰🇷"),
    "Kosovo": ("Косово", "🇽🇰"),
    "Kuwait": ("Кувейт", "🇰🇼"),
    "Kyrgyzstan": ("Киргизия", "🇰🇬"),
    "Latvia": ("Латвия", "🇱🇻"),
    "Lebanon": ("Ливан", "🇱🇧"),
    "Libya": ("Ливия", "🇱🇾"),
    "Lithuania": ("Литва", "🇱🇹"),
    "Luxembourg": ("Люксембург", "🇱🇺"),
    "Madagascar": ("Мадагаскар", "🇲🇬"),
    "Malaysia": ("Малайзия", "🇲🇾"),
    "Mali": ("Мали", "🇲🇱"),
    "Malta": ("Мальта", "🇲🇹"),
    "Mauritania": ("Мавритания", "🇲🇷"),
    "Mexico": ("Мексика", "🇲🇽"),
    "Moldova": ("Молдова", "🇲🇩"),
    "Mongolia": ("Монголия", "🇲🇳"),
    "Montenegro": ("Черногория", "🇲🇪"),
    "Morocco": ("Марокко", "🇲🇦"),
    "Mozambique": ("Мозамбик", "🇲🇿"),
    "N.Ireland": ("Северная Ирландия", "🇬🇧"),
    "Namibia": ("Намибия", "🇳🇦"),
    "Netherlands": ("Нидерланды", "🇳🇱"),
    "New Caledonia": ("Новая Каледония", "🇳🇨"),
    "New Zealand": ("Новая Зеландия", "🇳🇿"),
    "Nicaragua": ("Никарагуа", "🇳🇮"),
    "Nigeria": ("Нигерия", "🇳🇬"),
    "North Korea": ("Северная Корея", "🇰🇵"),
    "North Macedonia": ("Македония", "🇲🇰"),
    "Northern Ireland": ("Северная Ирландия", "🇬🇧"),
    "Norway": ("Норвегия", "🇳🇴"),
    "Oman": ("Оман", "🇴🇲"),
    "Palestine": ("Палестина", "🇵🇸"),
    "Panama": ("Панама", "🇵🇦"),
    "Papua New Guinea": ("Новая Гвинея", "🇵🇬"),
    "Paraguay": ("Парагвай", "🇵🇾"),
    "Peru": ("Перу", "🇵🇪"),
    "Poland": ("Польша", "🇵🇱"),
    "Portugal": ("Португалия", "🇵🇹"),
    "Qatar": ("Катар", "🇶🇦"),
    "Republic of Ireland": ("Ирландия", "🇮🇪"),
    "Romania": ("Румыния", "🇷🇴"),
    "Russia": ("Россия", "🇷🇺"),
    "Saudi Arabia": ("Саудовская Аравия", "🇸🇦"),
    "Scotland": ("Шотландия", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    "Senegal": ("Сенегал", "🇸🇳"),
    "Serbia": ("Сербия", "🇷🇸"),
    "Sierra Leone": ("Сьерра-Леоне", "🇸🇱"),
    "Slovakia": ("Словакия", "🇸🇰"),
    "Slovenia": ("Словения", "🇸🇮"),
    "Solomon Islands": ("Соломоновы Острова", "🇸🇧"),
    "Somalia": ("Сомали", "🇸🇴"),
    "South Africa": ("ЮАР", "🇿🇦"),
    "South Korea": ("Южная Корея", "🇰🇷"),
    "Spain": ("Испания", "🇪🇸"),
    "Sudan": ("Судан", "🇸🇩"),
    "Suriname": ("Суринам", "🇸🇷"),
    "Sweden": ("Швеция", "🇸🇪"),
    "Switzerland": ("Швейцария", "🇨🇭"),
    "Syria": ("Сирия", "🇸🇾"),
    "Tahiti": ("Таити", "🇵🇫"),
    "Tajikistan": ("Таджикистан", "🇹🇯"),
    "Tanzania": ("Танзания", "🇹🇿"),
    "Thailand": ("Таиланд", "🇹🇭"),
    "Togo": ("Того", "🇹🇬"),
    "Trinidad and Tobago": ("Тринидад", "🇹🇹"),
    "Tunisia": ("Тунис", "🇹🇳"),
    "Turkey": ("Турция", "🇹🇷"),
    "Turkmenistan": ("Туркменистан", "🇹🇲"),
    "Türkiye": ("Турция", "🇹🇷"),
    "UAE": ("ОАЭ", "🇦🇪"),
    "USA": ("США", "🇺🇸"),
    "Uganda": ("Уганда", "🇺🇬"),
    "Ukraine": ("Украина", "🇺🇦"),
    "United States": ("США", "🇺🇸"),
    "Uruguay": ("Уругвай", "🇺🇾"),
    "Uzbekistan": ("Узбекистан", "🇺🇿"),
    "Vanuatu": ("Вануату", "🇻🇺"),
    "Venezuela": ("Венесуэла", "🇻🇪"),
    "Vietnam": ("Вьетнам", "🇻🇳"),
    "Wales": ("Уэльс", "🏴󠁧󠁢󠁷󠁬󠁳󠁿"),
    "Yemen": ("Йемен", "🇾🇪"),
    "Zambia": ("Замбия", "🇿🇲"),
    "Zimbabwe": ("Зимбабве", "🇿🇼"),
}


def _localize_team(name: str) -> Tuple[str, str]:
    """(Russian name, flag) for a TheSportsDB team name; fallback (as-is, ⚽)."""
    ru = NATIONS.get((name or "").strip())
    if ru:
        return ru
    return (name or "?", "⚽")


def _parse_utc(ts: str):
    """Parse TheSportsDB strTimestamp (UTC, ISO-ish) → naive UTC datetime or None."""
    try:
        return datetime.fromisoformat((ts or "").replace("Z", ""))
    except ValueError:
        return None


def _to_match_dict(event: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a TheSportsDB event to the kulichki-style match dict."""
    home_en = (event.get("strHomeTeam") or "").strip()
    away_en = (event.get("strAwayTeam") or "").strip()
    home_ru, home_flag = _localize_team(home_en)
    away_ru, away_flag = _localize_team(away_en)

    kickoff_utc = _parse_utc(event.get("strTimestamp") or "")
    kickoff_tbilisi = kickoff_utc + timedelta(hours=4) if kickoff_utc else None

    league_en = event.get("strLeague") or ""
    match = {
        "home": home_ru,
        "away": away_ru,
        "home_en": home_en,
        "away_en": away_en,
        "home_flag": home_flag,
        "away_flag": away_flag,
        "league": _LEAGUE_RU.get(league_en, league_en),
        "time": kickoff_tbilisi.strftime("%H:%M") if kickoff_tbilisi else "TBD",
        "match_date": kickoff_tbilisi.date().isoformat() if kickoff_tbilisi else None,
        "kickoff": kickoff_tbilisi.isoformat() if kickoff_tbilisi else None,
        "kickoff_utc": kickoff_utc,
    }

    home_score = event.get("intHomeScore")
    away_score = event.get("intAwayScore")
    if home_score is not None and away_score is not None:
        match["score"] = f"{home_score}:{away_score}"
        match["halftime_score"] = None
    return match


async def _fetch_events(client: httpx.AsyncClient, endpoint: str, team_id: int, key: str) -> List[Dict[str, Any]]:
    """GET eventsnext/eventslast for a team; [] on any failure (worker must not break the digest)."""
    try:
        response = await client.get(f"{_API_BASE}/{endpoint}.php", params={"id": team_id})
        response.raise_for_status()
        return (response.json() or {}).get(key) or []
    except Exception as e:
        logger.warning(f"[NATIONAL] {endpoint} failed for team {team_id}: {type(e).__name__}: {str(e)[:80]}")
        return []


async def get_national_team_events() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch tracked national teams' matches: (upcoming next 24h, finished last 24h).

    Both lists use the kulichki match dict shape. Deduplicated by event id (two
    tracked teams playing each other produce one entry), sorted by kickoff.
    """
    now_utc = datetime.utcnow()
    upcoming: Dict[str, Dict[str, Any]] = {}
    results: Dict[str, Dict[str, Any]] = {}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for team_id, team_name in TRACKED_TEAMS.items():
                next_events = await _fetch_events(client, "eventsnext", team_id, "events")
                last_events = await _fetch_events(client, "eventslast", team_id, "results")

                for event in next_events:
                    match = _to_match_dict(event)
                    kickoff_utc = match.pop("kickoff_utc", None)
                    if kickoff_utc is None:
                        continue
                    if now_utc <= kickoff_utc < now_utc + timedelta(hours=24):
                        upcoming[event.get("idEvent") or match["home"] + match["away"]] = match
                    else:
                        logger.debug(f"[NATIONAL] {team_name}: {match['home']} vs {match['away']} at {kickoff_utc}Z — outside 24h window")

                for event in last_events:
                    match = _to_match_dict(event)
                    kickoff_utc = match.pop("kickoff_utc", None)
                    if kickoff_utc is None or "score" not in match:
                        continue
                    if now_utc - timedelta(hours=24) <= kickoff_utc < now_utc:
                        results[event.get("idEvent") or match["home"] + match["away"]] = match
    except Exception as e:
        logger.warning(f"[NATIONAL] Fetch failed: {type(e).__name__}: {e}")
        return [], []

    upcoming_list = sorted(upcoming.values(), key=lambda m: m.get("kickoff") or "9999")
    results_list = sorted(results.values(), key=lambda m: m.get("kickoff") or "9999")
    logger.info(f"[NATIONAL] upcoming(24h)={len(upcoming_list)}, results(24h)={len(results_list)}")
    return upcoming_list, results_list
