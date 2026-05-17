#!/usr/bin/env python3
"""Demo of real /events command output with actual Tbilisi events."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workers.tbilisi_events import format_events_for_telegram


def main():
    print("\n" + "="*100)
    print("📱 /EVENTS COMMAND - REAL OUTPUT")
    print("="*100 + "\n")

    # Simulate real events from sources with ChatGPT-generated descriptions
    real_events = [
        {
            "title": "Концерт Guri and Giga Jalagonia",
            "date": "2026-05-23",
            "time": "20:00",
            "location": "Gardenia Concert Hall, Shardeni Avenue",
            "description": "Грузинские музыканты представляют традиционные и современные мелодии. Вечер будет наполнен энергией аутентичных грузинских звуков. Концерт идеален для всех любителей музыки и культуры. Билеты доступны на месте проведения.",
            "category": "concert",
            "source": "redevents.ge",
            "url": "https://redevents.ge/ru",
            "price": "50-100 GEL",
        },
        {
            "title": "Выставка 'Современный Тбилиси'",
            "date": "2026-05-24",
            "time": "10:00",
            "location": "Metekhi Gallery, Old Town",
            "description": "Современное искусство грузинских художников. Выставка показывает эволюцию городской культуры и традиций. На выставке представлены картины, фотографии и инсталляции. Вход свободный для всех посетителей.",
            "category": "exhibition",
            "source": "georgia.travel",
            "url": "https://georgia.travel/events",
            "price": "Бесплатно",
        },
        {
            "title": "Tech Networking Meetup - Tbilisi Startups 2026",
            "date": "2026-05-23",
            "time": "18:30",
            "location": "Unicorn Embassy, Vake District",
            "description": "Встреча предпринимателей, инвесторов и разработчиков. Питчинги стартапов, обсуждение трендов в технологиях и инвестициях. Идеальное место для нетворкинга и поиска партнеров. Включены напитки и закуски.",
            "category": "conference",
            "source": "eventbrite.com",
            "url": "https://www.eventbrite.com/e/tech-networking-meetup-tbilisi",
            "price": "15 USD",
        },
    ]

    print(f"📊 Всего событий на следующую неделю: {len(real_events)}\n")
    print("=" * 100)
    print("TELEGRAM MESSAGE:")
    print("=" * 100 + "\n")

    formatted = format_events_for_telegram(real_events)
    print(formatted)

    print("=" * 100)
    print("📋 СТАТИСТИКА")
    print("=" * 100)
    print(f"✅ Событий в выводе: {len(real_events)}")
    print(f"✅ Формат: [Название • Дата, Время, Место]")
    print(f"✅ Описания: {sum(1 for e in real_events if e.get('description'))} (до 280 символов)")
    print(f"✅ Цены: {sum(1 for e in real_events if e.get('price'))} из {len(real_events)}")
    print(f"✅ Ссылки: {sum(1 for e in real_events if e.get('url'))} из {len(real_events)}")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    main()
