# Task Sorting & Display Logic

Comprehensive guide to how tasks are selected, sorted, and displayed in the morning digest.

## Task Selection (Database Level)

**File**: `src/workers/todoist_client.py`

Tasks are fetched from Todoist with this filter:
```python
async def get_todoist_tasks(user_id: int) -> List[Task]:
    """Get all tasks with due date today or no due date"""
    # Pseudo-code:
    # SELECT tasks WHERE:
    #   - due_date IS NULL (no deadline)
    #   - OR due_date == TODAY
    #   - AND status != 'completed'
```

**Result**: Only tasks relevant to today are retrieved. Future tasks are excluded.

## Task Classification

**File**: `src/bot/scheduler.py` (lines 56-78)

### Urgency Detection Function: `_is_task_urgent_by_keywords(task) → bool`

Tasks are checked against urgency keywords:

```python
urgency_keywords = [
    "срочно",           # urgent
    "важно",            # important
    "asap",
    "асап",
    "быстро",           # quickly
    "немедленно",       # immediately
    "срочная",
    "срочной",
    "неотложн",         # not deferrable
    "критичн",          # critical
    "экстренно",        # emergency
    "urgent",
    "emergency",
    "immediately",
    "right now",
    "now",
]
```

**Logic**:
```python
text = f"{task.what or ''} {task.raw_text or ''}".lower()
is_urgent = any(keyword in text for keyword in urgency_keywords)
```

**Examples**:
- ✅ "СРОЧНО позвонить боссу" → urgent
- ✅ "Важно! Оплатить счёт" → urgent
- ✅ "Срочная встреча" → urgent
- ✅ "Asap отправить письмо" → urgent
- ❌ "Позвонить другу" → not urgent

## Task Separation

**File**: `src/bot/scheduler.py` (lines 505-515)

Tasks are separated into two groups:

```python
urgent_tasks = [
    t for t in today_tasks_sorted
    if t.is_urgent or _is_task_urgent_by_keywords(t)
]

non_urgent_tasks = [
    t for t in today_tasks_sorted
    if not t.is_urgent and not _is_task_urgent_by_keywords(t)
]
```

**Note**: Both lists are already sorted by importance score (from line 476).

## Importance Scoring

**File**: `src/ai/task_explainer.py`

Function: `score_task_importance(task) → int`

Scoring system:
```python
def score_task_importance(task) -> int:
    score = 0
    
    # Urgent flag: +100
    if task.is_urgent:
        score += 100
    
    # Outdoor task: +30
    if task.is_outdoor:
        score += 30
    
    # Has specific time: +20
    if task.when_time:
        score += 20
    
    # Has specific date: +10
    if task.when_date:
        score += 10
    
    return score
```

**Examples**:
- "СРОЧНО купить билеты" → 100 (urgent)
- "Пойти в спортзал в 10:00" → 20 (timed)
- "Сходить в парк" → 30 (outdoor)
- "Сходить в парк в 15:00" → 50 (outdoor + timed)
- "СРОЧНО сходить в магазин" → 130 (urgent + outdoor)
- "Ответить на письмо" → 0 (no markers)

**Sorting**: Highest score first (descending order)

## Display Format

**File**: `src/bot/scheduler.py` (lines 517-557)

### Urgent Tasks Section

```python
if urgent_tasks:
    message_lines.append(f"СРОЧНЫЕ ({len(urgent_tasks)} задач):")
    for task in urgent_tasks:
        name = task.what or task.raw_text[:50]
        task_data = task_explanations.get(task.id, {})
        explanation = task_data.get("explanation", "")
        time_minutes = task_data.get("time_minutes", 30)
        
        message_lines.append(f"• {name} ({time_minutes} мин)")
        if explanation:
            message_lines.append(f"  └ {explanation}")
```

**Output Format**:
```
СРОЧНЫЕ (N задач):
• Task name (30 мин)
  └ Brief explanation from AI
• Another task (45 мин)
  └ Another explanation
```

### Non-Urgent Tasks Section

```python
if non_urgent_tasks:
    message_lines.append(f"НЕСРОЧНЫЕ ({len(non_urgent_tasks)} задач):")
    
    for task in non_urgent_tasks:  # ALL tasks shown (no limit)
        name = task.what or task.raw_text[:50]
        task_data = task_explanations.get(task.id, {})
        explanation = task_data.get("explanation", "")
        time_minutes = task_data.get("time_minutes", 30)
        
        message_lines.append(f"• {name} ({time_minutes} мин)")
        if explanation:
            message_lines.append(f"  └ {explanation}")
```

**Output Format**:
```
НЕСРОЧНЫЕ (M задач):
• Task name (20 мин)
  └ Brief explanation
• Another task (60 мин)
  └ Another explanation
... (все задачи показаны)
```

**Change Log**: Previously only top 3 non-urgent tasks were shown. Now **all** non-urgent tasks are displayed.

## AI Explanations

**File**: `src/ai/task_explainer.py`

For each task, AI generates a brief explanation (10-15 words):

```python
async def get_task_explanations(
    tasks: List[Task],
    weather: Optional[Dict] = None,
    profile: Optional[Dict] = None
) -> Dict[int, Dict]:
    """Generate explanations for all tasks"""
    
    # Context injected into prompt:
    # - Current weather conditions
    # - User's wake/sleep times
    # - User's preferences
    
    # Output: {task_id: {"explanation": "...", "time_minutes": 30}}
```

**Example Explanations**:
- "Нужно перед вылетом завтра" → for urgent flight booking
- "Утром до 11:00 по плану" → for timed outdoor task
- "Холодно, не забыть куртку" → contextual weather advice
- "Лучше в спокойное время" → for complex tasks

## Complete Flow Example

### User Inputs These Tasks

```
/plan СРОЧНО купить билеты
/plan сходить в спортзал (утром в 10:00)
/plan ответить на письма
/plan погулять в парке
/plan встреча с клиентом (14:00)
```

### Database Stores

| ID | Task | is_urgent | is_outdoor | when_date | when_time |
|----|------|-----------|-----------|-----------|-----------|
| 1 | купить билеты | true | false | 2026-05-17 | null |
| 2 | спортзал | false | true | 2026-05-17 | 10:00 |
| 3 | письма | false | false | 2026-05-17 | null |
| 4 | парк | false | true | 2026-05-17 | null |
| 5 | встреча | false | false | 2026-05-17 | 14:00 |

### Importance Scores

| ID | Task | Keywords | Score | Reason |
|----|------|----------|-------|--------|
| 1 | купить билеты | СРОЧНО | 100 | urgent (+100) |
| 2 | спортзал | no | 50 | outdoor (+30) + timed (+20) |
| 5 | встреча | no | 20 | timed (+20) |
| 4 | парк | no | 30 | outdoor (+30) |
| 3 | письма | no | 0 | no markers |

### Sorted (Descending)

1. **купить билеты** (100)
2. **спортзал** (50)
3. **встреча с клиентом** (20)
4. **погулять в парке** (30)
5. **ответить на письма** (0)

Wait, scores should be:
1. купить билеты (100)
2. спортзал (50)
3. парк (30)
4. встреча (20)
5. письма (0)

### Classified

**СРОЧНЫЕ**:
- купить билеты (100)

**НЕСРОЧНЫЕ** (sorted by score):
- спортзал (50)
- парк (30)
- встреча (20)
- письма (0)

### Final Display

```
СРОЧНЫЕ (1 задача):
• Купить билеты (30 мин)
  └ Критично перед вылетом завтра

НЕСРОЧНЫЕ (4 задачи):
• Сходить в спортзал (45 мин)
  └ Лучше утром (планируешь 10:00)
• Погулять в парке (60 мин)
  └ Хорошая погода сегодня
• Встреча с клиентом (60 мин)
  └ В 14:00, подготовь материалы
• Ответить на письма (30 мин)
  └ Когда освободишься в течение дня
```

## Edge Cases

### Empty Urgent / Non-Urgent

- If no urgent tasks: section skipped
- If no non-urgent tasks: section skipped
- Both could be empty if no tasks for today

### Very Long Task Names

Task names truncated to 50 chars (from raw_text if `what` is empty):
```python
name = task.what or task.raw_text[:50]
```

### Missing AI Explanation

If AI fails to generate explanation, field is empty:
```python
if explanation:
    message_lines.append(f"  └ {explanation}")
# else: task shown without explanation
```

### Very Many Tasks

No limit on non-urgent tasks. If 20+ tasks:
```
НЕСРОЧНЫЕ (23 задачи):
• Task 1
• Task 2
...
• Task 23
```

Message splitting occurs if total digest exceeds 4000 chars.

## Updated: 2026-05-17

Changed: Show all non-urgent tasks instead of limiting to top 3.
