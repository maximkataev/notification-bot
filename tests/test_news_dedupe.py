#!/usr/bin/env python3
"""Regression test for news deduplication.

The digest used to show one story twice: the same BBC item reaches both the politics
and the culture pool, and separate outlets retell the same event under different
headlines. The pairs below are real headlines observed together in one morning's
pools; the NON-duplicate cases guard the opposite failure — silently merging two
genuinely distinct stories, which is worse, since the reader never learns it happened.

Run: python3 tests/test_news_dedupe.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workers.news_dedupe import StoryDeduper, story_tokens, is_same_story

# Real same-event pairs seen across sources in one digest run.
SAME_STORY = [
    (
        "Burnham exchanged messages with impersonator of top Trump aide",
        "Burnham exchanged messages with person posing as Trump's chief of staff",
    ),
    (
        "Trump directs Hegseth to scale back joint military exercises with South Korea",
        "Trump orders Pentagon to scale back joint exercises with South Korea",
    ),
    (
        "Post-mortems due on five boys killed in crash on wrong side of motorway",
        "Five teenagers killed after car driven on wrong side of Irish motorway",
    ),
]

# Distinct stories that share topic words and must NOT be merged.
DIFFERENT_STORIES = [
    (
        "Trump envoy Kushner arrives in Israel after rare Hamas talks on Gaza peace plan",
        "Trump directs Hegseth to scale back joint military exercises with South Korea",
    ),
    (
        "Ukrainian strikes kill six in Russia, acting governor says",
        "Ukraine war briefing: Kyiv could hit Russia with domestic ballistic missiles",
    ),
    (
        "How switching your bank account could earn you up to £220",
        "Asking prices for newly listed homes in UK's richest borough fall by £100k",
    ),
    (
        "Instagram and Facebook could change forever if Meta loses child privacy trial",
        "Elon Musk's Starbase wants to expand in south Texas",
    ),
    (
        "Курс доллара на рынке форекс превысил ₽86 впервые за пять месяцев",
        "Индекс Мосбиржи упал ниже 2100 пунктов на планах масштабных санкций ЕС",
    ),
]


def check(label, condition):
    print(f"{'✓' if condition else '✗'} {label}")
    return condition


def test_dedupe():
    ok = True

    print("-- same event, different outlets (must merge) --")
    for a, b in SAME_STORY:
        ok &= check(f"{a[:52]}... == {b[:40]}...",
                    is_same_story(story_tokens(a), story_tokens(b)))

    print("\n-- distinct stories (must NOT merge) --")
    for a, b in DIFFERENT_STORIES:
        ok &= check(f"{a[:52]}... != {b[:40]}...",
                    not is_same_story(story_tokens(a), story_tokens(b)))

    print("\n-- StoryDeduper over a mixed pool --")
    # Same url in two pools, a cross-source retelling, and two distinct stories.
    pool = [
        {"title": "Burnham exchanged messages with impersonator of top Trump aide",
         "url": "https://politico.eu/burnham"},
        {"title": "Ukrainian strikes kill six in Russia, acting governor says",
         "url": "https://bbc.co.uk/ukraine"},
        {"title": "Ukrainian strikes kill six in Russia, acting governor says",
         "url": "https://bbc.co.uk/ukraine?utm_source=rss"},   # same story, tracking param
        {"title": "Burnham exchanged messages with person posing as Trump's chief of staff",
         "url": "https://bbc.co.uk/burnham"},                  # same event, other outlet
        {"title": "Ebola outbreak in Democratic Republic of the Congo now deadliest",
         "url": "https://theguardian.com/ebola"},
    ]
    deduper = StoryDeduper()
    kept = [i for i in pool if deduper.accept(i)]
    ok &= check(f"5 items -> {len(kept)} unique (expected 3)", len(kept) == 3)

    print()
    print("✓ Deduplication behaves as expected" if ok else "✗ FAILURES above")
    return ok


if __name__ == "__main__":
    sys.exit(0 if test_dedupe() else 1)
