# News Digest Feature

## Overview

Every morning at 08:00, the digest now includes 2 selected news stories from the last 8 hours, chosen by AI based on your interests.

**Example morning digest:**
```
☀️ Доброе утро! В Тбилиси хорошая погода (22°C). 
Совет дня: делай сложные дела утром когда в тонусе.

📰 Интересные новости:
• ООН опубликовала новый доклад об изменении климата. 
  Выбросы СО2 выросли на 5% в 2025 году.
• Зеленский назвал условия переговоров с Путиным. 
  Обсуждается возможность саммита в мае.

📋 Ваши дела:
• Купить продукты (до 14:00)
• Встреча с боссом (16:00) 🔴
```

## News Sources (9 Free Feeds)

1. **BBC News** — основные мировые новости
2. **Reuters** — новостное агентство
3. **AP News** — Associated Press
4. **The Guardian** — английские и мировые новости
5. **Al Jazeera** — новости с разных регионов
6. **Deutsche Welle** — немецкое вещание
7. **NPR** — американское радио
8. **CNN** — американские новости
9. **Financial Times** — деловые новости

## How It Works

### Flow
```
08:00 (утро)
  ↓
Получить последние новости за 8 часов (00:00-08:00)
  ↓
AI: выбирает 2 самые интересные по твоим критериям
  ↓
AI: переписывает каждую в 1-2 предложения
  ↓
Добавить в дайджест перед списком дел
```

### Customization

**Посмотреть текущий промпт:**
```
/news_prompt
```

**Установить свой промпт:**
```
/news_set Выбери только новости политики и экономики. 
Игнорируй спорт и развлечения.
```

**Вернуть default:**
```
/news_reset
```

## Default Prompt

```
Ты — редактор новостного дайджеста. Твоя задача:
1. Выбрать 2 самые важные и интересные новости из списка
2. Переписать каждую в 1-2 предложения максимум
3. Сосредоточиться на экономике, политике, культуре и спорте
4. Быть объективным, избегать sensationalism
5. Ответить на русском
```

## Custom Prompt Examples

**Только бизнес:**
```
/news_set Выбери только новости о экономике и бизнесе. 
Фокусируйся на курсах валют, IPO, слияниях компаний.
```

**Только политика:**
```
/news_set Выбери только политические новости. 
Интересуй конфликты, выборы, дипломатические события.
```

**Только культура и спорт:**
```
/news_set Выбери интересные новости о культуре, кино, 
музыке, спорте. Игнорируй политику и экономику.
```

**Новости Грузии:**
```
/news_set Выбери новости связанные с Грузией и 
региональные новости Кавказа.
```

## Implementation Details

### Files Added
- `src/workers/news_fetcher.py` — fetch from RSS feeds
- `src/ai/news_selector.py` — AI selection and summarization
- `src/bot/handlers/news_handler.py` — /news_* commands
- Updated: `src/bot/scheduler.py` — integrated news into digest
- Updated: `src/db/database.py` — added news_config table

### Database Changes
New table: `news_config`
```sql
CREATE TABLE news_config (
    user_id       INTEGER PRIMARY KEY,
    custom_prompt TEXT,
    updated_at    TEXT DEFAULT (datetime('now'))
)
```

### Cost Optimization
- **Single AI call** — fetch + select + summarize in one request
- **Prompt caching** — 90% cheaper on system prompt
- **Limited context** — only recent 20 news items sent to AI
- **Per-user prompt** — stored in DB for customization

**Cost per morning digest:** ~$0.0005 (with caching)

## Commands

### /info
Shows all available commands in the bot:
```
/info
```

### /news_prompt
Show current news selection prompt:
```
/news_prompt
```

### /news_set
Set custom news selection criteria:
```
/news_set <your criteria>
```

### /news_reset
Reset to default prompt:
```
/news_reset
```

## Testing

To test news fetching locally:
```python
import asyncio
from src.workers.news_fetcher import get_recent_news

async def test():
    news = await get_recent_news(hours=8)
    print(f"Found {len(news)} news items")
    for item in news[:3]:
        print(f"- {item['title']} ({item['source']})")

asyncio.run(test())
```

## Troubleshooting

**No news showing in digest?**
- Check internet connection (RSS feeds require network access)
- Some feeds might be temporarily unavailable
- Bot will gracefully skip news section if fetching fails

**Want to disable news?**
- Set empty prompt: `/news_set ` (space only)
- Or just ignore the news section in digest

**Prompt not working as expected?**
- Check spelling and grammar
- Be specific about what to include/exclude
- Examples work better than general rules
- Reset and try again: `/news_reset` then `/news_set <new>`

## Future Enhancements

- [ ] News categories preference storage
- [ ] Multiple daily news digests (morning + evening)
- [ ] News filtering by language
- [ ] News caching to avoid duplicate stories
- [ ] Breaking news alerts
- [ ] Personalized news ranking by engagement
