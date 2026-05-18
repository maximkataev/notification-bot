# AI Task Planning Feature

## Overview

The AI task planner helps you organize your tasks intelligently. Send a task in free text, and the AI:
1. Extracts what needs to be done
2. Identifies date, time, and location
3. Looks up business hours if needed
4. Proposes optimal timing based on your profile
5. Asks clarifying questions if data is missing

## Example Workflow

### User Input
```
/plan в субботу отправить открытки из почтового отделения Исани
```

### AI Analysis
The AI agent returns:
```json
{
  "what": "отправить открытки",
  "when_date": "2026-05-10",
  "place": "почтовое отделение Исани",
  "place_hours": {"sat": "10:00-14:00"},
  "proposed_time": "12:30",
  "explanation": "Почтовое отделение работает по субботам с 10:00 до 14:00. 
                  Вы обычно просыпаетесь в 11:00, поэтому оптимально сходить в 12:30."
}
```

### Bot Response
```
✓ Задача сохранена (ID: 1)

Отправить открытки из почтового отделения Исани
📅 Суббота, 2026-05-10
⏰ 12:30
📍 Почтовое отделение Исани (работает 10:00-14:00)

Рекомендация: Помещение открывается в 10:00, вы просыпаетесь в 11:00, 
поэтому оптимально сходить в 12:30 (середина дня, перед закрытием).
```

## Data Model

### Task Record
```python
@dataclass
class Task:
    id: int                      # Auto-generated
    user_id: int                 # From Telegram
    raw_text: str                # Original user input
    what: str                    # Extracted action
    when_date: str               # ISO date YYYY-MM-DD
    when_time: str               # HH:MM
    place: str                   # Location name
    place_hours: str             # JSON {"mon": "10-18", ...}
    proposed_time: str           # AI-suggested HH:MM
    status: str                  # planned | done | cancelled
    clarification_pending: bool  # Awaiting user response
    clarification_question: str  # What to ask user
    created_at: str              # Timestamp
    updated_at: str              # Last modified
```

### User Profile
```python
@dataclass
class UserProfile:
    user_id: int           # From Telegram
    wake_time: str         # Default: 09:00
    sleep_time: str        # Default: 23:00
    preferences: str       # Freeform: "не люблю утром", "предпочитаю дневное время"
    timezone: str          # Default: Asia/Tbilisi
    updated_at: str
```

## AI Agent System Prompt

```
You are a personal AI assistant for task planning. Your job is to:
1. Parse free-text task descriptions
2. Extract structured data: what, when (date/time), place, constraints
3. Check for missing information and ask clarifying questions
4. Propose optimal timing considering user profile and existing tasks
5. Explain your suggestions clearly

Rules:
- NEVER invent dates, times, or place opening hours — ask if unsure
- If a place is mentioned, ALWAYS attempt to lookup its opening hours
- Respond in the same language as the user input
- Be precise and concise
- Provide explanations for time suggestions
```

## Implementation Stages

### Stage 1: Foundation (Done ✓)
- ✓ Switch to aiogram
- ✓ SQLite database + models
- ✓ Basic commands: /plan, /tasks, /done, /cancel, /me
- ✓ Docker setup

### Stage 2: AI Parsing (In Progress)
- [ ] Wire AI agent to /plan handler
- [ ] Parse task → structured JSON
- [ ] Save parsed fields to DB
- [ ] Clarification questions flow (reply-to)

### Stage 3: Smart Scheduling
- [ ] Web search for business hours
- [ ] Consider existing tasks when proposing time
- [ ] Apply user profile preferences

### Stage 4: Morning Digest
- [ ] APScheduler daily cron (default 08:00)
- [ ] Filter today's tasks
- [ ] Generate natural-language summary
- [ ] Send to Telegram

## API Integration Points

### gpt-5.4-mini (OpenAI)
- **Model**: gpt-5.4-mini
- **Input**: raw task text + user profile context
- **Output**: structured JSON + explanation
- **Tools**: Future: web search, business hours lookup

### Business Hours Lookup
- **Data Source**: Web search (httpx) or hardcoded database
- **Purpose**: Verify place opening hours when planning
- **Cache**: Could cache in DB to minimize API calls

## Notes for Development

1. **Clarifications**: When AI returns `needs_clarification=true`, store the task with `clarification_pending=1` and wait for user's next message to re-parse.

2. **Timezone Handling**: All dates should be stored in user's timezone (default: Asia/Tbilisi) but can be overridden per user.

3. **Morning Digest**: Should be personalized per user — send only their tasks, in their preferred language/tone.

4. **Rate Limiting**: Consider OpenAI rate limits; cache user profiles in memory to avoid redundant API calls.

5. **Error Handling**: If AI can't parse, fall back to asking user specific questions rather than rejecting the input.
