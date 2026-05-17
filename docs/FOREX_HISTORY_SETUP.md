# Динамика EUR/USD и USD/RUB — Настройка исторических данных

## Текущее состояние

Дайджест теперь показывает динамику EUR/USD и USD/RUB за 24h и 30d! 

```
EUR: 1.17786 USD (↓ 0.05% for 24h, ↑ 1.1 % for 30d)
USD: 74.59 RUB (↑ 0.0% for 24h, ↑ 5.8 % for 30d)
```

## Как это работает

### Вариант 1: База данных (долгосрочный подход) ✅ АКТИВНО

Система **автоматически** сохраняет курсы в базу данных при каждом запуске. Со временем накапливается история, и динамика становится доступна.

**Преимущества**:
- ✅ Работает без дополнительной настройки
- ✅ Надежно (не зависит от внешних API)
- ✅ Бесплатно

**Недостаток**:
- ⏳ Нужно 30+ дней для полной истории

### Вариант 2: Open Exchange Rates API (быстрый подход) 🚀 ОПЦИОНАЛЬНО

Если нужны данные прямо сейчас, можно подключить **Open Exchange Rates API** — бесплатный сервис с историей на 1+ год.

**Преимущества**:
- ✅ Данные доступны сразу
- ✅ Исторические данные за год
- ✅ 1000 запросов в месяц (более чем достаточно)

**Как подключить**:

1. Перейти на https://openexchangerates.org/
2. Нажать **"Sign up for free"**
3. Создать аккаунт (нужна только email)
4. Скопировать API ключ со страницы dashboard
5. Добавить в Doppler:
   ```bash
   doppler secrets set EXCHANGE_RATES_API_KEY <ваш-ключ>
   ```
6. Перезапустить бот

Готово! Теперь динамика будет показываться сразу.

## Как это работает технически

### Механизм

1. **При каждом дайджесте**:
   - Сохранить текущие курсы USD/EUR и USD/RUB в БД
   - Вычислить изменение за последние 24h и 30d

2. **Источник данных (приоритет)**:
   - Сначала пытаемся использовать БД (накопленная история)
   - Если БД пуста → пытаемся Open Exchange Rates API (если ключ есть)
   - Если оба не работают → показываем без динамики (но курсы есть)

### Код

```python
# Получить динамику EUR/USD за 24h и 30d
eur_change_24h = rates.get("eur_change_24h")  # float или None
eur_change_30d = rates.get("eur_change_30d")  # float или None

# Пример вывода:
# EUR: 1.17786 USD (↑ 0.5% for 24h, ↑ 1.1 % for 30d)
```

## Примеры вывода

### С полной динамикой (после 30+ дней)
```
Курсы валют:
BTC: 80 903 USD (↑ 0.9% for 24h, ↑ 12.5 % for 30d)
ETH: 2 332.06 USD (↑ 0.8% for 24h, ↑ 5.6 % for 30d)
EUR: 1.17786 USD (↑ 0.05% for 24h, ↑ 1.1 % for 30d)
USD: 74.59 RUB (↑ 0.0% for 24h, ↑ 5.8 % for 30d)
```

### Без динамики (в первые дни)
```
Курсы валют:
BTC: 80 903 USD (↑ 0.9% for 24h, ↑ 12.5 % for 30d)
ETH: 2 332.06 USD (↑ 0.8% for 24h, ↑ 5.6 % for 30d)
EUR: 1.17786 USD
USD: 74.59 RUB
```

## База данных

Таблица `exchange_rates`:
```sql
CREATE TABLE exchange_rates (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pair      TEXT NOT NULL,        -- "USD_EUR", "USD_RUB"
    rate      REAL NOT NULL,        -- 0.849, 74.59
    timestamp TEXT DEFAULT (datetime('now'))
)
```

**Вычисление изменения**:
```python
# Текущий курс
current = rates[-1]

# Курс 24h назад
rate_24h_ago = rates[-(24 hours)]

# Курс 30d назад
rate_30d_ago = rates[-(30 days)]

# Изменение
change_24h = (current - rate_24h_ago) / rate_24h_ago * 100
change_30d = (current - rate_30d_ago) / rate_30d_ago * 100
```

## Список бесплатных API для форекса

| API | Бесплатный уровень | История | Примечания |
|-----|-------------------|---------|-----------|
| **Open Exchange Rates** ⭐ | 1000/месяц | 1+ год | Рекомендуем |
| Fixer.io | 100/месяц | 📅 платный | Хороший, но мало бесплатных запросов |
| Alpha Vantage | 500/день | 20+ лет | Требует ждать между запросами |
| exchangerate.host | Неограниченно | Нет истории | Только текущие курсы |
| XE.com API | 300/месяц | Нет | Текущие курсы только |

## FAQ

**Вопрос**: Почему нет динамики в первые дни?
**Ответ**: Система только начала собирать историю. Подождите 30+ дней или подключите Open Exchange Rates API.

**Вопрос**: Можно ли использовать другой API?
**Ответ**: Да, можно добавить поддержку других API. Отредактируйте `src/workers/rates_fetcher.py`.

**Вопрос**: Как часто обновляются курсы?
**Ответ**: При каждом дайджесте (обычно 08:00 ежедневно) + при ручном запуске `/digest`.

**Вопрос**: Что если API ключ неправильный?
**Ответ**: Система gracefully falls back на БД. Проверьте ключ в Doppler.

## Дополнительно

### Проверить данные в БД
```bash
sqlite3 data/tasks.db "
SELECT pair, rate, timestamp FROM exchange_rates 
ORDER BY timestamp DESC LIMIT 20;
"
```

### Пересчитать вручную
```bash
PYTHONPATH=. python3 -c "
import asyncio
from src.workers.rates_fetcher import get_crypto_and_forex_rates

async def test():
    rates = await get_crypto_and_forex_rates()
    print('EUR 24h:', rates.get('eur_change_24h'))
    print('EUR 30d:', rates.get('eur_change_30d'))
    print('RUB 24h:', rates.get('rub_change_24h'))
    print('RUB 30d:', rates.get('rub_change_30d'))

asyncio.run(test())
"
```

---

**Статус**: ✅ Работает через БД | 🚀 Опционально: Open Exchange Rates API  
**Дата**: 2026-05-10  
**Документация**: [src/workers/rates_fetcher.py](src/workers/rates_fetcher.py)
