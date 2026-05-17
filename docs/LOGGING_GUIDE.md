# Logging Guide

Весь проект обильно покрыт логами для отладки и мониторинга.

## Уровни Логирования

| Level | Когда Использовать | Пример |
|-------|-------------------|--------|
| **DEBUG** | Детальная информация для отладки | `logger.debug(f"Loading tasks: {len(tasks)}")` |
| **INFO** | Важные события в процессе | `logger.info(f"✓ Task #5 saved")` |
| **WARNING** | Что-то странное, но не критичное | `logger.warning(f"Feed timeout, skipping")` |
| **ERROR** | Ошибка, требующая внимания | `logger.error(f"✗ AI parsing failed: {e}")` |

## Что Логируется

### 1. **Task Management** (plan_handler.py)
```
📝 /plan command from user 123: в пн вечером концерт...
  ✓ Task #5 saved
  Context loaded: 3 tasks, 2 rules
  Calling AI to parse task
  Reminder pattern detected - creating 2 tasks
  ✓ Reminder task #6 created
✓ Task(s) [5, 6] parsed and sent to user 123
```

### 2. **AI Parsing** (planner_agent.py)
```
  Parsing task: 'в пн вечером концерт...'
  Calling GPT-4o with cached system prompt
  AI response: 150→45 tokens
✓ Tasks parsed (with reminder): 'Концерт' + reminder
```

### 3. **News Fetching** (news_fetcher.py)
```
Starting news fetch from 9 RSS feeds (last 8h)
  Fetching: https://feeds.bbci.co.uk/news/rss.xml
  ✓ HTTP 200: BBC News
  Parsed 50 entries from BBC News
  Skipping old entry: 2026-05-01T15:30:00
  ✓ BBC News: 5 items added
✓ News fetch complete: 12 items, 9/9 feeds OK, 0 failed
```

### 4. **News Selection** (news_selector.py)
```
Selecting top 2 from 12 news items
Using default prompt
AI response received: 450→120 tokens
  1. ООН опубликовала доклад об изменении климата... (Reuters)
  2. Зеленский назвал условия переговоров с Путиным... (Al Jazeera)
✓ Selected 2 news items for digest
```

### 5. **Morning Digest** (scheduler.py)
```
🌅 Starting morning digest for user 123
  Tasks: 4, Profile loaded, Weather: 22°C
  Weather description: переменная облачность, 22°C
  Generating intro via AI
  Intro generated: Доброе утро! В Тбилиси хорошая погода...
  News items fetched: 12
  News prompt: default
  News 1: ООН опубликовала доклад об изменении климата...
  News 2: Зеленский назвал условия переговоров с Путиным...
  Sending digest (35 lines, 1250 chars)
✓ Morning digest sent successfully for user 123
```

### 6. **Database Operations** (database.py)
```
Saving task for user 123: в пн вечером концерт...
✓ Task #5 saved to DB

Loading AI analysis tasks for user 123 (today: 2026-05-09)
Found 4 tasks for AI analysis

Loading news prompt for user 123
✓ Custom news prompt found for user 123

Updating news prompt for user 123: Только политика...
✓ News prompt updated for user 123
```

### 7. **Secrets Management** (doppler.py)
```
Fetching secret: TELEGRAM_BOT_TOKEN
✓ Secret fetched: TELEGRAM_BOT_TOKEN

Fetching all secrets from Doppler
✓ Loaded 3 secrets from Doppler
```

### 8. **Clarification Flow** (plan_handler.py)
```
💬 Clarification reply for task #5 from user 123: в пн вечером
  Loading task #5
  Task is not awaiting clarification
  (или if pending)
  Loading context for task #5 re-parsing
  Clarified text: в пн вечером концерт...
  [Уточнение: в 19:00]...
  Re-parsing task #5 with AI
  ✓ Task #5 re-parsed successfully
  Sending clarification response (12 lines)
✓ Clarification processed and sent for task #5
```

## Запуск с Разными Уровнями Логирования

```bash
# По умолчанию (INFO + выше)
python src/main.py

# Включить DEBUG логи
LOGLEVEL=DEBUG python src/main.py

# Только WARNING и выше (меньше шума)
LOGLEVEL=WARNING python src/main.py

# Только ERROR
LOGLEVEL=ERROR python src/main.py
```

## Формат Логов

```
2026-05-09 08:00:01 | src.bot.scheduler | INFO | 🌅 Starting morning digest for user 123
2026-05-09 08:00:01 | src.ai.planner_agent | DEBUG | Parsing task: 'в пн вечером концерт...'
2026-05-09 08:00:02 | src.ai.planner_agent | INFO | ✓ Task parsed: 'Концерт'
2026-05-09 08:00:02 | src.workers.news_fetcher | INFO | ✓ News fetch complete: 12 items
2026-05-09 08:00:03 | src.bot.scheduler | INFO | ✓ Morning digest sent successfully
```

## Emoji Indicators

| Emoji | Meaning |
|-------|---------|
| ✓ | Success, operation completed |
| ✗ | Failure, error occurred |
| 📝 | User input (commands, messages) |
| 🌅 | Morning digest started |
| 📰 | News fetch/selection |
| 💬 | Clarification/reply |
| 🔄 | Processing in progress |
| ❌ | Critical error |

## Debugging Tips

### 1. Отследить конкретную задачу
```bash
python src/main.py 2>&1 | grep "Task #5"
```

### 2. Увидеть все DEBUG логи для новостей
```bash
LOGLEVEL=DEBUG python src/main.py 2>&1 | grep -E "(news|NEWS)"
```

### 3. Отследить ошибки
```bash
python src/main.py 2>&1 | grep -E "ERROR|✗"
```

### 4. Полный лог с timestamp
```bash
python src/main.py 2>&1 | tee bot_$(date +%Y%m%d_%H%M%S).log
```

### 5. Следить за новыми логами в реальном времени
```bash
tail -f bot_20260509_080000.log | grep INFO
```

## Log Files Setup (Optional)

Для сохранения логов в файл, добавь в main.py:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
```

## Common Issues & How to Debug

### "Task not found or doesn't belong to user"
```
Ищи в логах: "Task #X not found"
Проверь: user_id совпадает? Task статус правильный?
```

### "AI parsing failed"
```
LOGLEVEL=DEBUG для полного AI response
Ищи: "AI response received: X→Y tokens"
Проверь: JsonDecodeError в логах?
```

### "No news showing"
```
Ищи: "News fetch complete: X items"
Если 0: RSS feeds недоступны или нет новостей за 8 часов
Если есть но не selected: AI selection вернула None
```

### "Digest sent but looks wrong"
```
Ищи: "Sending digest (X lines, Y chars)"
LOGLEVEL=DEBUG для debugging каждого компонента
```
