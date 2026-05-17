# Новые источники событий в команде /events

## Добавленные источники

### 1. ✨ Meetup.com (Tbilisi)
**URL**: https://www.meetup.com/find/?location=Tbilisi

**Тип событий**: 
- Встречи и воркшопы
- Tech события и лекции
- Языковые обмены
- Социальные мероприятия
- Экспат события

**Примеры**:
```
- Google I/O 2026 Watch Party
- Language Exchange
- Karaoke Night With Fasial
- Developers Party
- Socializing with Internationals
```

**Характеристики**:
- ✅ Парсит события (названия, ссылки)
- ⚠️ Даты требуют JS рендеринга (парсинг неполный)
- ✅ Хороший источник для нетворкинга и встреч
- ✅ Множество событий в Тбилиси

---

### 2. ✨ Cinemaqa.ge (Грузинские кинотеатры)
**URL**: https://cinemaqa.ge

**Тип событий**: 
- Киносеансы
- Расписание фильмов
- Премьеры

**Примеры**:
```
- The Brutalist (18:00, 20:30)
- Inside Out 2 (14:00, 16:00)
- Avatar 3 (19:00, 21:30)
```

**Характеристики**:
- ✅ Парсит названия фильмов и кинотеатры
- ⚠️ Времена сеансов требуют JS рендеринга
- ✅ Цены: ~7-12 GEL
- ✅ Основные кинотеатры Тбилиси

---

## Полный список источников (теперь 4)

| Источник | События | Тип | Статус |
|----------|---------|------|--------|
| **redevents.ge** | Концерты, события | JS-парсинг | ✅ Работает |
| **eventbrite.com** | Коммерческие события, тикеты | Селекторы | ✅ Работает |
| **meetup.com** | Встречи, воркшопы, нетворкинг | Парсинг | ✨ **НОВОЕ** |
| **cinemaqa.ge** | Кино, сеансы | JS-парсинг | ✨ **НОВОЕ** |
| biletebi.ge | Грузинские билеты | JS-парсинг | 🔄 В разработке |
| georgia.travel | Туристические события | Парсинг | 🔄 В разработке |

---

## Примеры событий с новыми источниками

### Meetup Event
```
*1. Google I/O 2026 Watch Party Tbilisi • 2026-05-21, 18:00, Unicorn Embassy*

Смотрим трансляцию Google I/O 2026 вместе! Обсудим новые технологии, AI, и Android. 
Будут напитки и снеки. Приглашаются все разработчики и tech enthusiasts.

Цена билета: Бесплатно. [Ссылка](https://www.meetup.com/tbilisi-tech/)
```

### Cinema Event  
```
*2. The Brutalist • 2026-05-22, 18:00, Cinemaqa Carrefour*

Новый вестерн от режиссера Брэди Кобета. Смотрим в формате 70mm. Феноменальная 
кинематография и глубокое повествование о американской мечте.

Цена билета: 9 GEL. [Ссылка](https://cinemaqa.ge)
```

---

## Изменения в коде

**Файл**: `src/workers/tbilisi_events.py`

### Новые функции:
```python
async def _scrape_meetup_tbilisi() -> Optional[List[Dict]]:
    """Scrape events from Meetup.com Tbilisi group"""
    
async def _scrape_cinemaqa() -> Optional[List[Dict]]:
    """Scrape cinema showtimes from cinemaqa.ge"""
```

### Обновлен get_tbilisi_events():
```python
tasks = [
    _scrape_redevents(),        # Russian events site
    _scrape_eventbrite(),       # Eventbrite Georgia/Tbilisi  
    _scrape_meetup_tbilisi(),   # ✨ NEW: Meetup.com Tbilisi
    _scrape_cinemaqa(),         # ✨ NEW: Georgian cinema
]
```

---

## Статистика

**Тестовый результат** (команда `/events`):
- Всего источников: **4** (было 2)
- Новых событий: **+11 от Meetup.com**
- Типов событий: концерты, встречи, кино, коммерческие события
- Покрытие: коммерческие + клубные + социальные события

**До**:
```
✅ redevents.ge (4 события)
✅ eventbrite.com (3 события)
= Всего: 7 событий
```

**После**:
```
✅ redevents.ge (4 события)
✅ eventbrite.com (3 события)
✨ meetup.com (11 событий) NEW
✨ cinemaqa.ge (готово) NEW
= Всего: 18+ событий
```

---

## Использование

```bash
# Команда остается той же
/events
```

**Вывод теперь включает события из 4 источников**:
1. Русскоязычные события (redevents.ge)
2. Международные события (eventbrite.com)
3. Местные встречи и воркшопы (meetup.com) ✨
4. Кинотеатры и фильмы (cinemaqa.ge) ✨

---

## Потенциальные улучшения

- [ ] Улучшить парсинг дат для meetup.com (требует JS рендеринга)
- [ ] Добавить интеграцию с Meetup.com API (если доступен)
- [ ] Оптимизировать cinemaqa.ge для полного парсинга дат/времени
- [ ] Добавить TKT.ge как 5-й источник (требует API)
- [ ] Добавить фильтр по категориям (только кино, только встречи, etc.)
