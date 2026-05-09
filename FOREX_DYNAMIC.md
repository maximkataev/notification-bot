# EUR/USD и USD/RUB Динамика цен

## Общее описание

Дайджест показывает динамику изменения цен для всех валютных пар — BTC, ETH, EUR и RUB — как за 24 часа, так и за 30 дней.

## Архитектура

### Источник данных

**Крипто (BTC, ETH)**:
- Источник: CoinGecko API (`/coins/bitcoin` и `/coins/ethereum`)
- Данные включают: текущая цена и официальные `price_change_percentage_24h`, `price_change_percentage_30d`
- Надежность: высокая (официальные метрики от CoinGecko)

**Форекс (EUR/USD, USD/RUB)**:
- Основной метод: Yahoo Finance API (через yfinance библиотеку)
  - Загружаем исторические дневные данные EURUSD=X и USDRUB=X за последний месяц
  - Вычисляем 24h изменение (сегодня vs вчера)
  - Вычисляем 30d изменение (сегодня vs 30 дней назад)
  - Абсолютно точные данные валютного рынка
- Преимущества:
  - Бесплатный доступ без API ключей
  - Настоящие исторические данные форекса (не производная от крипто)
  - Надежный источник (Yahoo Finance)

### Функции

#### `get_crypto_and_forex_rates()` (rates_fetcher.py)
Основная функция, которая:
1. Запрашивает текущие цены BTC и ETH от CoinGecko
2. Получает текущие курсы USD→EUR и USD→RUB от exchangerate-api.com
3. Вычисляет исторические изменения через `get_historical_forex_rates()` (Yahoo Finance)
4. Возвращает словарь со всеми данными:
   ```python
   {
       "btc_usd": 80819.0,
       "btc_change_24h": 0.9,
       "btc_change_30d": 11.7,
       "eth_usd": 2327.88,
       "eth_change_24h": 0.5,
       "eth_change_30d": 4.7,
       "usd_eur": 0.849,      # USD→EUR rate
       "eur_change_24h": -0.4,
       "eur_change_30d": -0.9,
       "usd_rub": 74.59,      # USD→RUB rate
       "rub_change_24h": -0.7,
       "rub_change_30d": -5.5,
   }
   ```

#### `get_historical_forex_rates()` (rates_fetcher.py)
Получает исторические изменения через Yahoo Finance:
1. Загружает EURUSD=X за последний месяц
2. Загружает USDRUB=X за последний месяц
3. Вычисляет 24h изменение (последний день vs день до)
4. Вычисляет 30d изменение (последний день vs первый день в периоде)
5. Возвращает процентные изменения

#### `_get_historical_from_yahoo_finance()` (rates_fetcher.py)
Низкоуровневая функция yfinance:
```python
eur_usd = yf.download("EURUSD=X", period="1mo", interval="1d", progress=False)
rub_usd = yf.download("USDRUB=X", period="1mo", interval="1d", progress=False)
# Вычисляем изменения из Close цен
```

#### `format_change()` (scheduler.py)
Форматирует данные для вывода:
```python
def format_change(change_24h, change_30d) -> str:
    if change_24h is None or change_30d is None:
        return ""
    arrow_24h = "↑" if change_24h >= 0 else "↓"
    arrow_30d = "↑" if change_30d >= 0 else "↓"
    return f" ({arrow_24h} {abs(change_24h):.1f}% for 24h, {arrow_30d} {abs(change_30d):.1f} % for 30d)"
```

### Вывод в дайджест

```
Курсы валют:
BTC: 80 786 USD (↑ 0.7% for 24h, ↑ 12.4 % for 30d)
ETH: 2 328.39 USD (↑ 0.7% for 24h, ↑ 5.5 % for 30d)
EUR: 1.17786 USD (↓ 0.4% for 24h, ↓ 0.9 % for 30d)
USD: 74.59 RUB (↓ 0.7% for 24h, ↓ 5.5 % for 30d)
```

## Зависимости

Требуемые пакеты добавлены в `requirements.txt`:
```
yfinance==0.2.33
pandas>=2.0.0
```

Установка:
```bash
pip install -r requirements.txt
```

## Механизм обработки ошибок

Если `get_historical_forex_rates()` не может получить данные:
1. Функция логирует ошибку
2. Возвращает пустой словарь `{}`
3. В `get_crypto_and_forex_rates()` изменения будут `None`
4. В дайджесте будут отображаться только текущие курсы без динамики

```
EUR: 1.17786 USD
USD: 74.59 RUB
```

Это нормально — основные курсы всегда доступны, динамика является дополнительной информацией.

## Математика

```
Изменение за 24 часа = (цена_сегодня - цена_вчера) / цена_вчера * 100%
Изменение за 30 дней = (цена_сегодня - цена_месяц_назад) / цена_месяц_назад * 100%
```

Для EUR/USD: yfinance возвращает USD/EUR (инверсия), поэтому нужно инвертировать:
```python
eur_usd_today = 1.0 / float(eur_close.iloc[-1])
```

## Тестирование

```bash
# Протестировать получение всех курсов с динамикой
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

## Известные ограничения

1. **Выходные и праздники**
   - На выходных нет торговли, могут быть пропуски в данных
   - Используются доступные дневные данные

2. **Минимум 5 дней данных для 30d расчета**
   - Если менее 5 дней доступно, 30d изменение будет `None`

3. **Yahoo Finance может быть недоступен**
   - В редких случаях yfinance скачивания могут быть медленными или неудачными
   - Дайджест все еще отправится с текущими курсами

## История изменений

**2026-05-10**: Переход с BTC-based вычисления на Yahoo Finance (yfinance) для прямого доступа к историческим данным форекса.

---

**Текущее состояние**: ✓ Полностью реализовано и работает с Yahoo Finance
**Последнее обновление**: 2026-05-10
