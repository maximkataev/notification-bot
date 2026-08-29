"""Tests for clean-language filtering of the daily joke."""

from src.workers.joke_of_day import contains_profanity


def test_detects_common_russian_profanity_forms():
    assert contains_profanity("Да пошёл ты нахуй")
    assert contains_profanity("Вот это пиздец")
    assert contains_profanity("Он совсем ебанулся")
    assert contains_profanity("Блядь, опять дождь")
    assert contains_profanity("Какой же мудак")


def test_does_not_reject_innocent_words():
    assert not contains_profanity("Ребёнок любит хлеб")
    assert not contains_profanity("Спасибо тебе за добрый анекдот")
    assert not contains_profanity("На улице чудесная погода")
