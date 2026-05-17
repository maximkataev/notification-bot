# 🔍 Диагностика Источников Мероприятий

**Дата**: 2026-05-17  
**Проблема**: Команда `/events` не загружает мероприятия из Тбилиси

---

## 📊 Статус Источников

| Источник | Статус | Проблема | Решение |
|----------|--------|---------|---------|
| **visitgeorgia.ge** | ❌ 404 | URL удален/изменен | Найти новый URL или API |
| **tkt.ge** | ⚠️ 200 OK но пусто | Next.js (JS-rendered) | Нужен Playwright/Puppeteer |
| **Meetup.com RSS** | ❌ 404 | RSS endpoint не существует | Найти новый endpoint |
| **mtavari.ge** | ❌ SSL Error | Сертификат hostname mismatch | Использовать другой источник |
| **arthall.ge** | ✅ 200 OK | Неправильная страница (786 bytes) | Найти правильный URL события |

---

## 🔧 Детальный Анализ

### 1. ❌ visitgeorgia.ge/en/events — 404 Not Found

**Проблема:**  
Главный источник мероприятий возвращает 404 — страница удалена или URL изменен.

```
GET https://www.visitgeorgia.ge/en/events
Status: 301 (redirect)
Location: https://visitgeorgia.ge/en/events
Final: 404 Not Found
```

**Решения:**
```bash
# Вариант 1: Проверить альтернативные URL
curl https://visitgeorgia.ge/en/
curl https://visitgeorgia.ge/en/calendar
curl https://visitgeorgia.ge/en/attractions

# Вариант 2: Использовать API если есть
# Проверить: https://api.visitgeorgia.ge/events
# или: https://www.visitgeorgia.ge/api/events
```

---

### 2. ⚠️ tkt.ge/en/events — 200 OK Но Пусто

**Проблема:**  
Сайт загружается (190KB), но HTML не содержит события. Это Next.js приложение, которое:
- Рендерит события на клиенте (JavaScript)
- Загружает данные из API AJAX
- BeautifulSoup не может парсить JS-rendered контент

```html
<!DOCTYPE html>
<html class="flex min-h-screen flex-col" lang="en">
  <head>...</head>
  <body>
    <div id="__next"><!-- Events loaded here by JavaScript --></div>
  </body>
</html>
```

**Решения:**

**Вариант 1: Найти API endpoint** (easiest)
```bash
# Открыть DevTools (F12) → Network tab → искать XHR requests
# Вероятно есть API вроде:
# https://api.tkt.ge/events
# https://tkt.ge/api/v1/events
# https://tkt.ge/_next/data/*/en/events.json
```

**Вариант 2: Использовать Playwright** (для JS-rendering)
```python
from playwright.async_api import async_playwright

async def get_tkt_events():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://tkt.ge/en/events")
        await page.wait_for_selector(".event")  # Wait for JS to load
        html = await page.content()
        # Now parse with BeautifulSoup
```

---

### 3. ❌ Meetup.com RSS — 404 Not Found

**Проблема:**  
RSS endpoint больше не существует.

```
GET https://www.meetup.com/find/tbilisi/events/rss/xml/
Status: 404 Not Found
```

**Решения:**

**Вариант 1: Новый Meetup RSS endpoint**
```bash
# Попробовать другие форматы:
https://www.meetup.com/find/tbilisi/events/rss/
https://www.meetup.com/en-US/find/tbilisi/events/rss/

# Или через API (требует token):
https://api.meetup.com/find/events?sign=true&lon=44.7671&lat=41.7151&radius=2
```

**Вариант 2: Альтернативные события сайты Тбилиси**
```bash
# Eventbrite Tbilisi:
https://www.eventbrite.com/d/georgia--tbilisi/

# Ticketmaster (если есть для Грузии):
https://www.ticketmaster.com/

# Local Georgian sites:
https://www.ajaria.ge (Батуми, но есть события)
```

---

### 4. ❌ mtavari.ge — SSL Certificate Error

**Проблема:**  
SSL сертификат не валиден для этого хостнейма.

```
SSLCertVerificationError: certificate is not valid for 'mtavari.ge'
```

**Решение:**
```python
# Временный обход (НЕ рекомендуется для production):
verify=False  # ❌ ОПАСНО

# Лучше: использовать другой источник или связаться с администратором
```

---

### 5. ✅ arthall.ge — 200 OK Но Пусто

**Статус:** 200 OK, 786 bytes (слишком мало для событий)

**Проблема:**  
Вероятно перенаправлен на главную страницу.

```
GET https://arthall.ge/en/events
→ 301 https://arthall.ge/ka (грузинская версия)
```

---

## ✅ Рекомендуемые Действия

### Короткосрочно (Quick Fix)
```python
# В src/workers/tbilisi_events.py:

# 1. Удалить неработающие источники:
# - visitgeorgia.ge ❌
# - Meetup RSS ❌
# - mtavari.ge (SSL) ❌
# - arthall.ge (redirect) ❌

# 2. Оставить только:
# - tkt.ge (найти API или использовать Playwright)

# 3. Добавить новые источники:
# - Eventbrite API
# - Местные события сайты Грузии
```

### Долгосрочно (Proper Solution)
1. **Найти работающие API** для событий в Тбилиси
2. **Использовать Playwright** для JS-rendered сайтов
3. **Fallback цепь** (если один источник упал, пробовать следующий)
4. **Кеширование результатов** (не загружать каждый раз)

---

## 🔗 Возможные Источники

**Работающие API для событий:**
- [Eventbrite API](https://www.eventbrite.com/platform/api/)
- [SeatGeek API](https://platform.seatgeek.com/)
- [Ticketmaster API](https://developer.ticketmaster.com/)
- Локальные события сайты Грузии (нужно найти)

**Грузинские сайты:**
- https://geliving.com/ (lifestyle events)
- https://ajaria.ge/ (события Батуми)
- https://foursquare.com/ (места и события)

---

## 🛠️ Команда для Проверки

```bash
# Проверить статус всех источников:
python3 scripts/test_events_saturday.py

# Отправить команду боту:
/events

# Диагностика:
curl -I https://visitgeorgia.ge/en/events
curl -I https://tkt.ge/en/events
```

---

**Статус**: ⚠️ **ТРЕБУЕТСЯ ДЕЙСТВИЕ**  
**Приоритет**: HIGH (мероприятия не загружаются)  
**Автор**: Claude  
**Дата обновления**: 2026-05-17
