# Task Parsing Improvements

## Changes Made

### 1. Improved System Prompt (src/ai/planner_agent.py)
Added explicit rule for parsing flexible deadlines without asking for clarification:

```
- PARSE FLEXIBLE DEADLINES: if user says "можно X" / "или X" / "если нет X" / "в крайнем случае X":
  a) Use the FIRST mentioned date/time as when_date/when_time
  b) Put the flexible option ("можно в среду") in constraints field
  c) Do NOT ask clarification — all info is already in the text
```

This ensures the AI understands patterns like:
- "в пн вечером забрать посылки, можно в среду" 
- "завтра в 14:00, если нет — в 16:00"
- "в понедельник, или вторник если некогда"

### 2. Added Reply-to Clarification Handler (src/bot/handlers/plan_handler.py)
Implemented `clarification_reply` handler that:
- Detects when user replies to a bot message with clarification
- Extracts task ID from the bot's original message
- Re-parses the task with the user's clarification appended
- Updates task fields with the new parsed result
- Shows updated task info to user

**Flow:**
```
User: /plan задача без даты
Bot: ✓ Задача #5 разобрана... ❓ Уточнение: Когда выполнить?
User: replies "завтра в 15:00"
Bot: ✓ Задача #5 обновлена... ⏰ 15:00
```

## Test Scenarios

### Scenario 1: Task with flexible deadline (NO clarification needed)
```
User: /plan после качалки в пн вечером забрать посылки, можно в среду

Expected behavior:
- when_date: понедельник (monday of next week)
- when_time: ~19:00 (evening)
- is_urgent: false
- constraints: "можно в среду"
- needs_clarification: false

Result: Task is fully parsed without asking questions
```

### Scenario 2: Task with missing info (clarification needed)
```
User: /plan купить что-то важное

Expected behavior:
- needs_clarification: true
- clarification_question: "Когда нужно купить? Сегодня, завтра или на какую дату?"

User replies: "на субботу"

Result: Task is re-parsed with the clarification
```

### Scenario 3: Weather-dependent task
```
User: /plan прогулка в парке

Expected behavior:
- is_outdoor: true
- Weather context is considered in proposed_time
- Example: If rainy, might suggest covered areas or different time
```

## Database Schema
The tasks table already supports:
- `clarification_pending` (INTEGER): 1 if waiting for user clarification, 0 otherwise
- `clarification_question` (TEXT): The question asked to user, or NULL

## Router Order Note
The `clarification_reply` handler is a generic message handler that:
1. Early-returns if message is not a reply (no overhead for normal messages)
2. Early-returns if no task ID found in replied message
3. Early-returns if task doesn't have clarification_pending flag
4. Only processes if all conditions match

This design ensures no performance impact on normal message flow.
