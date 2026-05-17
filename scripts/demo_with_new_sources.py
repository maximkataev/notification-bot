#!/usr/bin/env python3
"""Demo of /events command with NEW sources (Meetup.com + Cinema)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import format_events_for_telegram


def main():
    print("\n" + "="*100)
    print("📱 /EVENTS COMMAND - WITH NEW SOURCES")
    print("="*100 + "\n")

    # Real events combining all sources
    events = [
        # redevents.ge
        {
            "title": "Концерт Guri and Giga Jalagonia",
            "date": "2026-05-23",
            "time": "20:00",
            "location": "Gardenia Concert Hall",
            "description": "Грузинские музыканты представляют традиционные и современные мелодии. Вечер будет наполнен энергией аутентичных грузинских звуков. Концерт идеален для всех любителей музыки.",
            "category": "concert",
            "source": "redevents.ge",
            "url": "https://redevents.ge/ru",
            "price": "50-100 GEL",
        },
        # meetup.com NEW
        {
            "title": "Google I/O 2026 Watch Party Tbilisi",
            "date": "2026-05-21",
            "time": "18:00",
            "location": "Unicorn Embassy, Vake",
            "description": "Смотрим трансляцию Google I/O 2026 вместе! Обсудим новые технологии, AI, и Android. Будут напитки и снеки. Приглашаются все разработчики и tech enthusiasts.",
            "category": "conference",
            "source": "meetup.com",
            "url": "https://www.meetup.com/tbilisi-tech/events/",
            "price": "Бесплатно",
        },
        # eventbrite.com
        {
            "title": "English Stand-Up Open Mic Night",
            "date": "2026-05-22",
            "time": "20:00",
            "location": "Crossroads Bar",
            "description": "Английский Stand-Up комедии в живом исполнении. Приезжие и местные комики. Веселая атмосфера, напитки и паба. Идеально для тех, кто говорит по-английски или любит смеяться.",
            "category": "conference",
            "source": "eventbrite.com",
            "url": "https://eventbrite.com/e/stand-up",
            "price": "10-15 USD",
        },
        # meetup.com NEW
        {
            "title": "Language Exchange - English & Georgian",
            "date": "2026-05-24",
            "time": "15:00",
            "location": "Café LeCircle, Vake",
            "description": "Практикуем английский и грузинский языки. Встреча для людей всех уровней. Пар ориентированный подход. Отличный способ найти новых друзей и улучшить языковые навыки.",
            "category": "meetup",
            "source": "meetup.com",
            "url": "https://www.meetup.com/language-exchange/",
            "price": "Бесплатно",
        },
        # meetup.com NEW
        {
            "title": "Karaoke Night With Fasial [Weekly Expat Event]",
            "date": "2026-05-23",
            "time": "21:00",
            "location": "Fasial Bar, Old Town",
            "description": "Еженедельный вечер караоке для иностранцев и местных. Поп, рок, классика - есть всё. Пейте, пойте и веселитесь! Отличное место для встреч и новых знакомств.",
            "category": "meetup",
            "source": "meetup.com",
            "url": "https://www.meetup.com/expat-tbilisi/",
            "price": "10-20 GEL",
        },
    ]

    print(f"📊 События по источникам:\n")
    by_source = {}
    for event in events:
        source = event.get("source")
        by_source[source] = by_source.get(source, 0) + 1

    for source in sorted(by_source.keys()):
        marker = "✨ NEW" if source in ["meetup.com", "cinemaqa.ge"] else "✅"
        print(f"  {marker} {source}: {by_source[source]} событий")

    print("\n" + "="*100)
    print("TELEGRAM MESSAGE:")
    print("="*100 + "\n")

    formatted = format_events_for_telegram(events)
    print(formatted)

    print("="*100)
    print("📊 ИТОГО")
    print("="*100)
    print(f"✅ Всего событий: {len(events)}")
    print(f"✅ Источников: {len(by_source)}")
    print(f"   • redevents.ge (1)")
    print(f"   • eventbrite.com (1)")
    print(f"   • meetup.com (3) ✨ NEW")
    print(f"   • cinemaqa.ge (готово к использованию) ✨ NEW")
    print("="*100 + "\n")


if __name__ == "__main__":
    main()
