# Docker Logging Guide

## Быстрый старт

### Запустить бот с логами в Docker
```bash
docker-compose up
```

### Просмотреть логи в реальном времени
```bash
docker logs -f notification-bot
```

### Просмотреть только ошибки
```bash
docker logs notification-bot 2>&1 | grep -i error
```

### Сохранить логи в файл
```bash
docker logs notification-bot > bot_logs.txt 2>&1
```

## Формат Логов

### JSON Format (Docker)
```json
{
  "timestamp": "2026-05-09T08:00:01.234Z",
  "level": "INFO",
  "logger": "src.bot.scheduler",
  "message": "🌅 Starting morning digest for user 123"
}
```

### Local Format
```
2026-05-09 08:00:01 | src.bot.scheduler | INFO | 🌅 Starting morning digest for user 123
```

## Переменные Окружения

### LOG_LEVEL (по умолчанию: INFO)
```bash
# DEBUG - максимум информации
docker-compose -e LOG_LEVEL=DEBUG up

# INFO - основные события (по умолчанию)
docker-compose -e LOG_LEVEL=INFO up

# WARNING - только важные предупреждения
docker-compose -e LOG_LEVEL=WARNING up

# ERROR - только ошибки
docker-compose -e LOG_LEVEL=ERROR up
```

### DOCKER_MODE (по умолчанию: true в Docker)
```bash
# Для локальной разработки (читаемый формат)
DOCKER_MODE=false python src/main.py

# Для Docker (JSON формат)
DOCKER_MODE=true python src/main.py
```

## Команды для Docker Logs

### Смотреть последние 100 строк
```bash
docker logs --tail 100 notification-bot
```

### Смотреть логи за последний час
```bash
docker logs --since 1h notification-bot
```

### Смотреть логи без timestamps
```bash
docker logs --no-timestamps notification-bot
```

### Комбинированные фильтры
```bash
# Только ERROR логи в реальном времени
docker logs -f notification-bot 2>&1 | grep -i '"level":"ERROR"'

# Только INFO логи
docker logs notification-bot 2>&1 | grep -i '"level":"INFO"'

# Логи от конкретного модуля
docker logs notification-bot 2>&1 | grep 'src.ai.planner_agent'

# Логи с ключевым словом
docker logs notification-bot 2>&1 | grep 'Task #5'
```

## Интеграция с Log Aggregation

### Для ELK Stack (Elasticsearch, Logstash, Kibana)
JSON формат автоматически парсируется:
```bash
docker logs notification-bot | jq '.' # красивый вывод JSON
```

### Для Datadog / CloudWatch / Splunk
```bash
# JSON логи легко агрегируются в облако
docker-compose logs -f bot | jq '.message'
```

## Ошибки в Docker

### Смотреть только STDERR (ошибки)
```bash
docker logs notification-bot 2>&1 | grep -E '"level":"ERROR"'
```

### Полный stack trace ошибки
```bash
docker logs notification-bot | jq 'select(.level=="ERROR")'
```

### Отследить конкретную ошибку
```bash
# Найти все логи с "AI parsing failed"
docker logs notification-bot 2>&1 | grep "AI parsing failed"

# С полным контекстом
docker logs notification-bot | jq 'select(.message | contains("AI parsing failed"))'
```

## Пример Логов при Ошибке

```json
{
  "timestamp": "2026-05-09T08:00:02.456Z",
  "level": "ERROR",
  "logger": "src.ai.planner_agent",
  "message": "✗ AI parsing failed: JSONDecodeError",
  "exc_info": "json.decoder.JSONDecodeError: Expecting value: line 1 column 1"
}
```

## Setup для Production

### 1. Перенаправить логи в файл на хосте
```yaml
# docker-compose.yml
services:
  bot:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 2. Отправлять логи в syslog
```yaml
logging:
  driver: "syslog"
  options:
    syslog-address: "udp://localhost:514"
```

### 3. Отправлять в Datadog
```yaml
logging:
  driver: "json-file"
  options:
    labels: "service=notification-bot"
    # Datadog автоматически парсирует JSON логи
```

## Мониторинг Errors

### Real-time error monitoring
```bash
# Окно 1: смотрим only ERRORs
docker logs -f notification-bot 2>&1 | grep -E '"level":"ERROR"'

# Окно 2: смотрим all logs
docker logs -f notification-bot
```

### Email alert on critical errors (пример)
```bash
#!/bin/bash
docker logs notification-bot | grep -i '"level":"ERROR"' | while read line; do
  echo "$line" | mail -s "Bot Error Alert" admin@example.com
done
```

### Webhook notification (пример)
```bash
#!/bin/bash
docker logs notification-bot 2>&1 | jq -r 'select(.level=="ERROR") | .message' | while read msg; do
  curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK \
    -d "{\"text\": \"🔴 Bot Error: $msg\"}"
done
```

## Troubleshooting

### "No logs showing"
```bash
# Проверь что контейнер запущен
docker ps | grep notification-bot

# Проверь все логи с момента старта
docker logs notification-bot
```

### "Logs cut off / truncated"
```bash
# Увеличь буфер логов
docker logs --tail 1000 notification-bot

# Или сохрани в файл
docker logs notification-bot > full_logs.txt
```

### "Can't grep JSON"
```bash
# Правильный способ для JSON
docker logs notification-bot | jq 'select(.level=="ERROR")'

# Или парсить как текст
docker logs notification-bot | grep '"level":"ERROR"'
```

## Performance Tips

### Для больших объемов логов
```bash
# Используй tail вместо всех логов
docker logs --tail 100 -f notification-bot

# Или пайпи через jq для фильтрации
docker logs notification-bot | jq 'select(.level=="INFO")' | less
```

### Архивирование старых логов
```bash
# Сохрани логи перед очисткой
docker logs notification-bot > archive_$(date +%Y%m%d).log 2>&1

# Очисти логи контейнера (требует root)
docker logs --tail 0 -f notification-bot
```
