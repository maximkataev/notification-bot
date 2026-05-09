# Улучшение: Проверка баланса OpenAI в дайджесте

## Что было добавлено

### ✅ Информация о балансе OpenAI в конце дайджеста

Теперь дайджест показывает текущий баланс OpenAI аккаунта в конце сообщения.

**Нормальный баланс**:
```
💳 Баланс OpenAI: $5.42
```

**Низкий баланс** (< $0.50):
```
💳 Баланс OpenAI: $0.32
⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!
```

**Если баланс недоступен**:
- Строка не выводится
- Дайджест отправляется как обычно
- Нет ошибок в логах

## Как это работает

### Механизм получения баланса

1. **Method 1**: OpenAI SDK Billing API
   ```python
   credit_grants = await client.billing.credit_grants.list()
   ```

2. **Method 2**: Direct HTTP request
   ```
   GET /v1/billing/credit_grants
   ```

3. **Graceful Fallback**: Если оба не работают, просто не показываем баланс

### Требования

- ✅ API ключ в Doppler (`OPENAI_API_KEY`)
- ✅ Ключ должен иметь доступ к billing (Organization-level ключи обычно имеют)

**Если ключ не имеет доступа**: Функция gracefully fails, дайджест отправляется без баланса

## Файлы, измененные/созданные

| Файл | Изменение | Статус |
|------|-----------|--------|
| `src/workers/openai_balance.py` | Новая функция получения баланса | ✓ Создан |
| `src/bot/scheduler.py` | Интеграция в конец дайджеста | ✓ Обновлен |
| `CLAUDE.md` | Добавлен раздел про OpenAI Balance | ✓ Обновлен |
| `OPENAI_BALANCE.md` | Полная документация | ✓ Создан |
| `test_openai_balance.py` | Тестовый скрипт | ✓ Создан |

## Как использовать

### В реальном дайджесте
```
1. Убедитесь, что OPENAI_API_KEY настроен в Doppler
2. Отправьте /digest в бот или подождите 08:00
3. В конце дайджеста появится баланс OpenAI
```

### Для проверки
```bash
# Проверить доступность баланса
doppler run --project notifications-bot --config dev -- python3 test_openai_balance.py

# Должен вывести:
# ✓ Balance fetched successfully
# 💳 Баланс OpenAI: $X.XX
```

### Если баланс недоступен
```bash
# Это нормально для некоторых API ключей
# Дайджест будет отправлен без баланса
```

## Структура кода

### `src/workers/openai_balance.py`

```python
async def get_openai_balance() -> Optional[float]:
    """Get OpenAI account balance in USD.
    
    Returns:
        Balance amount or None if API call fails
    """

def format_balance(balance: Optional[float]) -> str:
    """Format balance for display.
    
    Returns:
        Formatted string with balance and warning if needed
    """
```

### Интеграция в `src/bot/scheduler.py`

```python
# В конце дайджеста, перед отправкой
openai_balance = await get_openai_balance()
if openai_balance is not None:
    balance_text = format_balance(openai_balance)
    message_lines.append(balance_text)
    message_lines.append("")
```

## Настройка доступа к Billing API

### Если ключ не имеет доступа

**Вариант 1: Использовать Organization-level ключ** (рекомендуется)
1. OpenAI Dashboard → Settings → Organization settings
2. Найти API keys
3. Использовать организационный ключ (не пользовательский)

**Вариант 2: Проверить доступ аккаунта**
1. Перейти на https://platform.openai.com/account/billing/overview
2. Если есть доступ, можно использовать этот ключ

**Вариант 3: Ничего не делать**
- Функция gracefully fails
- Дайджест отправляется без баланса
- Все работает как раньше

## Безопасность

- ✓ API ключ используется только для billing запроса
- ✓ Баланс не сохраняется в БД
- ✓ Информация видна только в Telegram
- ✓ Ключ не логируется в открытом виде

## Примеры вывода в дайджесте

### Полный дайджест с балансом
```
🌅 Доброе утро! Сегодня...

Погода: 🌤️ Ясно, +18°C
...
Ваши дела на сегодня:
• Купить молоко
...
Курсы валют:
BTC: 80 819 USD (↑ 0.9% for 24h, ↑ 11.7 % for 30d)
...
💳 Баланс OpenAI: $5.42
```

### С предупреждением о низком балансе
```
...
💳 Баланс OpenAI: $0.32
⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!
```

## Дополнительная информация

Полная документация: [OPENAI_BALANCE.md](OPENAI_BALANCE.md)

Техническая справка: [CLAUDE.md](CLAUDE.md) раздел "OpenAI Balance Monitor"

---

**Статус**: ✓ Полностью реализовано и документировано  
**Дата**: 2026-05-09  
**Ответственный**: Claude Code
