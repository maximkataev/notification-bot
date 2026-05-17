# Changelog: Switch to GPT-based Task Sorting

**Date**: 2026-05-17  
**Type**: Feature Enhancement / Architecture Change  
**Impact**: Smarter task ordering in digest, better AI understanding of priorities

---

## Summary

Replaced the static point system for task sorting with **GPT-based intelligent ordering**. GPT now decides which tasks should be done first by analyzing:
- Urgency markers
- Time constraints (specific time = timed tasks)
- Consequences of delay
- Energy requirements (easy vs hard tasks)
- Optimal day flow (what makes sense to do when)

No more hardcoded scores (+100 for urgent, +30 for outdoor, etc). GPT ranks all tasks intelligently.

---

## What Changed

### Before: Static Point System
```python
def score_task_importance(task) -> int:
    score = 0
    if task.is_urgent: score += 100
    if task.is_outdoor: score += 30
    if task.proposed_time: score += 20
    if task.when_date: score += 10
    return score

# Sorting:
tasks_sorted = sorted(tasks, key=score_task_importance, reverse=True)
```

**Problem**: Tasks ranked mechanically. No context about consequences, dependencies, or what actually matters today.

### After: GPT-based Ranking
```python
# GPT returns for each task:
{
    "priority_rank": 1,  # 1 = highest, N = lowest
    "explanation": "Срочно: нужно перед полётом завтра",
    "time_minutes": 30,
    "difficulty": 2,
    "is_urgent": true
}

# Sorting:
tasks_sorted = sorted(tasks, key=lambda t: task_explanations[t.id]["priority_rank"])
```

**Advantage**: GPT understands context holistically. A non-urgent task with tight deadline might rank higher than a marked-urgent task that can wait.

---

## Files Modified

### 1. `src/ai/task_explainer.py`

**Changed**: `get_task_explanations()` function

- **Added to prompt**: Request `priority_rank` (1 = highest priority to N = lowest)
- **New prompt instruction**: "Определи ранг от 1 (самая важная) до N (наименее важная), учитывая все факторы вместе"
- **JSON example updated**: Shows `priority_rank` field in response
- **Parsing updated**: Store `priority_rank` in returned dict alongside `explanation`, `time_minutes`, etc.
- **Deleted**: `score_task_importance()` function (no longer needed)

**Code change**:
```diff
  explanations[task.id] = {
      "explanation": item.get("explanation", ""),
      "time_minutes": item.get("time_minutes", 30),
      "difficulty": item.get("difficulty", 2),
      "is_urgent": item.get("is_urgent", False),
+     "priority_rank": item.get("priority_rank", 999),  # NEW
  }
```

### 2. `src/bot/scheduler.py`

**Changed**: Task sorting and display logic

- **Line 29**: Removed import of `score_task_importance`
- **Lines 475-476**: Deleted static sort that used point system
- **Lines 477-481**: Tasks now passed to `get_task_explanations()` in original order (no pre-sort)
- **Lines 483-486**: New sorting logic using GPT's `priority_rank`:
  ```python
  def _get_gpt_rank(task) -> int:
      return task_explanations.get(task.id, {}).get("priority_rank", 999)
  
  today_tasks_sorted = sorted(today_tasks, key=_get_gpt_rank)
  ```
- **Lines 489-507**: Urgent and non-urgent tasks also sorted by `_get_gpt_rank` after separation

**Effect**: 
- One less call to GPT (same call now returns both explanations AND ranking)
- Smarter ordering based on full context
- More flexible than point system

---

## How GPT Decides Priority

The prompt now includes:

```
Для каждой задачи определи priority_rank — порядковый номер от 1 (самая важная) до N (наименее важная).

При определении ранга задач:
- Ранг 1 = самая важная / критичная для дня
- Учитывай все факторы вместе (не только срочность, но и время дня, предпосылки)
- Предложи порядок, который максимально продуктивен для дня
```

**Factors GPT considers**:
- Urgency (срочно, важно, ASAP)
- Time constraints (specific time = must do then)
- Consequences (what breaks if not done today)
- Energy (easy tasks first to build momentum, or hard tasks when fresh?)
- Dependencies (do this before that)
- Optimal flow (breaks between intense tasks)

---

## No API Call Increase

**Key optimization**: The `priority_rank` field is returned in the same GPT call that generates explanations. No additional API calls. The response that previously contained:

```json
{
  "task_index": 0,
  "explanation": "...",
  "time_minutes": 30,
  "difficulty": 2,
  "is_urgent": true
}
```

Now contains:

```json
{
  "task_index": 0,
  "priority_rank": 1,        // NEW: just a few extra tokens
  "explanation": "...",
  "time_minutes": 30,
  "difficulty": 2,
  "is_urgent": true
}
```

**Cost**: ~10-20 extra tokens per task. Single GPT call for all tasks. No performance impact.

---

## Example: Old vs New Ordering

### Scenario
```
/plan СРОЧНО позвонить боссу
/plan сходить в спортзал в 10:00
/plan ответить на письма
/plan купить продукты
/plan встреча с клиентом в 14:00
```

### Old System (Point-Based)
```
Sort order:
1. СРОЧНО позвонить боссу (100 points: urgent)
2. встреча с клиентом в 14:00 (20 points: timed)
3. сходить в спортзал в 10:00 (50 points: outdoor + timed)
4. ответить на письма (0 points)
5. купить продукты (0 points)
```

### New System (GPT-Based)
```
GPT priority_rank:
1. сходить в спортзал в 10:00 (rank=1: specific time, sets energy for day)
2. встреча с клиентом в 14:00 (rank=2: depends on being fresh)
3. СРОЧНО позвонить боссу (rank=3: can do between tasks)
4. ответить на письма (rank=4: flexible, anytime)
5. купить продукты (rank=5: least urgent, after main tasks)
```

GPT reasoning: "Sport in morning sets energy and focus. Client meeting needs preparation. Boss call is urgent but can be squeezed in. Emails are flexible. Errands last."

---

## Testing

### Manual Testing

1. Create tasks with varied properties:
   ```
   /plan СРОЧНО позвонить боссу
   /plan сходить в спортзал в 10:00
   /plan ответить на письма
   /plan купить продукты
   /plan встреча в 14:00
   ```

2. Send `/digest`

3. Check order:
   - [ ] Tasks in СРОЧНЫЕ section appear in sensible order
   - [ ] Tasks in НЕСРОЧНЫЕ section appear in sensible order (not arbitrary)
   - [ ] Each task has explanation
   - [ ] Count shown: "СРОЧНЫЕ (N задач)" and "НЕСРОЧНЫЕ (M задач)"

### What to Look For

- **Better ordering**: Tasks with tight time constraints appear first
- **Smart grouping**: Related tasks might appear together if GPT sees dependency
- **Consistent logic**: Order should reflect practical productivity

---

## Rollback (if needed)

To revert to point-based sorting:

```bash
git checkout HEAD~1 src/ai/task_explainer.py src/bot/scheduler.py
```

Or manually restore:
1. Restore `score_task_importance()` function in `task_explainer.py`
2. Change import in `scheduler.py` line 29: add back `score_task_importance`
3. Restore lines 475-476 in `scheduler.py`: `today_tasks_sorted = sorted(today_tasks, key=score_task_importance, reverse=True)`
4. Remove the new `_get_gpt_rank()` function and sort logic

---

## Related Documentation

- **Updated**: [CLAUDE.md](CLAUDE.md) — section on Scheduler (lines 14-16)
- **Task Lifecycle**: [TASK_LIFECYCLE.md](TASK_LIFECYCLE.md)
- **Task Sorting Details**: [TASK_SORTING_LOGIC.md](TASK_SORTING_LOGIC.md)

---

## Benefits

1. **Intelligent ordering** — GPT understands context, not just metadata
2. **No extra cost** — same GPT call, just one extra field
3. **Flexible** — can adapt to different task types and user styles
4. **Better explanations** — GPT's reasoning about order is clearer
5. **Future-proof** — easy to add more reasoning to prompt if needed

## Trade-offs

- **Slightly less predictable** — GPT might order tasks unexpectedly (but usually for good reason)
- **Depends on GPT quality** — if GPT is confused, ordering might be odd (unlikely with gpt-5.4-mini)

---

## Notes

- No database schema changes
- No API contract changes
- Backward compatible (tasks still display the same way)
- `is_urgent` flag still respected for СРОЧНЫЕ/НЕСРОЧНЫЕ split
- Urgency keywords still trigger the СРОЧНЫЕ section
