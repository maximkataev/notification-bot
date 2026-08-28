#!/usr/bin/env python3
"""Test new morning digest sections: fact, art, movie, book."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workers.movie_recommender import is_movie_day, MOVIE_WEEKDAYS
from src.workers.book_recommender import is_book_day, BOOK_WEEKDAY


def test_schedule_days():
    # Movie days: Tue (1), Fri (4), Sat (5), Sun (6)
    assert is_movie_day(1) is True
    assert is_movie_day(4) is True
    assert is_movie_day(5) is True
    assert is_movie_day(6) is True
    assert is_movie_day(0) is False  # Mon
    assert is_movie_day(2) is False  # Wed
    assert is_movie_day(3) is False  # Thu

    # Book days: Wed (2)
    assert is_book_day(2) is True
    assert is_book_day(0) is False
    assert is_book_day(1) is False
    assert is_book_day(4) is False
    print("✓ Schedule day checks passed")


def main():
    test_schedule_days()
    print("✓ All new section logic tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
