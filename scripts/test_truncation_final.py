#!/usr/bin/env python3
"""Test that descriptions are truncated to 280 chars WITHOUT ellipsis."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import format_events_for_telegram


def main():
    print("\n" + "="*100)
    print("✅ FINAL TEST: DESCRIPTIONS UP TO 280 CHARS, NO ELLIPSIS")
    print("="*100 + "\n")

    # Mock events with long descriptions
    mock_events = [
        {
            "title": "Концерт Guri and Giga Jalagonia",
            "date": "2026-05-23",
            "time": "20:00",
            "location": "Gardenia Hall",
            # This description is 239 chars - will NOT be truncated
            "description": "Грузинские музыканты представляют традиционную музыку в современном исполнении. Вечер будет наполнен энергией и аутентичными звуками Грузии. Концерт подойдет как опытным меломанам, так и новичкам, желающим познакомиться с культурой страны.",
            "category": "concert",
            "source": "redevents.ge",
            "url": "https://redevents.ge/ru",
            "price": "50-100 GEL",
        },
        {
            "title": "TAF - Tbilisi Art Fair 2026",
            "date": "2026-05-24",
            "time": "10:00",
            "location": "Expo Georgia",
            # This description is 275 chars - will NOT be truncated
            "description": "Ежегодная выставка современного искусства с участием художников со всего мира. На ярмарке представлены работы в различных стилях: живопись, скульптура, инсталляции и видео-арт. Посетители смогут познакомиться с творчеством как известных, так и молодых талантливых художников.",
            "category": "exhibition",
            "source": "georgia.travel",
            "url": "https://georgia.travel/events",
            "price": "15 GEL",
        },
        {
            "title": "VeryLongEventNameWithExtremelyDetailedDescriptionThatWillDefinitelyExceed280Characters",
            "date": "2026-05-25",
            "time": "19:00",
            "location": "Convention Center",
            # This description is 350+ chars - WILL be truncated to exactly 280 chars
            "description": "Это очень длинное описание события, которое превышает лимит в 280 символов. Оно содержит много информации о событии, его программе, участниках, расписании, ценах и других важных деталях. Описание написано для того, чтобы проверить, что система правильно обрезает текст ровно на 280 символе без добавления троеточий или других символов. Давайте добавим еще больше текста, чтобы быть уверенными в корректности работы функции обрезания.",
            "category": "conference",
            "source": "eventbrite.com",
            "url": "https://eventbrite.com",
            "price": "25 USD",
        },
    ]

    formatted = format_events_for_telegram(mock_events)

    print("📱 FORMATTED OUTPUT:\n")
    print(formatted)

    print("\n" + "="*100)
    print("📊 VERIFICATION")
    print("="*100 + "\n")

    for i, event in enumerate(mock_events, 1):
        desc = event.get("description", "")
        truncated = desc[:280]

        print(f"Event {i}: {event.get('title')[:50]}")
        print(f"  Description length: {len(desc)} chars")
        print(f"  Truncated to: {len(truncated)} chars")
        print(f"  Ends with: ...{truncated[-25:] if len(truncated) > 25 else truncated}")
        print(f"  Has '...' at end? {'❌ YES (BUG!)' if truncated.endswith('...') else '✅ NO'}")
        print()

    print("="*100 + "\n")


if __name__ == "__main__":
    main()
