# Implementation Summary: News Digest + /info Command

## What's New

### 1. Morning News Digest 📰
Every day at 08:00, the digest now includes 2 AI-selected news stories from the last 8 hours.

**Example:**
```
☀️ Доброе утро! В Тбилиси хорошая погода (22°C).

📰 Интересные новости:
• ООН опубликовала доклад об изменении климата. 
  Выбросы СО2 выросли на 5% в 2025 году.
• Зеленский назвал условия переговоров с Путиным. 
  Обсуждается саммит в мае.

📋 Ваши дела:
• [tasks...]
```

### 2. News Customization Commands
- `/news_prompt` — show current selection criteria
- `/news_set <criteria>` — set custom criteria
- `/news_reset` — back to default

**Examples:**
```
/news_set Только новости экономики и политики
/news_set Выбери интересные события в Грузии
/news_reset
```

### 3. Help Command /info
Shows all available commands in the bot with examples.

```
/info
```

## Files Created

| File | Purpose |
|------|---------|
| `src/workers/news_fetcher.py` | Fetch from 9 RSS feeds |
| `src/ai/news_selector.py` | AI selection + summarization |
| `src/bot/handlers/news_handler.py` | `/news_*` commands |
| `NEWS_DIGEST_FEATURE.md` | Complete news feature docs |

## Files Modified

| File | Changes |
|------|---------|
| `src/bot/scheduler.py` | Added news to morning_digest |
| `src/bot/main.py` | Added `/info` command, news_handler router |
| `src/db/database.py` | Added `news_config` table + functions |
| `requirements.txt` | Added `feedparser` library |
| `CLAUDE.md` | Updated with new commands + architecture |

## News Sources (9 Free RSS Feeds)

1. BBC News
2. Reuters
3. AP News
4. The Guardian
5. Al Jazeera
6. Deutsche Welle
7. NPR
8. CNN
9. Financial Times

## Database Schema

New table: `news_config`
```sql
CREATE TABLE news_config (
    user_id       INTEGER PRIMARY KEY,
    custom_prompt TEXT,
    updated_at    TEXT DEFAULT (datetime('now'))
)
```

Stores custom news selection prompts per user. If NULL, uses default.

## Cost Optimization

✅ **Single AI call** — fetch + select + summarize together  
✅ **Prompt caching** — 90% discount on system prompt  
✅ **Limited context** — only recent 20 items  
✅ **Per-user customization** — no extra calls

**Cost per digest:** ~$0.0005 (with caching)

## Testing

### Quick Test RSS Fetch
```python
import asyncio
from src.workers.news_fetcher import get_recent_news

async def test():
    news = await get_recent_news(hours=8)
    print(f"Found {len(news)} items")
    for item in news[:2]:
        print(f"- {item['title']} ({item['source']})")

asyncio.run(test())
```

### Test News Selection
```python
import asyncio
from src.ai.news_selector import select_and_summarize_news
from src.workers.news_fetcher import get_recent_news

async def test():
    news = await get_recent_news(hours=8)
    selected = await select_and_summarize_news(news)
    for item in selected:
        print(f"✓ {item['title']}")
        print(f"  {item['summary']}")

asyncio.run(test())
```

## Commands Summary

### Task Management
- `/plan <text>` — add task (supports "напомни X" for 2 tasks)
- `/tasks` — list all
- `/done <id>` — mark done
- `/cancel <id>` — cancel

### User Profile
- `/me` — show profile
- `/me <text>` — update preferences

### AI Rules
- `/ai-rules` — show all rules
- `/ai-add <rule>` — add rule
- `/ai-del <id>` — delete rule
- `/ai-reset` — delete all

### News
- `/news_prompt` — show current prompt
- `/news_set <criteria>` — set custom
- `/news_reset` — reset to default

### Help
- `/start` — welcome
- `/info` — all commands

## Morning Digest Flow

```
08:00 Trigger
  ↓
Get 8-hour news window (00:00-08:00)
  ↓
Fetch from 9 RSS feeds (max 10/feed)
  ↓
Get user's custom prompt (or default)
  ↓
AI: select 2 + summarize (single call, cached)
  ↓
Generate intro (weather + insight)
  ↓
Append news (📰 section)
  ↓
Append tasks (📋 section)
  ↓
Send to Telegram
```

## Backwards Compatibility

✅ All existing commands still work  
✅ No breaking changes to task parsing  
✅ News is optional (fails gracefully if unavailable)  
✅ Default prompt used if no custom set  

## What If News Fetching Fails?

- RSS feeds timeout → skip news section, show rest of digest
- AI selection fails → skip news section, show rest of digest
- No recent news found → skip news section, show rest of digest

Always prioritize showing tasks + intro, never break the digest.

## Next Features (Optional)

- [ ] Evening news digest (19:00)
- [ ] Per-category news preferences
- [ ] Breaking news alerts
- [ ] News in English + Russian
- [ ] Trending topics summary
- [ ] News filtering by sentiment
