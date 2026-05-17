# Task Parsing Improvements - Summary

## Problem Solved
User feedback indicated that tasks with flexible deadlines were triggering unnecessary clarification questions when all information was already in the text.

**Example:** "после качалки в пн вечером забрать посылки, можно в среду"
- Had: when_date (Monday evening)
- Had: flexible_option (can do Wednesday)
- **Problem:** AI asked "когда это сделать?" despite clear information
- **Why:** System prompt didn't explicitly handle "можно X" patterns

## Solutions Implemented

### 1. Enhanced System Prompt (src/ai/planner_agent.py)
Added explicit rule for parsing flexible deadlines:

```
- PARSE FLEXIBLE DEADLINES: if user says "можно X" / "или X" / "если нет X" / "в крайнем случае X":
  a) Use the FIRST mentioned date/time as when_date/when_time
  b) Put the flexible option ("можно в среду") in constraints field
  c) Do NOT ask clarification — all info is already in the text
```

**Impact:** Tasks like "в пн вечером, можно в среду" are now fully parsed without clarification questions.

### 2. Reply-to Clarification Handler (src/bot/handlers/plan_handler.py)
Added `clarification_reply()` handler that:
- Detects replies to bot messages with task info
- Extracts task ID from original message
- Re-parses task with user's clarification appended
- Updates all task fields (what, when_date, proposed_time, is_urgent, is_outdoor)
- Shows updated task info

**Flow:**
```
User: /plan задача без четкой даты
Bot: ✓ Задача #5 разобрана...
     ❓ Уточнение: Когда это выполнить?
     
User: replies "в пятницу в 14:00"
Bot: ✓ Задача #5 обновлена... ⏰ 14:00
```

### 3. Database Updates (src/db/database.py)
- Added `is_urgent` and `is_outdoor` to allowed fields in `update_task_fields()`
- These fields are now properly saved when tasks are updated

### 4. Handler Updates (src/bot/handlers/plan_handler.py)
Both `plan_command()` and `clarification_reply()` now pass:
- `is_urgent` - extracted from task text
- `is_outdoor` - extracted from task text (for weather consideration)

## Test Scenarios

### ✅ Scenario 1: Flexible Deadline (No Clarification)
```
User: /plan в пн вечером забрать посылки, можно в среду

Result:
- what: "забрать посылки"
- when_date: "2026-05-12" (Monday)
- when_time: "19:00" (evening)
- constraints: "можно в среду"
- needs_clarification: false ← NO QUESTION ASKED
```

### ✅ Scenario 2: Missing Info (Clarification Needed)
```
User: /plan купить что-то важное

Bot shows:
❓ Уточнение: Когда нужно купить? Сегодня, завтра, или на какую дату?

User replies: завтра в 15:00
Bot re-parses and updates task ✓
```

### ✅ Scenario 3: Urgent Task
```
User: /plan СРОЧНО звонок боссу

Result:
- is_urgent: true
- proposed_time: immediately (within working hours or sooner)
- Shown with "(срочно)" marker
```

### ✅ Scenario 4: Weather-Dependent Task
```
User: /plan прогулка в парке

Result:
- is_outdoor: true
- Weather context considered (rainy → suggest cover, hot → suggest cool hours)
- 🌦️ "Учтена текущая погода" shown in response
```

## Database Schema Impact
All changes are backward compatible. Task table already has:
- `is_urgent` (INTEGER)
- `is_outdoor` (INTEGER)
- `clarification_pending` (INTEGER)
- `clarification_question` (TEXT)

## Router Order & Performance
The `clarification_reply()` handler:
- Uses early returns: no overhead for normal messages
- Only processes if: reply exists → task ID found → clarification_pending = 1
- Safe to place at end of message handlers

## Benefits
✅ Fewer unnecessary clarification questions  
✅ Better parsing of flexible deadlines from user text  
✅ Users can reply to clarifications instead of typing new commands  
✅ All task attributes properly saved (is_urgent, is_outdoor)  
✅ Morning/evening digests get complete task context  

## Next Steps
- Test with actual Telegram bot
- Verify morning digest uses is_urgent/is_outdoor for better prioritization
- Monitor for edge cases in flexible deadline parsing
