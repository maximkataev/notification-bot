#!/usr/bin/env python3
"""Regression test for _parse_selection — the news selector reply normalizer.

ChatGPT is asked for a bare JSON array but returns a different container almost
every call: `{"news": [...]}` one time, `{"1": {...}, "2": {...}}` the next. Those
parse as valid JSON, so before the normalizer existed the validation loop iterated
a dict's KEYS, saw strings, rejected everything ("Invalid index unknown") and the
whole main news block silently vanished from the digest while the small pools —
which happened to still get arrays — kept working.

Run: python3 tests/test_news_selection_parsing.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai.news_processor import _parse_selection

# (name, raw ChatGPT reply, expected list of index values or None)
CASES = [
    (
        "bare array (the documented shape)",
        '[{"index": 1, "category": "politics", "description_ru": "a"}]',
        [1],
    ),
    (
        "array wrapped in an object",
        '{"news": [{"index": 1, "description_ru": "a"}, {"index": 2, "description_ru": "b"}]}',
        [1, 2],
    ),
    (
        "object keyed by position, values are the items",
        '{"1": {"index": 5, "description_ru": "a"}, "2": {"index": 6, "description_ru": "b"}}',
        [5, 6],
    ),
    (
        "single item returned unwrapped",
        '{"index": 3, "description_ru": "a"}',
        [3],
    ),
    (
        "markdown-fenced array",
        '```json\n[{"index": 4, "description_ru": "a"}]\n```',
        [4],
    ),
    (
        "index as a numeric string (must become int)",
        '[{"index": "7", "description_ru": "a"}]',
        [7],
    ),
    (
        "array nested two levels deep",
        '{"result": {"items": [{"index": 8, "description_ru": "a"}]}}',
        [8],
    ),
    (
        "prose around the array",
        'Вот выбранные новости:\n[{"index": 9, "description_ru": "a"}]',
        [9],
    ),
    ("refusal text, no JSON at all", "I cannot complete this request", None),
    ("empty array", "[]", None),
    ("object with no items anywhere", '{"error": "no suitable news"}', None),
]


def test_parse_selection():
    failures = []

    for name, raw, expected in CASES:
        result = _parse_selection(raw, "test")

        if expected is None:
            ok = result is None
            got = "None" if result is None else result
        else:
            ok = result is not None and [i.get("index") for i in result] == expected
            got = [i.get("index") for i in result] if result else result
            # Indices must be ints — every caller compares them against int ranges.
            if ok and not all(isinstance(i.get("index"), int) for i in result):
                ok = False
                got = f"{got} (index not int)"

        print(f"{'✓' if ok else '✗'} {name}\n    expected={expected} got={got}")
        if not ok:
            failures.append(name)

    print()
    if failures:
        print(f"✗ {len(failures)}/{len(CASES)} FAILED: {', '.join(failures)}")
        return False

    print(f"✓ All {len(CASES)} selector-reply shapes handled")
    return True


if __name__ == "__main__":
    sys.exit(0 if test_parse_selection() else 1)
