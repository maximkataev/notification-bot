# Changelog: Show All Tasks in Morning Digest

**Date**: 2026-05-17  
**Type**: Feature Enhancement  
**Impact**: User-facing change in digest output

---

## Summary

The morning digest now displays **all** tasks for today instead of limiting non-urgent tasks to the top 3.

## What Changed

### Before
```
НЕСРОЧНЫЕ (если захочешь взяться):
(показаны 3 из 8 несрочных)
• Task 1
• Task 2
• Task 3
```

### After
```
НЕСРОЧНЫЕ (8 задач):
• Task 1
• Task 2
• Task 3
• Task 4
• Task 5
• Task 6
• Task 7
• Task 8
```

## Files Modified

### 1. `src/bot/scheduler.py` (lines 534-550)
**Change**: Removed the `[:3]` slice that limited non-urgent tasks

```diff
- display_non_urgent = non_urgent_tasks[:3]
- if len(non_urgent_tasks) > 3:
-     message_lines.append(f"(показаны 3 из {len(non_urgent_tasks)} несрочных)\n")
- for task in display_non_urgent:

+ for task in non_urgent_tasks:
```

Also updated the header to show the total count:
```diff
- message_lines.append(f"НЕСРОЧНЫЕ (если захочешь взяться):")
+ message_lines.append(f"НЕСРОЧНЫЕ ({len(non_urgent_tasks)} задач):")
```

### 2. `CLAUDE.md` (lines 109-119)
**Change**: Updated documentation of the morning digest execution flow

```diff
  14. **Score and sort tasks** by importance (urgent +100, outdoor +30, timed +20, dated +10)
- 15. **Generate AI explanations** for top 5 tasks
- 16. **Fetch exchange rates** (BTC, ETH, USD→EUR, USD→RUB) with 24h/30d changes
- 17. **Fetch top Product Hunt product** (today's top product with description)
- 18. **Get content recommendation** (random video, podcast, or music for analyst/tech specialist)
- 19. **Check OpenAI account balance** (shows balance, warns if <$0.50)
- 20. **Build final message** with all sections
- 21. **Send to Telegram** via `bot.send_message()` (split if >4000 chars)

+ 15. **Separate and display tasks**:
+     - **СРОЧНЫЕ** — all urgent tasks (marked as urgent or containing urgency keywords)
+     - **НЕСРОЧНЫЕ** — all non-urgent tasks (sorted by importance)
+ 16. **Generate AI explanations** for all tasks (what, when, why context)
+ 17. **Fetch exchange rates** (BTC, ETH, USD→EUR, USD→RUB) with 24h/30d changes
...
```

### 3. `TASK_LIFECYCLE.md` (added section)
**Change**: Added documentation about task display in morning digest

New section "## Отображение в Morning Digest" explaining:
- How tasks are separated into СРОЧНЫЕ and НЕСРОЧНЫЕ
- Display format with examples
- Note about the change from showing 3 to showing all

### 4. **New Files Created**

#### `TASK_DISPLAY_UPDATE.md`
High-level documentation of the change:
- Summary of before/after behavior
- Implementation details
- Benefits of the change

#### `TASK_SORTING_LOGIC.md`
Comprehensive technical documentation:
- Task selection from database
- Task classification (urgency detection)
- Importance scoring system with examples
- Display format details
- Complete flow example with all steps
- Edge cases and handling

#### `CHANGELOG_TASK_DISPLAY.md` (this file)
Detailed changelog with:
- What changed and why
- Files modified with diffs
- Testing recommendations
- Rollback instructions (if needed)

---

## Testing

### Manual Testing

1. **Create multiple tasks** in Telegram:
   ```
   /plan СРОЧНО позвонить боссу
   /plan сходить в спортзал
   /plan ответить на письма
   /plan купить продукты
   /plan встреча в 14:00
   /plan поговорить с другом
   ```

2. **Trigger digest**: `/digest`

3. **Verify output**:
   - [ ] All urgent tasks shown (should be 1)
   - [ ] All non-urgent tasks shown (should be 5)
   - [ ] Count is correct: "НЕСРОЧНЫЕ (5 задач)"
   - [ ] No truncation message: ~~"(показаны 3 из 5)"~~
   - [ ] Each task has explanation
   - [ ] Tasks sorted by importance

### Edge Cases

1. **No urgent tasks**:
   - Should show only НЕСРОЧНЫЕ section
   - СРОЧНЫЕ section skipped

2. **No non-urgent tasks**:
   - Should show only СРОЧНЫЕ section
   - НЕСРОЧНЫЕ section skipped

3. **No tasks at all**:
   - Should show: "Дел на сегодня нет."

4. **Very many tasks (20+)**:
   - All should display
   - Message may split if >4000 chars (normal behavior)

### Automated Testing

Run type checker:
```bash
mypy src/bot/scheduler.py --strict
```

---

## Benefits

1. **Complete visibility** — users see all their tasks for the day
2. **Better planning** — understand full workload without scrolling externally
3. **Consistent sorting** — all tasks sorted by importance, not arbitrary cutoff
4. **Removed confusion** — no more "showing 3 of 8" messages

## Potential Concerns

1. **Longer digest** — if user has 15+ tasks, digest will be longer
   - ✅ Mitigation: Message splitting handles >4000 chars automatically
   
2. **Information overload** — too many tasks visible at once
   - ✅ Mitigation: Tasks are sorted by importance, so critical ones appear first

## Rollback (if needed)

To revert this change:

```bash
# Revert the scheduler.py changes
git checkout HEAD~1 src/bot/scheduler.py

# Or manually revert:
# Line 536: Change f"НЕСРОЧНЫЕ ({len(non_urgent_tasks)} задач):" 
#          back to f"НЕСРОЧНЫЕ (если захочешь взяться):"
# Line 538: Change for task in non_urgent_tasks:
#          back to display_non_urgent = non_urgent_tasks[:3]
#          and for task in display_non_urgent:
# Lines 539-542: Add back the limit check
```

---

## Documentation Links

- **High-level overview**: [TASK_DISPLAY_UPDATE.md](TASK_DISPLAY_UPDATE.md)
- **Technical details**: [TASK_SORTING_LOGIC.md](TASK_SORTING_LOGIC.md)
- **Task lifecycle**: [TASK_LIFECYCLE.md](TASK_LIFECYCLE.md)
- **Main guide**: [CLAUDE.md](CLAUDE.md) (updated section 1.14-19)

---

## Related Issues/PRs

- Fixes requirement: "выводились бы все срочные задачи и все несрочные задачи"
- No breaking changes
- No database migration needed
- No API changes

---

## Notes

- This change increases message length slightly but automatically splits if needed
- No performance impact (same number of tasks processed, just displayed differently)
- Works seamlessly with Todoist API integration
- Compatible with existing AI explanation generation
