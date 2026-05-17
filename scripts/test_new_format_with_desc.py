#!/usr/bin/env python3
"""Test new event format with descriptions."""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import format_events_for_telegram


def main():
    print("\n" + "="*100)
    print("🎭 TESTING NEW EVENT FORMAT (WITH DESCRIPTIONS)")
    print("="*100 + "\n")

    # Mock events with all fields
    mock_events = [
        {
            "title": "Концерт Guri and Giga Jalagonia",
            "date": "2026-05-23",
            "time": "20:00",
            "location": "Gardenia Hall",
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
            "location": "Expo Georgia Exhibition Center",
            "description": "Ежегодная выставка современного искусства с участием художников со всего мира. На ярмарке представлены работы в различных стилях: живопись, скульптура, инсталляции и видео-арт. Посетители смогут познакомиться с творчеством как известных, так и молодых талантливых художников.",
            "category": "exhibition",
            "source": "georgia.travel",
            "url": "https://georgia.travel/events",
            "price": "15 GEL",
        },
        {
            "title": "Partnership & Networking Party",
            "date": "2026-05-23",
            "time": "18:00",
            "location": "Unicorn Embassy",
            "description": "Встреча предпринимателей, инвесторов и технологических специалистов. На мероприятии будут представлены стартапы, проводиться питчинги и сетевые мероприятия. Отличная возможность найти партнеров, инвесторов или клиентов для вашего проекта.",
            "category": "conference",
            "source": "eventbrite.com",
            "url": "https://www.eventbrite.com/e/partnership-networking-party",
            "price": "20 USD",
        },
    ]

    print(f"📊 Testing with {len(mock_events)} events\n")

    # Format and display
    formatted = format_events_for_telegram(mock_events)

    print("="*100)
    print("📱 NEW FORMAT OUTPUT WITH DESCRIPTIONS")
    print("="*100 + "\n")
    print(formatted)
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
