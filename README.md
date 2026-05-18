# Notification Bot with AI Task Planner

Two-in-one Telegram bot:
1. **Currency Monitor**: Tracks EUR/USD, alerts when > 1.18
2. **AI Task Planner**: Free-text tasks → AI parsing → smart scheduling → morning digest

## Quick Start

### Local (requires Doppler)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

doppler login
doppler secrets set TELEGRAM_BOT_TOKEN <token>
doppler secrets set TELEGRAM_CHAT_ID <chat-id>
doppler secrets set OPENAI_API_KEY <key>

python src/main.py
```

### Docker
```bash
docker-compose up --build
```

## Bot Commands

**Tasks:**
| Command | Description |
|---|---|
| `/plan <text>` | Add task from free text |
| `/tasks` | List all tasks |
| `/done <id>` | Mark task as done |
| `/cancel <id>` | Cancel task |

**Profile:**
| Command | Description |
|---|---|
| `/me` | Show profile |
| `/me <text>` | Update preferences |

**AI Rules (NEW!):**
| Command | Description |
|---|---|
| `/ai-rules` | Show all AI rules |
| `/ai-add <rule>` | Add custom rule |
| `/ai-del <id>` | Delete rule |
| `/ai-reset` | Delete all rules |

Examples of rules:
- `/ai-add не планировать в понедельник`
- `/ai-add предпочитаю дневное время (12-17)`
- `/ai-add спорт только утром`
- `/ai-add избегай спортзалов в пятницу`

## Features

**Currency Monitor:**
- Multiple APIs with fallback (no single point of failure)
- EUR/USD > 1.18 → notification
- Checks every 10 minutes
- Dedup: won't spam if rate stays high

**Task Planner (Stage 1 - Foundation):**
- ✓ Free-text task input
- ✓ SQLite persistence
- ✓ User profile/preferences
- ⏳ AI parsing (gpt-5.4-mini) — Stage 2
- ⏳ Smart time suggestions — Stage 3
- ⏳ Morning digest cron — Stage 4

See [CLAUDE.md](CLAUDE.md) for architecture, [PLANNING_FEATURE.md](PLANNING_FEATURE.md) for task planner details, and [AI_RULES_MANAGEMENT.md](AI_RULES_MANAGEMENT.md) for managing AI behavior.
