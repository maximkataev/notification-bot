# CLAUDE.md — Telegram Notification Bot with AI Task Planner

Comprehensive guide for Claude Code working with this project. This bot is a multi-feature Telegram service that combines task planning, news aggregation, weather reporting, exchange rate tracking, and infrastructure monitoring.

I'm using gpt-5.4-mini model. Don't ever fucking change it.

## Project Overview

**Purpose**: Deliver a morning digest with weather, news, tasks, exchange rates, and alerts directly to Telegram.

**Core Features**:
1. **Morning Digest** (scheduled 08:00 daily) — single comprehensive message with all information
2. **Task Notifications** — free-text task input → AI parsing → smart scheduling → reminder in digest
3. **Weather Aggregation** — multiple sources with fallback
4. **News Feed** — real RSS data only, keyword-based filtering (no AI generation)
5. **Exchange Rates** — BTC, ETH, USD→EUR, USD→RUB from multiple APIs
6. **Infrastructure Alerts** — GWP (Georgian Water & Power) works on Vazha Iverievi street
7. **Holiday/Event Tracking** — Georgia, Russia, Cyprus holidays + DST changes

**Architecture**: Single-user bot instance with FastAPI webhook server. Telegram sends updates via HTTP webhooks to the server, processed through aiogram dispatcher. Background tasks (scheduler, monitors) run on same asyncio event loop with SQLite database.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Bot Framework | aiogram 3.x | Telegram API integration with Router/Dispatcher pattern |
| Webhook Server | FastAPI + uvicorn | HTTP webhook endpoint for Telegram updates |
| Async Runtime | asyncio | All I/O operations (HTTP, database, Telegram) |
| Database | SQLite (aiosqlite) | Task persistence, user profiles, custom rules |
| AI Models | OpenAI GPT-4o | Task parsing, morning intro, task explanations |
| HTTP Client | httpx (async) | All external API calls |
| News Parsing | feedparser | RSS feed parsing |
| HTML Parsing | BeautifulSoup | GWP website scraping |
| Scheduling | APScheduler (AsyncIOScheduler) | Morning digest cron job (08:00) |
| Secrets | Doppler CLI | All credentials (no .env files) |

## Project Structure

```
notification-bot/
├── src/
│   ├── bot/
│   │   ├── main.py                 # aiogram setup, dispatcher, polling
│   │   ├── scheduler.py            # Morning digest orchestration (CRITICAL)
│   │   ├── handlers/
│   │   │   ├── plan_handler.py     # /plan command, task input
│   │   │   ├── tasks_handler.py    # /tasks command
│   │   │   ├── profile_handler.py  # /me (user preferences)
│   │   │   ├── ai_handler.py       # /ai-* (custom rules)
│   │   │   ├── news_handler.py     # /news_* (prompt management)
│   │   │   └── digest_handler.py   # /digest (send now)
│   │
│   ├── ai/
│   │   ├── planner_agent.py        # GPT-4o task parsing + system prompt
│   │   ├── task_explainer.py       # Generate brief task explanations
│   │   ├── news_selector.py        # Keyword-based news filtering (NO AI)
│   │   └── weather_aggregator.py   # Multi-source weather with fallback
│   │
│   ├── workers/
│   │   ├── news_fetcher.py         # 9 RSS feeds, 12h window
│   │   ├── gwp_checker.py          # BeautifulSoup scraper for works
│   │   ├── rates_fetcher.py        # Crypto + forex rates
│   │   ├── currency_monitor.py     # Background EUR/USD alerting
│   │   └── holidays.py             # Nager.Date API for holidays + DST
│   │
│   ├── db/
│   │   ├── models.py               # Task, UserProfile dataclasses
│   │   └── database.py             # aiosqlite CRUD, auto-migration
│   │
│   └── utils/
│       ├── doppler.py              # Secrets retrieval
│       ├── tbc_bank.py             # Exchange rate APIs (fallback chain)
│       └── telegram.py             # Message sending utility
│
├── data/
│   └── tasks.db                    # SQLite database (auto-created)
│
├── requirements.txt                # Dependencies
├── CLAUDE.md                        # This file
└── docker-compose.yml              # Docker setup
```

## Core Components Deep Dive

### 1. **Scheduler** (`src/bot/scheduler.py`) — CRITICAL

The heart of the morning digest. Orchestrates all digest components in sequence.

**Function**: `morning_digest(bot: Bot, user_id: int, chat_id: int)`

**Execution Flow**:
1. Load user tasks for today (filter by `when_date == today`)
2. Load user profile (wake/sleep times, preferences)
3. Fetch aggregated weather (Open-Meteo + wttr.in)
4. **Generate weather context intro** via GPT-4o (1-2 sentences in Russian)
5. **Fetch quote of the day** (inspirational wisdom from quotable.io API, fallback to hardcoded quotes)
6. **Format weather** by periods (morning/day/evening/night) with emoji + condition + temp
7. **Fetch air quality** in Tbilisi (Open-Meteo air quality API) with AQI and PM2.5
8. **Check for today's holidays** (Nager.Date API)
9. **Check for today's DST events** (calculated from last Sunday March/October)
10. **Check GWP works** on Vazha Iverievi street
11. **Fetch recent news** from 11 RSS feeds (12-hour window)
12. **Filter and select news** using GPT-4o with user preferences:
    - 2 stories (politics, economics, finance)
    - 1 sports story (football, hockey, etc.)
    - 1 culture/society/good news story
    - 1 IT/AI/technology story (for analyst & tech specialist)
13. **Format news** as: `[Source](url): description` (markdown links)
14. **Score and sort tasks** by importance (urgent +100, outdoor +30, timed +20, dated +10)
15. **Generate AI explanations** for top 5 tasks
16. **Fetch exchange rates** (BTC, ETH, USD→EUR, USD→RUB) with 24h/30d changes
17. **Fetch top Product Hunt product** (today's top product with description)
18. **Get content recommendation** (random video, podcast, or music for analyst/tech specialist)
19. **Check OpenAI account balance** (shows balance, warns if <$0.50)
20. **Build final message** with all sections
21. **Send to Telegram** via `bot.send_message()` (split if >4000 chars)

**Critical Bug Fixes**:
- News items from `news_fetcher.py` have `description` field, NOT `summary`
- Scheduler line 162 now correctly uses: `summary = news.get("description", "")`
- All trailing zeros in exchange rates removed: `f"{value:,.5f}".rstrip('0').rstrip('.')`

**Model Used**: `gpt-4o` (generates 1–2 sentence intro with weather + practical context)

**Key Formatting**:
```python
# Currency rates: 5 decimals, strip trailing zeros
f"{value:,.5f}".rstrip('0').rstrip('.')  # Outputs: $1.18 not $1.18000

# News: [Source](url): brief description
f"{i}. [{source}]({url}): {summary}"

# Tasks: bullet + name + time (if set) + urgent marker
f"• {name}{time_str}{urgent}"
f"  └ {explanation}"  # AI-generated explanation
```

**Scheduling**:
- Triggered by APScheduler at 08:00 (CronTrigger in `init_scheduler()`)
- Can also be triggered manually via `/digest` command

---

### 2. **Task Planner** (`src/ai/planner_agent.py`)

Converts free-text task input into structured JSON with AI reasoning.

**Function**: `parse_task(raw_text, user_profile, existing_tasks, custom_rules) → Dict`

**System Prompt Context** (injected for every parse):
- Current date, day of week, time
- User profile: wake/sleep times, timezone, preferences
- Working hours: 10:00–19:00 (weekdays only)
- Weather: current conditions, temperature (affects outdoor task timing)
- Custom user rules: injected as-is into the prompt
- Existing tasks: context to avoid conflicts

**Parsed JSON Output Schema**:
```json
{
  "what": "task action",
  "when_date": "YYYY-MM-DD or null",
  "when_time": "HH:MM or null",
  "place": "location name or null",
  "place_hours": {"mon": "10:00-18:00", ...} or null,
  "proposed_time": "HH:MM or null",
  "is_urgent": true/false,
  "is_outdoor": true/false,
  "is_recurring": true/false,
  "recurrence_pattern": "every_monday|tue_fri|every_day|weekly|sat_sun|mon_tue_wed_thu_fri|null",
  "recurrence_end_date": "YYYY-MM-DD or null",
  "constraints": "extracted constraints as text",
  "explanation": "human-readable explanation in Russian",
  "needs_clarification": true/false,
  "clarification_question": "question for user or null"
}
```

**Smart Features**:
- **Urgency Detection**: "urgent", "ASAP", "today", "срочно" → overrides working hours
- **Weather Context**: Outdoor tasks → AI suggests weather-appropriate times
- **Flexible Deadlines**: "можно в среду" → uses first date, puts alternative in constraints
- **Reminder Pattern**: "напомни в X" → creates two tasks (main + reminder)
- **Recurring Tasks**: "каждый понедельник", "по вторникам и пятницам" → sets recurrence_pattern
- **Weekend Awareness**: Tasks on Sat/Sun → flexible timing, not work hours

**Model Used**: `gpt-4o` (parses complex, context-rich tasks)

**JSON Extraction**: Handles markdown code blocks (`\`\`\`json ... \`\`\``)

**Fallback Behavior**: If parsing fails, returns error object with `needs_clarification: true`

---

### 3. **News Processor** (`src/ai/news_processor.py`) — GPT-4o SELECTION WITH EXCLUSION FILTERING

**Design**: GPT-4o selects news from real RSS data with user preference enforcement.

**Selection Process**:
1. Fetch raw news from RSS feeds
2. Build indexed list for GPT
3. Inject user profile (interests + exclusions)
4. GPT-4o selects exactly 5 news items across categories
5. Post-filter: reject any items containing excluded keywords
6. Return selected news with summaries

**News Categories** (5 total):
1. **Politics/Economics** (2 stories) — politics, finance, markets, trade
2. **Sports** (1 story) — football (especially European/Spanish), hockey, etc.
3. **Culture/Society/Good News** (1 story) — cultural events, social progress, positive stories
4. **Technology/AI** (1 story) — IT, AI, machine learning, innovations (for analyst & tech specialist)

**User Customization**:
- Custom prompt via `/news_set <text>` command
- Can specify interests and strict exclusions (e.g., "ИСКЛЮЧАЮ: документалки, сериалы, кино")
- Exclusions are extracted and enforced at post-processing stage
- Default profile available if no custom prompt set

**Exclusion Enforcement**:
- Extracted from user profile after "ИСКЛЮЧАЮ:" marker
- Checked against title and description of selected items
- Items violating exclusions are removed and not included in digest
- Ensures no hallucinations or unwanted content

**Output Format**:
```python
[
  {
    "index": 0,
    "category": "politics",
    "summary": "Brief one-liner (max 15 words)",
    "description_ru": "Full summary in Russian (max 250 chars)"
  },
  ...
]
```

---

### 4. **News Fetcher** (`src/workers/news_fetcher.py`)

Aggregates real news from 11 free RSS feeds covering politics, economics, culture, sports, and technology.

**RSS Feeds** (by category):
**Politics & Economics**:
1. Bloomberg Markets
2. Politico Europe

**World News & Culture**:
3. BBC News
4. The Guardian
5. NPR News

**Technology & AI** (for analyst & tech-savvy user):
6. TechCrunch
7. Ars Technica
8. Hacker News
9. The Verge
10. Bloomberg Technology

**Russia & CIS**:
11. Meduza

**Validation Rules**:
- Only parse entries with `title`
- Only accept entries with `link` (URL)
- Only accept URLs starting with `http://` or `https://`
- Skip entries older than cutoff time (12 hours by default)
- Take first 300 chars of description

**Function**: `async get_recent_news(hours=12) → List[Dict]`

**Output Format** (per item):
```python
{
    "title": str,              # Entry title
    "description": str,        # First 300 chars of summary
    "source": str,             # Feed title
    "url": str,                # Entry link
    "published": ISO timestamp # Parsed from entry.published_parsed
}
```

**Error Handling**:
- Timeout: 10 seconds per feed
- Failed feed: logged, continues to next
- Returns: all successfully fetched items (partial results OK)

---

### 5. **Weather Aggregator** (`src/ai/weather_aggregator.py`)

Multi-source weather with fallback and averaging.

**Sources**:
1. **Open-Meteo** (primary): Free, no API key, hourly detailed
2. **wttr.in** (fallback): Free, public service

**Function**: `async get_aggregated_weather() → Dict`

**Output Format** (by periods):
```python
{
    "morning": {
        "emoji": "🌤️",
        "condition": "переменная облачность",
        "temperature": 18.5,  # Celsius, rounded to 1 decimal
    },
    "day": {...},
    "evening": {...},
    "night": {...}
}
```

**Fallback Logic**:
- Try Open-Meteo first
- If timeout/error → use wttr.in
- If both fail → return None, scheduler shows "🌤️ Погода недоступна"

**Period Grouping**:
- Night: 00:00–06:00
- Morning: 06:00–12:00
- Day: 12:00–18:00
- Evening: 18:00–24:00

---

### 6. **GWP Checker** (`src/workers/gwp_checker.py`)

Monitors Georgian Water & Power website for infrastructure works on Vazha Iverievi street.

**Street Name Variants** (case-insensitive matching):
- vazha iverievi (English transliteration)
- ვაზა ივერიელი (Georgian)
- ვაჟა ივერელის ქუჩა (Georgian with "street" suffix)
- ვაჟა ივერელი (Georgian alternative)
- vazha iverelis (alternative transliteration)

**URLs**:
- Scheduled works: `https://www.gwp.ge/en/news/scheduled-works/`
- Unscheduled works: `https://www.gwp.ge/en/news/nonscheduled-works/`

**Redirect Handling**:
```python
# GWP may return 301 redirect from URL without trailing slash
try:
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
except Exception:
    # Fallback: retry with trailing slash
    if not url.endswith('/'):
        response = await client.get(url + '/', follow_redirects=True)
        response.raise_for_status()
```

**HTML Parsing**:
- Tries multiple selectors: `.item-news`, `<article>`, `.news-item`, `.news`, `.news` `<li>`
- Extracts title from: `<h2>`, `<h3>`, `<h4>`, `.title <a>`, any `<a>`
- Fallback: first 80 chars of text if no heading found

**Function**: `async check_gwp_works() → Optional[List[str]]`

**Output Format**:
```python
[
    "🚧 Scheduled work: Pipe replacement on Vazha Iverievi",
    "🚧 Unscheduled work: Emergency repairs on main street"
]
```

**Timeout**: 10 seconds per request

---

### 7. **Holidays & Events** (`src/workers/holidays.py`)

Dynamic holiday and DST event tracking (NO hardcoding).

**Holiday API**: Nager.Date (`https://date.nager.at/api/v3/PublicHolidays/{year}/{country}`)

**Countries**:
- Georgia (GE)
- Russia (RU)
- Cyprus (CY)

**DST Calculation** (hardcoded algorithm, not from API):
- **DST Start**: Last Sunday of March at 02:00 (clocks forward +1h)
- **DST End**: Last Sunday of October at 03:00 (clocks back -1h)

**Functions**:

```python
async def get_today_holidays() → Optional[List[Tuple[str, str]]]
  # Returns: [("🇬🇪 Georgia: Easter", "🎉"), ...]

async def get_today_events() → Optional[List[str]]
  # Returns: ["⏰ Daylight Saving Time begins at 02:00..."]

async def get_upcoming_holidays(days_ahead=7) → Optional[List[str]]
  # Returns: ["🎉 🇬🇪 Georgia: Holiday (in 3 days)", ...]
```

**Error Handling**:
- Timeout: 5 seconds per request
- Failed requests logged but not fatal
- If API unavailable, returns None

---

### 8. **Exchange Rates** (`src/workers/rates_fetcher.py`)

Cryptocurrency and forex rates with 24h and 30d change tracking.

**Rates Tracked**:
- BTC/USD (Bitcoin) with change %
- ETH/USD (Ethereum) with change %
- USD→EUR (Euro) with change %
- USD→RUB (Russian Ruble) with change %

**Data Sources**:

**Crypto** (BTC, ETH):
- Source: CoinGecko API endpoint `/coins/bitcoin` and `/coins/ethereum`
- Includes: current price + official `price_change_percentage_24h` and `price_change_percentage_30d`

**Forex** (EUR/USD, USD/RUB):
- Current rates: `exchangerate-api.com` (free, no API key)
- Historical changes (24h, 30d): Yahoo Finance via yfinance (free, no API key)
  - Downloads EUR/USD and RUB/USD for last 30 days
  - If yfinance unavailable, historical changes not shown

**Output Format**:
```python
{
    "btc_usd": 80819.0,
    "btc_change_24h": 0.9,           # % change past 24h
    "btc_change_30d": 11.7,          # % change past 30d
    "eth_usd": 2327.88,
    "eth_change_24h": 0.5,
    "eth_change_30d": 4.7,
    "usd_eur": 0.849,                # USD→EUR rate
    "eur_change_24h": 0.05,          # % change in EUR/USD
    "eur_change_30d": 1.1,
    "usd_rub": 74.59,                # USD→RUB rate
    "rub_change_24h": 0.0,           # % change in USD/RUB
    "rub_change_30d": 5.8,
}
```

**Functions**:
- `get_crypto_and_forex_rates()`: Fetch all rates and calculate changes
- `get_historical_forex_rates()`: Calculate EUR/USD and USD/RUB changes via BTC prices

**Display Formatting** (in scheduler):
```python
# Currency value formatting
f"{value:,.5f}".rstrip('0').rstrip('.')  # Examples: $67234.5, 1.17786

# Change formatting
arrow = "↑" if change >= 0 else "↓"
f"({arrow} {abs(change):.1f}% for 24h, ...)"  # Example: (↑ 0.9% for 24h, ↑ 11.7 % for 30d)

# Example output in digest:
# BTC: 80 819 USD (↑ 0.9% for 24h, ↑ 11.7 % for 30d)
# EUR: 1.17786 USD (↑ 0.05% for 24h, ↑ 1.1 % for 30d)
# USD: 74.59 RUB (↑ 0.0% for 24h, ↑ 5.8 % for 30d)
```

**Timeout**: 10 seconds per request

---

**See also**: [FOREX_DYNAMIC.md](FOREX_DYNAMIC.md) for detailed technical documentation

---

### 9. **OpenAI Balance Monitor** (`src/workers/openai_balance.py`)

Checks OpenAI account balance and displays in digest with low-balance warning.

**Function**: `async get_openai_balance() → Optional[float]`

**How it works**:
1. Tries OpenAI SDK billing API (`client.billing.credit_grants.list()`)
2. Falls back to direct HTTP request to `/v1/billing/credit_grants`
3. Returns balance in USD or `None` if unavailable

**Requirements**:
- OPENAI_API_KEY configured in Doppler
- API key must have billing access (Organization-level keys usually do)
- Graceful fallback: if key lacks permissions, digest still sends without balance

**Display Format**:
```
💳 Баланс OpenAI: $5.42
```

**Alert** (if balance < $0.50):
```
💳 Баланс OpenAI: $0.32
⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!
```

**If Unavailable**: No balance line shown (digest sends normally)

**Timeout**: 10 seconds per request

**See also**: [OPENAI_BALANCE.md](OPENAI_BALANCE.md) for setup and troubleshooting

---

### 9. **Quote of the Day** (`src/workers/quote_of_day.py`)

Fetches inspirational wisdom/quotes to energize the user for the day.

**Function**: `async get_quote_of_day() → Optional[Dict]`

**Output Format**:
```python
{
    "text": str,          # The inspirational quote
    "author": str,        # Who said it
}
```

**Sources**:
1. **Primary**: `quotable.io` API (free, tags: inspirational, wisdom, success)
2. **Fallback**: Hardcoded list of 10 classic inspirational quotes (Steve Jobs, Churchill, etc.)

**Display Format**: `✨ "The quote text" — Author Name`

---

### 10. **Air Quality Monitor** (`src/workers/air_quality.py`)

Monitors air quality in Tbilisi using World Air Quality Index (WAQI) API.

**Function**: `async get_air_quality_tbilisi() → Optional[Dict]`

**Output Format**:
```python
{
    "aqi": int,           # 0-500 (US AQI standard)
    "description": str,   # "Хорошо 😊", "Загрязнено 😷", etc.
    "pm25": float,        # µg/m³ (fine particles)
    "pm10": float,        # µg/m³ (coarse particles)
    "o3": float,          # ppb (ozone)
    "no2": float,         # ppb (nitrogen dioxide)
}
```

**API Source**: `https://api.waqi.info/feed/tbilisi/` (World Air Quality Index)
- Free demo token: works for real-time data
- No authentication needed
- Covers 130+ countries

**AQI Scale**:
- 0-50: Good 😊
- 51-100: Moderate 🙂
- 101-150: Unhealthy for Sensitive Groups 😐
- 151-200: Unhealthy 😷
- 201-300: Very Unhealthy 😤
- 300+: Hazardous 😵

---

### 10. **Product Hunt Aggregator** (`src/workers/product_hunt.py`)

Fetches today's top product from Product Hunt using free RSS feed.

**Function**: `async get_top_product() → Optional[Dict]`

**Output Format**:
```python
{
    "name": str,          # Product name
    "url": str,           # Link to Product Hunt listing
    "description": str,   # First 300 chars of summary
}
```

**Source**: `https://www.producthunt.com/feed` (RSS feed)

---

### 11. **Content Recommender** (`src/workers/content_recommender.py`)

Recommends niche, high-quality content (video, podcast, music) curated for systems engineer + business analyst + AI enthusiast.

**Function**: `async get_content_recommendation() → Optional[Dict]`

**Output Format**:
```python
{
    "type": "video" | "podcast" | "music",
    "title": str,
    "creator": str,
    "description": str,
    "url": str,           # Real YouTube/Spotify/podcast links
    "emoji": str,         # "🎥", "🎙️", or "🎵"
}
```

**Curated Niche Content** (40% videos, 40% podcasts, 20% music):

**Videos** (Systems Design, AI, Data Engineering):
- System Design Deep Dive (Alex Xu)
- Neural Networks for Business (DeepLearning.AI)
- Data Engineering at Scale (DataTalks.Club)
- Kubernetes Architecture (That DevOps Guy)
- Trading Systems Design

**Podcasts** (Architecture, AI trends, Engineering):
- Data Skeptic — critical AI analysis
- Software Engineering Daily — deep technical interviews
- The Gradient — ML trends and research
- Lex Fridman Podcast — conversations with engineers and scientists

**Music** (Focus-optimized, niche genres):
- Synthwave (cyberpunk vibe for analytical work)
- Jazz for Thinking (Bill Evans — piano)
- Drone Ambient (Brian Eno — hours-long focus music)
- Progressive House (Lane 8 — flow state)
- Neo-Classical (Max Richter — deep work)

**Selection**: Weighted random with real working links to YouTube/podcast platforms.

---

### 12. **Task Explainer** (`src/ai/task_explainer.py`)

Generates brief AI explanations for tasks in the digest.

**Function**: `async get_task_explanations(tasks: List[Task]) → Dict[int, str]`

**Input**: List of Task objects for today

**Output**: Dictionary mapping `task.id → explanation_string`

**Explanation Format**:
- One line, 10–15 words per task
- Russian language
- Covers: what (if unclear), when (if time unspecified), why (context)

**Parsing Response**:
```
Задача 1: [explanation text]
Задача 2: [explanation text]
```

**Model Used**: `gpt-4o`

**Fallback**: If generation fails, returns empty dict (no explanations shown)

---

### 13. **Database** (`src/db/`)

SQLite with aiosqlite for async access.

**Models** (`models.py`):

```python
@dataclass
class Task:
    id: int
    user_id: int
    raw_text: str                    # Original user input
    what: str                         # Parsed action
    when_date: Optional[str]          # YYYY-MM-DD
    when_time: Optional[str]          # HH:MM
    proposed_time: Optional[str]      # HH:MM (AI suggestion)
    place: Optional[str]              # Location
    is_urgent: bool                   # true if urgent/ASAP
    is_outdoor: bool                  # true if outdoor
    is_recurring: bool                # true if repeating
    recurrence_pattern: Optional[str] # e.g., "every_monday"
    recurrence_end_date: Optional[str]# YYYY-MM-DD
    constraints: Optional[str]        # Extra conditions
    status: str                       # always "planned" (for notifications only)
    created_at: datetime
    updated_at: datetime

@dataclass
class UserProfile:
    id: int
    user_id: int
    wake_time: str                    # HH:MM (default "08:00")
    sleep_time: str                   # HH:MM (default "23:00")
    timezone: str                     # (default "Asia/Tbilisi")
    preferences: Optional[str]        # Free text
    news_prompt: Optional[str]        # Custom news filter prompt
```

**CRUD Functions** (`database.py`):
```python
async def get_tasks_for_ai_analysis(user_id) → List[Task]
async def get_user_profile(user_id) → UserProfile
async def get_custom_rules(user_id) → List[Tuple[int, str, str]]
async def get_news_prompt(user_id) → Optional[str]
async def save_task(task: Task) → int
async def update_task(task: Task) → None
async def delete_task(task_id: int) → None
```

**Auto-Migration**: Database schema created on first run

---

### 14. **Telegram Handlers** (`src/bot/handlers/`)

Command routing and user interaction.

**Commands Available**:

| Command | Function |
|---------|----------|
| `/info` | List all commands |
| `/start` | Welcome message |
| `/plan <text>` | Add task (free text) |
| `/tasks` | List today's tasks |
| `/me` | Show user profile |
| `/me <text>` | Update preferences |
| `/ai-rules` | View custom rules |
| `/ai-add <rule>` | Add custom rule |
| `/ai-del <id>` | Delete rule |
| `/ai-reset` | Delete all rules |
| `/news_prompt` | Show news prompt |
| `/news_set <text>` | Set custom news prompt |
| `/news_reset` | Reset news prompt |
| `/digest` | Send morning digest now |

**Custom Rules** (`/ai-add`):
- User can define custom planning rules
- Rules injected into task parsing system prompt
- Examples: "спорт только утром", "не планировать в понедельник"
- Stored in database, applied to all future task parsing

---

## Data Flow Examples

### Morning Digest Flow

```
08:00 → APScheduler triggers morning_digest()
  ↓
Load tasks (filter where when_date == today)
  ↓
Fetch user profile + weather (parallel)
  ↓
GPT-4o generates intro (1–2 sentences)
  ↓
Format weather by periods
  ↓
Check holidays (Nager.Date API)
  ↓
Check DST events (calculated)
  ↓
Check GWP works (BeautifulSoup)
  ↓
Fetch news (9 RSS feeds) + filter by keywords
  ↓
Score + sort tasks by importance
  ↓
GPT-4o generates task explanations
  ↓
Fetch exchange rates
  ↓
Build message (all sections)
  ↓
Send to Telegram
```

### Task Planning Flow

```
User: /plan завтра в парк в 15:00
  ↓
Fetch user profile + existing tasks + weather
  ↓
Fetch custom user rules
  ↓
Build system prompt with all context
  ↓
GPT-4o parses task → JSON
  ↓
Save to database
  ↓
Confirm to user
```

---

## Critical Design Decisions

### 1. **No AI-Generated News** (USER REQUIREMENT)
- Previous iteration used GPT to select and rewrite news
- User feedback: fake news, fake links
- **Decision**: Switched to 100% keyword-based filtering
- Only real RSS data with actual source URLs
- Trade-off: Less sophisticated but guaranteed data integrity

### 2. **Real Weather from Multiple Sources**
- Single weather API can fail or be inaccurate
- **Decision**: Fetch from both Open-Meteo and wttr.in, use first successful
- Fallback ensures digest still sends if one service is down

### 3. **SQLite for Simplicity**
- Single file, zero infrastructure, async support via aiosqlite
- No migrations needed (auto-created on first run)
- Trade-off: Single-user per instance

### 4. **Custom User Rules in System Prompt**
- User can add rules like "спорт только утром"
- **Decision**: Inject rules as-is into every task parsing prompt
- GPT-4o follows them naturally without special parsing

### 5. **APScheduler for Morning Digest**
- Runs on same asyncio event loop as Telegram bot
- Triggered by CronTrigger (hour=8, minute=0)
- Can also be triggered manually via `/digest` command

### 6. **Real Exchange Rates, No Hallucination**
- Fetch from actual APIs (CoinGecko, exchangerate-api)
- Format to 5 decimals, strip trailing zeros
- User approved formatting

### 7. **Timeout-First Approach**
- All external API calls have timeout (5–10 seconds)
- Failures are logged but non-fatal
- Partial results acceptable

---

## Environment Setup

### Prerequisites
```bash
python3 --version  # 3.9 or later
brew install doppler  # macOS
```

### Installation
```bash
git clone <repo>
cd notification-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

doppler login
doppler projects  # Verify access
```

### Required Secrets (via Doppler)

**Telegram Credentials:**
```bash
doppler secrets set TELEGRAM_BOT_TOKEN <token>
doppler secrets set TELEGRAM_CHAT_ID <chat-id>
doppler secrets set TELEGRAM_USER_ID <user-id>          # Optional, defaults to TELEGRAM_CHAT_ID
doppler secrets set OPENAI_API_KEY <key>
```

**Webhook Configuration (FastAPI mode):**
```bash
doppler secrets set WEBHOOK_URL https://example.com/telegram/webhook
doppler secrets set WEBHOOK_PORT 8080                    # Port to listen on
doppler secrets set WEBHOOK_SECRET <random-secret-key>   # For validating Telegram requests
```

### Running Locally (Webhook Mode)
```bash
# With Doppler access - runs FastAPI webhook server on WEBHOOK_PORT
PYTHONPATH=. doppler run --project notifications-bot --config dev -- python3 src/bot/main.py

# The server will:
# 1. Delete old webhook from Telegram
# 2. Register WEBHOOK_URL with Telegram
# 3. Listen for updates on 0.0.0.0:WEBHOOK_PORT
# 4. Validate incoming updates with WEBHOOK_SECRET

# For local development, you need:
# - WEBHOOK_URL to be publicly accessible (use ngrok or similar)
# - WEBHOOK_PORT must be accessible from internet
# - WEBHOOK_SECRET for security
```

### Running in Docker
```bash
docker-compose up -d
docker-compose logs -f bot
```

---

## Testing & Validation

### Type Checking
```bash
mypy src/ --strict
```

### Linting
```bash
flake8 src/
pylint src/
```

### Manual Testing
```bash
# Test currency fetch
python3 scripts/test_currency_rate.py

# Test GWP scraper
python3 scripts/test_gwp.py

# Test news fetch
python3 scripts/test_news.py

# Test weather
python3 scripts/test_weather.py

# Trigger digest manually
# Send /digest command to bot
```

---

## Common Issues & Fixes

### 1. **News Not Showing**
- **Cause**: Field name mismatch (`summary` vs `description`)
- **Fix**: Verified in scheduler.py line 162: `news.get("description", "")`

### 2. **GWP Works Not Detected**
- **Cause**: 301 redirects from GWP website
- **Fix**: Added try/except with fallback to URL + '/'

### 3. **Weather Aggregation Fails**
- **Cause**: Open-Meteo timeout/error
- **Fix**: Automatic fallback to wttr.in

### 4. **Tasks Not Parsed Correctly**
- **Cause**: JSON extraction fails
- **Fix**: Handles markdown code blocks and edge cases

### 5. **Digest Sends but Telegram Gets Nothing**
- **Cause**: Message too long (Telegram limit ~4096 chars)
- **Fix**: Split message or trim sections

### 6. **All OpenAI Calls Failing**
- **Cause**: OPENAI_API_KEY missing or invalid
- **Fix**: Verify Doppler secrets: `doppler secrets`

---

## Performance Considerations

### Execution Time (Morning Digest)
- Weather fetch: ~2 seconds
- News fetch: ~8 seconds (9 feeds)
- Task explanations: ~3 seconds
- Rate fetching: ~2 seconds
- **Total expected**: ~15–20 seconds end-to-end

### Database Operations
- All async via aiosqlite (non-blocking)
- Indexes on user_id and when_date
- No N+1 queries

### Memory Usage
- Minimal (no large data structures)
- SQLite file ~100KB per 100 tasks

### Network I/O
- 9 RSS feeds in sequence
- Multiple weather APIs with fallback
- All have timeouts to prevent hangs

---

## OpenAI Models Used

All AI calls use **GPT-4o** (upgraded from gpt-5.4-mini for better quality):

1. **Task Parsing** (`planner_agent.py:310`)
   - Complex free-text task interpretation
   - Requires understanding context, weather, user preferences
   - Model: `gpt-4o`

2. **Morning Digest Intro** (`scheduler.py:63`)
   - Generate 1–2 sentence weather context intro
   - Model: `gpt-4o`

3. **Task Explanations** (`task_explainer.py:51`)
   - Brief 10–15 word explanations per task
   - Model: `gpt-4o`

4. **Morning Digest Generation** (`planner_agent.py:454`)
   - Natural-language summary of tasks
   - Model: `gpt-4o`

5. **Evening Digest Generation** (`planner_agent.py:514`)
   - Evening review and encouragement
   - Model: `gpt-4o`

**Why GPT-4o**: More capable than mini at understanding context, parsing complex free-text, and generating natural language. Better for user-facing features.

---

## Code Guidelines for Claude

When working on this project:

1. **NO HARDCODED FALLBACKS**: If all API sources fail, return `None` (skip block in digest)
   - Better to omit a section than show fake/outdated data
   - Examples: quote_of_day returns None if all APIs fail (no fallback list)
   - This applies to: quotes, products, recommendations, any dynamic content
   
2. **Real Data Only**: All content must be from actual external APIs or RSS feeds
   - Never use AI to generate news — keyword filter or fetch from real sources
   - Never generate fake quotes, products, or recommendations when APIs fail
   
3. **No Hardcoding**: All dynamic data from external APIs, never embed static fallback lists

4. **Async-First**: All I/O operations must be async (httpx, aiosqlite, etc.)

5. **Error Logging**: Log errors with context (URL, status, timeout)

6. **Timeout All Requests**: Default 10 seconds for external APIs

7. **Field Names Matter**: news items have `description`, not `summary`

8. **Markdown Links**: Format news as `[Source](url): text`

9. **Russian Output**: All user-facing text in Russian

10. **Test End-to-End**: Verify digest actually sends to Telegram

11. **Model Choice**: Use `gpt-5.4-mini` for all AI tasks (not gpt-4o)

12. **Disable Link Previews**: All message sending methods must include `disable_web_page_preview=True`
    - Applies to: `send_message()`, `reply()`, `answer()`, `edit_text()`
    - Prevents Telegram from generating link previews in chat
    - Cleaner, faster message display

---

**Last Updated**: May 2026  
**Bot Status**: Fully functional with all features implemented  
**Tested**: All components verified working with real external data sources
