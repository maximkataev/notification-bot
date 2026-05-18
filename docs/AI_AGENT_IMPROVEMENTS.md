# AI Agent Improvements (Weather + Working Hours + Urgency)

## Overview

Updated AI task planning agent now considers:
1. **Current weather** in Tbilisi (Isani district)
2. **Working hours** context (weekdays 10:00-19:00)
3. **Urgency detection** from task text
4. **Outdoor tasks** that depend on weather
5. **User preferences override** — if user specifies time/urgency, it's respected

## New Fields in Task Model

```python
is_urgent: bool      # Task marked as urgent/ASAP/today
is_outdoor: bool     # Task requires going outside (weather-dependent)
```

## AI System Prompt Key Rules

```
IMPORTANT RULES:
- If user says "urgent" / "today" / "ASAP" / similar → allow any time (override working hours)
- If task is outdoor + rainy/very cold/very hot → suggest covered/protected alternatives or different time
- If user mentions weather-dependent activity → factor in current weather
- If user specifies clear time/date/urgency → use it as-is (user intent overrides defaults)
- Proposed time should be within working hours (10:00-19:00 weekdays) UNLESS:
  a) User explicitly says urgent/ASAP
  b) Task is clearly outside normal hours (dinner → evening)
  c) Task is weather-dependent and current weather blocks preferred time
```

## Weather Data Source

Uses **Open-Meteo API** (free, no key required):
- Temperature, wind speed, weather code
- Location: Tbilisi, Isani (41.7151°N, 44.8271°E)
- Detects: rain, very cold (< 0°C), very hot (> 28°C)

## Example Conversations

### Example 1: Outdoor task, rainy weather
```
User:  /plan завтра сходить в парк Ваке
AI:    [Fetches weather → detects rain]
Response:
  ✓ Задача #5 разобрана:
  
  📝 Сходить в парк Ваке
  📅 2026-05-10
  ⏰ 14:00
  🌦️ Учтена текущая погода
  
  💡 Завтра ожидается дождь. Рекомендую пойти в 14:00 (пик между осадками),
  или перенести на выходные. Возьми зонт!
```

### Example 2: Urgent task with time override
```
User:  /plan СРОЧНО купить лекарство в аптеке
AI:    [Detects urgency]
Response:
  ✓ Задача #6 разобрана:
  
  📝 Купить лекарство в аптеке
  ⏰ 10:00 (срочно) 🔴
  
  💡 Это срочная задача, поэтому предлагаю выполнить в ближайший 
  рабочий час. Большинство аптек открыты с 10:00.
```

### Example 3: Evening task (outside working hours)
```
User:  /plan вечером поужинать в ресторане на Руставели
AI:    [Recognizes meal time → evening]
Response:
  ✓ Задача #7 разобрана:
  
  📝 Поужинать в ресторане на Руставели
  ⏰ 20:00
  📍 Ресторан на Руставели (обычно открыт до 23:00)
  
  💡 Ужин — вечерняя активность. Предлагаю 20:00, когда ресторан 
  полон и атмосфера самая живая.
```

### Example 4: Weather-dependent outdoor with hot weather
```
User:  /plan завтра сходить на пляж
AI:    [Fetches weather → 31°C, sunny]
Response:
  ✓ Задача #8 разобрана:
  
  📝 Сходить на пляж
  📅 2026-05-11
  ⏰ 07:00 или 17:30
  🌦️ Учтена текущая погода
  
  💡 Завтра будет очень жарко (31°C). Предлагаю раннее утро (07:00) 
  или вечер (17:30) для комфорта. Днем слишком жарко.
```

### Example 5: User override — specific time
```
User:  /plan в субботу в 15:00 встреча в кино на Марджанишвили
AI:    [User specified 15:00 → respects it, ignores working hours]
Response:
  ✓ Задача #9 разобрана:
  
  📝 Встреча в кино на Марджанишвили
  📅 2026-05-10 (суббота)
  ⏰ 15:00
  📍 Кинотеатр на Марджанишвили
  
  💡 Вы указали конкретное время (15:00), поэтому я его сохранил.
```

## Implementation Details

### Weather Fetch
```python
async def get_weather_tbilisi() -> Optional[Dict[str, Any]]:
    # Returns: {
    #   "temperature": float,
    #   "is_raining": bool,
    #   "is_very_cold": bool,
    #   "is_very_hot": bool,
    #   ...
    # }
```

### System Prompt Building
```python
def _format_system_prompt(user_profile, weather) -> str:
    # Builds prompt with:
    # 1. Base instructions (parsing, urgency, weather handling)
    # 2. User profile context (wake/sleep times, preferences)
    # 3. Current weather data
    # 4. Working hours context
```

### Task Parsing Flow
```
/plan <text>
  ↓
parse_task(raw_text, user_profile, existing_tasks)
  ↓
get_weather_tbilisi()
  ↓
Build system prompt with weather context
  ↓
Call gpt-5.4-mini with user's task + context
  ↓
Return: {what, when_date, proposed_time, is_urgent, is_outdoor, explanation, ...}
  ↓
Update task in DB with parsed fields
  ↓
Send formatted response to user
```

## Database Schema Changes

Added to `tasks` table:
```sql
is_urgent   INTEGER DEFAULT 0,
is_outdoor  INTEGER DEFAULT 0,
```

## Testing

```bash
# Test with various scenarios
/plan завтра сходить в парк (outdoor, check weather)
/plan СРОЧНО купить продукты (urgency detection)
/plan в 17:00 встреча в офисе (time override)
/plan поужинать в 21:00 (evening outside working hours)
```

## Performance Notes

- Weather API call: ~500ms (cached per parse session)
- AI parsing: ~2-3s (including weather fetch)
- Total /plan response time: ~3-4 seconds

## Future Enhancements

1. **Web Search Tool**: Look up actual business hours (instead of defaults)
2. **Multi-day Forecast**: Consider weather for future dates
3. **Geo-aware Suggestions**: Different working hours for different locations
4. **User Timezone Override**: Allow non-Tbilisi users
5. **Cache Weather**: Don't refetch within 30 minutes
