# Architecture: notification-bot

Полная архитектура бота с описанием всех компонентов.

## 🏗️ High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      OVHCloud VPS                            │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Docker Container: notification-bot                   │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Telegram Bot (aiogram 3.x)                      │ │ │
│  │  │  - Polling for commands (/start, /plan, etc)    │ │ │
│  │  │  - Route messages to handlers                   │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                      ↓                                 │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Handlers (Router-based)                         │ │ │
│  │  │  - /plan → plan_handler (task parsing)          │ │ │
│  │  │  - /tasks → tasks_handler (list today's)        │ │ │
│  │  │  - /digest → digest_handler (manual trigger)    │ │ │
│  │  │  - /me, /info, /ping, /debug                    │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Scheduler (APScheduler)                         │ │ │
│  │  │  - Morning Digest (08:00 daily)                 │ │ │
│  │  │  - Orchestrates all data fetching               │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Background Monitors (Async Tasks)               │ │ │
│  │  │  - Currency Monitor (EUR/USD tracking)           │ │ │
│  │  │  - Water Cut Monitor (Vazha Iverievi street)     │ │ │
│  │  │  - Football Matches (Barcelona/Real Madrid)      │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Database (SQLite)                               │ │ │
│  │  │  - Tasks table                                  │ │ │
│  │  │  - User profiles                                │ │ │
│  │  │  - Custom rules & settings                      │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  AI/ML (gpt-5.4-mini)                                  │ │ │
│  │  │  - Task parsing (free-text → JSON)              │ │ │
│  │  │  - Intro generation (weather context)           │ │ │
│  │  │  - News selection (keyword-based filtering)     │ │ │
│  │  │  - Task explanations (brief summaries)          │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Workers (Data Fetching)                         │ │ │
│  │  │  - news_fetcher (11 RSS feeds)                  │ │ │
│  │  │  - weather_aggregator (Open-Meteo + wttr.in)    │ │ │
│  │  │  - rates_fetcher (BTC, ETH, EUR, RUB)           │ │ │
│  │  │  - gwp_checker (water/power works - scraping)   │ │ │
│  │  │  - holidays (Nager.Date API)                    │ │ │
│  │  │  - air_quality (WAQI)                           │ │ │
│  │  │  - product_hunt (RSS feed)                      │ │ │
│  │  │  - quote_of_day (quotable.io + fallback)        │ │ │
│  │  │  - content_recommender (curated list)           │ │ │
│  │  │  - currency_monitor (EUR/USD alerts)            │ │ │
│  │  │  - water_cut_monitor (water outage alerts)      │ │ │
│  │  │  - football_matches (match tracking)            │ │ │
│  │  │  - todoist_client (Todoist API integration)     │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │  Logging                                         │ │ │
│  │  │  - JSON to stdout (docker logs)                 │ │ │
│  │  │  - Readable to file (log.log)                   │ │ │
│  │  │  - Separate error stream (stderr)               │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  Volumes:                                                    │
│  - /app/data → /opt/notification-bot/data (SQLite)         │
│  - /app/logs → /opt/notification-bot/logs (log.log)        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
         ↑                                              ↑
         │                                              │
    Telegram API                          External APIs:
    (polling)                             - OpenAI (gpt-5.4-mini)
                                         - exchangerate-api
                                         - CoinGecko
                                         - Open-Meteo
                                         - wttr.in
                                         - GWP website (scrape)
                                         - WAQI
                                         - Nager.Date
                                         - API-Football
                                         - Todoist API
                                         - etc.
```

## 📁 Project Structure

```
notification-bot/
├── src/
│   ├── bot/
│   │   ├── main.py                     # Bot entry point, dispatcher, monitors
│   │   ├── scheduler.py                # Morning digest orchestration
│   │   └── handlers/
│   │       ├── plan_handler.py         # /plan command → task parsing
│   │       ├── tasks_handler.py        # /tasks command
│   │       ├── profile_handler.py      # /me command (user settings)
│   │       ├── ai_handler.py           # /ai-* (custom rules)
│   │       ├── news_handler.py         # /news_* (news prompts)
│   │       └── digest_handler.py       # /digest (manual trigger)
│   │
│   ├── ai/
│   │   ├── planner_agent.py            # gpt-5.4-mini task parsing
│   │   ├── task_explainer.py           # Generate task explanations
│   │   ├── weather_aggregator.py       # Multi-source weather
│   │   └── news_processor.py           # News selection with AI
│   │
│   ├── workers/
│   │   ├── news_fetcher.py             # 11 RSS feeds
│   │   ├── weather_aggregator.py       # Weather aggregation
│   │   ├── rates_fetcher.py            # Crypto + forex rates
│   │   ├── gwp_checker.py              # Water/power works (scraping)
│   │   ├── holidays.py                 # Holiday tracking
│   │   ├── air_quality.py              # Air quality API
│   │   ├── product_hunt.py             # Product Hunt RSS
│   │   ├── quote_of_day.py             # Inspirational quotes
│   │   ├── content_recommender.py      # Content suggestions
│   │   ├── currency_monitor.py         # EUR/USD alerts (background task)
│   │   ├── water_cut_monitor.py        # Water outage alerts (background task)
│   │   ├── football_matches.py         # Football match tracking
│   │   └── todoist_client.py           # Todoist integration
│   │
│   ├── db/
│   │   ├── models.py                   # Task, UserProfile dataclasses
│   │   └── database.py                 # aiosqlite CRUD
│   │
│   └── utils/
│       ├── doppler.py                  # Secrets retrieval
│       ├── logging_config.py           # JSON + file logging
│       ├── tbc_bank.py                 # Exchange rate APIs
│       └── telegram.py                 # Message sending utility
│
├── data/
│   └── tasks.db                        # SQLite (auto-created)
│
├── logs/
│   └── log.log                         # Application logs
│
├── scripts/
│   ├── deploy.sh                       # Manual deployment script
│   └── redeploy-notification-bot.sh    # VPS redeploy script
│
├── .github/
│   └── workflows/
│       └── deploy.yml                  # GitHub Actions CI/CD
│
├── Dockerfile                          # Build image with Playwright
├── docker-compose.yml                  # Docker Compose config
├── requirements.txt                    # Python dependencies
├── CLAUDE.md                           # Project instructions
├── DEPLOYMENT_READY.md                 # Deployment status
├── DEPLOY_SETUP.md                     # Setup instructions
├── DEPLOY_CHECKLIST.md                 # Pre-deployment checklist
├── README_DEPLOY.md                    # Quick start
├── VPS_SETUP.sh                        # VPS initialization script
├── ARCHITECTURE.md                     # This file
└── .gitignore
```

## 🔄 Data Flow: Morning Digest (08:00)

```
08:00 → APScheduler triggers morning_digest()
  ↓
Load user profile + preferences from SQLite
  ↓
Fetch weather (Open-Meteo + wttr.in fallback)
  ↓
Generate weather intro (gpt-5.4-mini)
  ↓
Fetch quote of the day (quotable.io + fallback)
  ↓
Fetch air quality (WAQI)
  ↓
Check holidays (Nager.Date API)
  ↓
Check GWP works (Playwright scraping)
  ↓
Fetch news (11 RSS feeds, 12h window)
  ↓
Select news with gpt-5.4-mini (keyword-based + exclusions)
  ↓
Load today's tasks from SQLite
  ↓
Score + sort tasks (urgency, outdoor, timed, dated)
  ↓
Generate task explanations (gpt-5.4-mini)
  ↓
Fetch exchange rates (crypto + forex with changes)
  ↓
Fetch top Product Hunt product
  ↓
Get content recommendation (curated list)
  ↓
Check OpenAI balance (billing API)
  ↓
Build final message (all sections)
  ↓
Split if >4000 chars (Telegram limit)
  ↓
Send to Telegram
```

## 🔄 Data Flow: Task Parsing (/plan command)

```
User: /plan завтра в парк в 15:00
  ↓
Load user profile (wake/sleep, timezone, preferences)
  ↓
Load existing tasks (context for conflicts)
  ↓
Load custom user rules (e.g., "спорт только утром")
  ↓
Fetch current weather (for outdoor tasks)
  ↓
Build system prompt (with all context)
  ↓
Call gpt-5.4-mini with system prompt + task text
  ↓
Extract JSON from response (handles markdown blocks)
  ↓
Validate JSON schema
  ↓
Save to SQLite
  ↓
Send confirmation to user
```

## 🔄 Background Monitors (Async)

```
┌─────────────────────────────────────────┐
│  Currency Monitor (every 5 minutes)     │
├─────────────────────────────────────────┤
│ - Fetch EUR/USD rate (exchangerate-api) │
│ - Check if > 1.18 (user threshold)      │
│ - Alert once per 24h if true            │
│ - Log result                            │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Water Cut Monitor (every 1 hour)       │
├─────────────────────────────────────────┤
│ - Scrape GWP website (Playwright)       │
│ - Check Vazha Iverievi street           │
│ - Alert once per day if found           │
│ - Log result                            │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Football Matches (on-demand)           │
├─────────────────────────────────────────┤
│ - Query API-Football for today's matches│
│ - Prioritize Barcelona/Real Madrid      │
│ - Return formatted match data           │
│ - (Can be added to digest)              │
└─────────────────────────────────────────┘
```

## 🔌 External APIs & Sources

### Data Fetching
| Service | Purpose | Free | Timeout |
|---------|---------|------|---------|
| OpenAI | Task parsing, digests | No | 30s |
| Open-Meteo | Weather (primary) | Yes | 10s |
| wttr.in | Weather (fallback) | Yes | 10s |
| WAQI | Air quality | Yes* | 10s |
| Nager.Date | Holidays/DST | Yes | 5s |
| CoinGecko | Crypto rates | Yes | 10s |
| exchangerate-api | Forex rates | Yes | 10s |
| Yahoo Finance | Forex history | Yes | 10s |
| 11 RSS feeds | News | Yes | 10s each |
| GWP website | Water/power works | N/A | 10s |
| quotable.io | Quotes | Yes | 5s |
| Product Hunt | Top product | Yes | 5s |
| API-Football | Football matches | Yes | 10s |
| Todoist API | Task sync | No | 10s |

### Secrets (Doppler)
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `TELEGRAM_CHAT_ID` — Chat to send digest to
- `TELEGRAM_USER_ID` — User ID (optional, fallback to chat_id)
- `OPENAI_API_KEY` — gpt-5.4-mini API key
- `NOTIFICATION_BOT_DOPPLER_TOKEN` — Doppler token for this app

## 🗄️ Database Schema

### Tasks Table
```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    raw_text TEXT,                  -- Original user input
    what TEXT,                      -- Parsed action
    when_date TEXT,                 -- YYYY-MM-DD
    when_time TEXT,                 -- HH:MM
    proposed_time TEXT,             -- HH:MM (AI suggestion)
    place TEXT,                     -- Location
    is_urgent BOOLEAN,              -- true if urgent
    is_outdoor BOOLEAN,             -- true if outdoor
    is_recurring BOOLEAN,           -- true if repeating
    recurrence_pattern TEXT,        -- e.g., "every_monday"
    recurrence_end_date TEXT,       -- YYYY-MM-DD
    constraints TEXT,               -- Extra conditions
    status TEXT,                    -- always "planned"
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

### UserProfile Table
```sql
CREATE TABLE user_profiles (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE,
    wake_time TEXT,                 -- HH:MM (default "08:00")
    sleep_time TEXT,                -- HH:MM (default "23:00")
    timezone TEXT,                  -- (default "Asia/Tbilisi")
    preferences TEXT,               -- Free text
    news_prompt TEXT,               -- Custom news filter
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

## 📊 Key Features

### Async/Concurrency
- Single asyncio event loop
- All I/O (HTTP, database, Telegram) is async
- Background monitors run in parallel with polling
- No blocking operations

### Error Handling
- All external API calls have timeouts (5-10s)
- Failures logged but non-fatal
- Graceful degradation (skip failed components)
- Partial results acceptable

### Logging
- JSON format to stdout (for docker logs)
- Readable format to `/app/logs/log.log`
- Separate error stream to stderr
- Configurable log level (DEBUG, INFO, WARNING, ERROR)

### Scalability
- Single-user per bot instance (1:1 bot-to-user)
- SQLite for simplicity (no DB server needed)
- Can handle large number of tasks/rules
- No N+1 queries

---

**Версия**: май 2026  
**Язык**: Python 3.11  
**Framework**: aiogram 3.x  
**Database**: SQLite3
