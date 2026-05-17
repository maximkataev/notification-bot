# Testing Guide: GPT-Based Task Sorting

## Quick Start

### Test 1: Basic Functionality (5 minutes)

Create these tasks in Telegram:

```
/plan СРОЧНО позвонить боссу
/plan сходить в спортзал в 10:00
/plan ответить на письма
/plan купить продукты
/plan встреча с клиентом в 14:00
```

Then trigger the digest:

```
/digest
```

### Expected Output Structure

```
СРОЧНЫЕ (1 задача):
• СРОЧНО позвонить боссу (30 мин)
  └ [AI explanation about why now]

НЕСРОЧНЫЕ (4 задачи):
• [Task 1] (time мин)
  └ [Explanation]
• [Task 2] (time мин)
  └ [Explanation]
• [Task 3] (time мин)
  └ [Explanation]
• [Task 4] (time мин)
  └ [Explanation]
```

### What to Verify

✅ **All 5 tasks appear** (not cut off)  
✅ **СРОЧНЫЕ section** has 1 task (the "СРОЧНО" one)  
✅ **НЕСРОЧНЫЕ section** has 4 tasks  
✅ **Each task has explanation** (from GPT)  
✅ **Time estimate present** e.g., "(30 мин)"  
✅ **Order is sensible** — tasks with specific times likely appear first  

---

## Test 2: Order Verification (10 minutes)

### Scenario 1: Time-Constrained Tasks

Create:
```
/plan встреча в 10:00
/plan СРОЧНО позвонить
/plan купить продукты
/plan ответить письма в 14:00
```

Check digest output:
- Tasks with specific times (10:00, 14:00) should rank high in НЕСРОЧНЫЕ
- "СРОЧНО позвонить" in СРОЧНЫЕ section
- "купить продукты" and "ответить письма" probably lower in НЕСРОЧНЫЕ

**Why?** GPT should recognize that time-specific tasks constrain your day.

### Scenario 2: Mixed Urgency

Create:
```
/plan важно! отправить отчёт
/plan позвонить другу
/plan выучить новый навык
/plan срочно купить продукты
```

Check digest:
- Both important tasks in СРОЧНЫЕ (contain keywords: важно, срочно)
- Other two in НЕСРОЧНЫЕ
- СРОЧНЫЕ ordered by GPT's judgment of consequences

**Why?** "Отправить отчёт" might be more time-critical than "купить продукты"

### Scenario 3: Outdoor/Weather Tasks

Create:
```
/plan сходить в парк (outdoor)
/plan сходить в спортзал в 10:00 (outdoor + timed)
/plan ответить на письма
/plan купить кофе (outdoor)
```

Check digest:
- Timed outdoor task (спортзал в 10:00) should rank high
- Non-timed outdoor tasks lower (depends on weather context)
- Indoor task (письма) varies

**Why?** GPT has access to weather data; it might rank outdoor tasks based on weather forecast and time of day

---

## Test 3: Edge Cases (5 minutes)

### Empty Tasks

Create no tasks, just `/digest`:
- Should show: "Дел на сегодня нет."
- No errors

### Only Urgent Tasks

Create:
```
/plan СРОЧНО задача 1
/plan СРОЧНО задача 2
/plan СРОЧНО задача 3
```

Check digest:
- Only СРОЧНЫЕ section
- No НЕСРОЧНЫЕ section
- All 3 tasks shown

### Only Non-Urgent Tasks

Create:
```
/plan задача 1
/plan задача 2
/plan задача 3
```

Check digest:
- Only НЕСРОЧНЫЕ section
- No СРОЧНЫЕ section
- All 3 tasks shown

### Many Tasks (10+)

Create 15 varied tasks, run `/digest`:
- All 15 appear (not truncated)
- Message may split if >4000 chars (normal)
- Order is logical

---

## Test 4: Consistency Check (5 minutes)

Run `/digest` twice with same tasks.

Expected: **Same order both times** (unless minutes changed, e.g., 10:15 vs 10:00)

This verifies GPT is deterministic (same input → same rank).

---

## Test 5: Regression — Check Nothing Broke

### Weather Section
- [ ] Weather still shows morning/day/evening/night
- [ ] Outfit advice still present
- [ ] Air quality still shown

### News Section
- [ ] News still appears
- [ ] Links still work

### Exchange Rates
- [ ] Rates still show
- [ ] Percent changes visible

### Logging
Run in terminal where bot is running:

```bash
tail -f bot.log | grep -E "(Sorted|priority_rank|explanation|Analyzing)"
```

Expected log lines:
```
🔄 Analyzing 5 tasks with time, difficulty, and priority
✓ Got task analysis from AI
✓ Analyzed 5 tasks
Sorted 5 tasks by GPT priority rank
```

---

## Debugging Checklist

### If tasks are in wrong order:

1. Check logs for errors in GPT response
2. Check if `priority_rank` is being parsed correctly
   - Add debug log in scheduler.py: `logger.info(f"Task {task.id}: rank = {_get_gpt_rank(task)}")`
3. Check if GPT is understanding the prompt
   - Run a manual test with small task list and inspect response

### If no explanation shown:

1. Check logs for `Failed to generate task explanations`
2. Verify OPENAI_API_KEY is set
3. Check if JSON parse is failing
   - Look for: `Failed to parse JSON response`

### If performance degrades:

1. Monitor token usage (should be same as before)
2. Check timeout settings (120 seconds default)
3. Verify all external APIs responding

---

## Expected Improvements

✨ **Tasks appear in smarter order** — not mechanical scoring  
✨ **Context-aware** — GPT sees whole day, not individual task metrics  
✨ **Explainable** — GPT can explain why task X comes before Y  
✨ **No performance impact** — same GPT call, just one extra field  

## Performance Baseline

**Before**: ~2-3 seconds for 5 tasks (GPT call + sort)  
**After**: ~2-3 seconds for 5 tasks (same, GPT just returns one more field)

Token usage should be virtually identical (few extra tokens for `priority_rank` field).

---

## Report Issues

If you find:
- Tasks ordering seems random → check logs for JSON errors
- Missing explanations → verify GPT response format
- Performance degradation → check timeout and API latency

Check logs first, they contain all GPT errors and parsing failures.
