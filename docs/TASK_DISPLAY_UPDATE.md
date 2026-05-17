# Task Display Update — Show All Tasks in Morning Digest

## Summary

Updated morning digest to show **all** tasks instead of limiting non-urgent tasks to 3.

## Changes

### Before
- **Срочные** (urgent tasks) — all shown
- **Несрочные** (non-urgent tasks) — only top 3 shown with note "(показаны 3 из N несрочных)"

### After
- **Срочные** (urgent tasks) — all shown
- **Несрочные** (non-urgent tasks) — **all** shown, sorted by importance

## Implementation

**File**: `src/bot/scheduler.py` (lines 534–557)

**Change**:
```python
# OLD: Show only top 3 non-urgent tasks
display_non_urgent = non_urgent_tasks[:3]
if len(non_urgent_tasks) > 3:
    message_lines.append(f"(показаны 3 из {len(non_urgent_tasks)} несрочных)\n")

# NEW: Show all non-urgent tasks
for task in non_urgent_tasks:  # <-- removed [:3] slice
    # ... format and display task ...
```

## Task Filtering Logic

Tasks shown in digest are filtered by:
1. **Urgency classification** (via `is_urgent` flag or keyword matching)
   - Keywords checked: "срочно", "важно", "asap", "быстро", "неотложн", "критичн", etc.
2. **Date filtering** (from database query)
   - Only tasks with `when_date == today` or `when_date IS NULL`
3. **Sorting** (by importance score)
   - Urgent tasks: +100 points
   - Outdoor tasks: +30 points
   - Timed tasks: +20 points
   - Dated tasks: +10 points

## Display Format

```
СРОЧНЫЕ (N задач):
• Задача 1 (30 мин)
  └ Объяснение от AI
• Задача 2 (45 мин)
  └ Объяснение от AI

НЕСРОЧНЫЕ (M задач):
• Задача 3 (20 мин)
  └ Объяснение от AI
• Задача 4 (60 мин)
  └ Объяснение от AI
...
```

## Benefits

1. **Complete visibility** — see all your tasks for the day, not just top 3
2. **Better planning** — understand full workload at a glance
3. **Sorted by importance** — most important non-urgent tasks appear first
4. **AI explanations** — each task has brief context from AI

## Date

Updated: 2026-05-17
