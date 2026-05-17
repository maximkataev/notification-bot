# Проверка баланса OpenAI в дайджесте

## Описание

В конец утреннего дайджеста добавлена информация о текущем балансе OpenAI аккаунта:

```
💳 Баланс OpenAI: $5.42
```

Если баланс менее 50 центов, дополнительное предупреждение:
```
💳 Баланс OpenAI: $0.32
⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!
```

## Требования

Функция работает только если:
1. ✅ API ключ сконфигурирован в Doppler (`OPENAI_API_KEY`)
2. ✅ Ключ имеет права доступа к billing endpoints

## Как настроить доступ к Billing API

OpenAI требует специальных прав для доступа к billing информации. Есть несколько вариантов:

### Вариант 1: Organization-level API key (рекомендуется)
1. Перейти в OpenAI Dashboard → Settings → Organization settings
2. Найти "API keys"
3. Убедиться, что используется организационный ключ (не пользовательский)
4. Убедиться, что ключ имеет права на "billing"

### Вариант 2: Использовать User-level API key
1. Убедиться, что у аккаунта есть доступ к billing
2. Перейти на https://platform.openai.com/account/billing/overview
3. Если есть доступ, значит можно использовать этот ключ

### Вариант 3: Альтернатива без billing API
Если у вас нет доступа к billing API:
1. Функция gracefully fails (не показывает баланс, но дайджест отправляется)
2. Можно проверять баланс вручную на https://platform.openai.com/account/billing/overview
3. Это безопасно — дайджест будет отправляться даже если баланс недоступен

## Как проверить

```bash
# С использованием Doppler (если ключ корректно сконфигурирован)
doppler run --project notifications-bot --config dev -- python3 test_openai_balance.py

# Должен вывести что-то типа:
# ✓ Balance fetched successfully
# 
# 💳 Баланс OpenAI: $5.42
```

## Если не работает

### Ошибка: "Could not fetch OpenAI balance from any endpoint"
Это означает, что текущий API ключ не имеет доступа к billing endpoints. Варианты:
1. ✅ Ничего не делать — функция gracefully fails, дайджест отправляется как обычно
2. Использовать другой ключ (Organization-level вместо User-level)
3. Проверить на https://platform.openai.com/account/billing/overview есть ли у аккаунта доступ к billing

### Ошибка: "The api_key client option must be set"
Ключ не сконфигурирован. Решение:
```bash
doppler secrets set OPENAI_API_KEY <ваш-ключ>
```

## Как это работает

### Механизм получения баланса

1. **Method 1: OpenAI SDK Billing API** (новые версии)
   ```python
   credit_grants = await client.billing.credit_grants.list()
   ```

2. **Method 2: Direct HTTP request к billing endpoints**
   ```
   GET /v1/billing/credit_grants
   GET /v1/billing/usage
   ```

3. **Fallback**: Если оба метода не работают, функция возвращает `None`

### Интеграция в scheduler

```python
# В конце дайджеста, перед отправкой
openai_balance = await get_openai_balance()
if openai_balance is not None:
    balance_text = format_balance(openai_balance)
    message_lines.append(balance_text)
```

## Примеры вывода

### Здоровый баланс
```
💳 Баланс OpenAI: $12.50
```

### Низкий баланс (< $0.50)
```
💳 Баланс OpenAI: $0.32
⚠️  Баланс менее 50¢ — рекомендуется пополнить аккаунт!
```

### Баланс недоступен
```
(строка не выводится, дайджест отправляется без баланса)
```

## Безопасность

- API ключ используется только для запроса к OpenAI billing API
- Баланс не сохраняется в БД
- Информация доступна только в Telegram дайджесте
- Ключ не логируется в открытом виде

## Тестирование

```bash
# Запустить тест
PYTHONPATH=. doppler run --project notifications-bot --config dev -- python3 test_openai_balance.py

# Или просто отправить /digest в бот
# Баланс появится в конце дайджеста (если доступен)
```

## Файлы

| Файл | Описание |
|------|---------|
| `src/workers/openai_balance.py` | Функции для получения баланса |
| `test_openai_balance.py` | Тестовый скрипт |
| `src/bot/scheduler.py` | Интеграция в дайджест |

---

**Статус**: ✓ Реализовано и интегрировано  
**Требует**: Специальные права на OpenAI API ключе  
**Fallback**: Graceful failure если баланс не доступен
