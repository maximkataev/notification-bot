# OVHCloud VPS Setup for notification-bot

Полная инструкция по настройке notification-bot на OVHCloud VPS.

## 0. Важные замечания о проекте

### Зависимости
Проект использует:
- **Playwright** для веб-скрепинга (GWP сайт, water cuts)
- **Doppler** для управления секретами
- **gpt-5.4-mini** для парсинга задач и генерации дайджеста

### Background Monitors
Бот запускает несколько асинхронных мониторов:
1. **CurrencyMonitor** — отслеживает EUR/USD rate (каждые 5 минут)
2. **WaterCutMonitor** — мониторит отключения воды (каждый час)
3. **Football Matches** — может отслеживать матчи Barcelona/Real Madrid

### Требования Docker образа
- Python 3.11 slim
- System libraries для Playwright Chromium
- Doppler CLI для получения секретов

---

## 1. Подготовка на VPS

### 1.1 Подключитесь к VPS
```bash
ssh root@<VPS_IP>
```

### 1.2 Создайте директорию для приложения
```bash
mkdir -p /opt/notification-bot
cd /opt/notification-bot

# Инициализируйте git репозиторий
git init
git remote add origin https://github.com/your-username/notification-bot.git
git fetch origin main
git checkout main
```

### 1.3 Создайте необходимые директории
```bash
mkdir -p /opt/notification-bot/data
mkdir -p /opt/notification-bot/logs

# Установите правильные права доступа
chmod 755 /opt/notification-bot
```

### 1.4 Скопируйте redeploy скрипт
```bash
cp scripts/redeploy-notification-bot.sh /opt/redeploy-notification-bot.sh
chmod +x /opt/redeploy-notification-bot.sh
```

## 2. Настройка переменных окружения на VPS

### 2.1 Создайте файл .env на VPS
```bash
cat > /opt/notification-bot/.env << 'EOF'
# Docker Hub credentials (для вытягивания образов)
DOCKER_HUB_USERNAME=your_docker_hub_username
NOTIFICATION_BOT_DOPPLER_TOKEN=your_doppler_token_here

# Логирование (опционально)
LOG_LEVEL=INFO
EOF
```

**Важно**: Не коммитьте .env в git!

### 2.2 Установите права доступа
```bash
chmod 600 /opt/notification-bot/.env
```

## 3. GitHub Actions Secrets

Добавьте следующие secrets в GitHub (Settings → Secrets and variables → Actions):

| Secret | Value | Description |
|--------|-------|-------------|
| `DOCKER_HUB_USERNAME` | ваше имя на Docker Hub | Используется для build и push образов |
| `DOCKER_ACCESS_TOKEN` | ваш token Docker Hub | [Создать тут](https://hub.docker.com/settings/security) |
| `SERVER_HOST` | IP или домен VPS | Например: 123.45.67.89 |
| `SERVER_ADMIN_USER` | пользователь SSH | Обычно: root |
| `SERVER_ADMIN_PASSWORD` | пароль SSH | Или используйте SSH key |
| `SERVER_PORT` | SSH порт | Обычно: 22 |

### Пример значений:
```
DOCKER_HUB_USERNAME: maximkataev
DOCKER_ACCESS_TOKEN: dckr_pat_xxxxxxxxxxxxx
SERVER_HOST: 123.45.67.89
SERVER_ADMIN_USER: root
SERVER_ADMIN_PASSWORD: your_password_here
SERVER_PORT: 22
```

**⚠️ Безопасность**: Не коммитьте эти значения в код!

## 4. Первый деплой (ручной)

### 4.1 На локальной машине
```bash
# Убедитесь что всё закоммичено
git status
git add .
git commit -m "setup: docker deployment with Docker Hub and redeploy script"
git push origin main

# Это должно триггерить GitHub Actions workflow
```

### 4.2 На VPS (параллельно)
```bash
# Проверьте что Docker и docker-compose установлены
docker --version
docker-compose --version

# Если нет - установите:
# apt-get update && apt-get install -y docker.io docker-compose

# Убедитесь что docker daemon запущен
systemctl status docker

# Залогиньтесь в Docker Hub (используя значения из .env)
docker login -u your_docker_hub_username -p your_docker_access_token
```

### 4.3 Проверьте GitHub Actions
```bash
# На GitHub перейдите в: Actions → latest workflow
# Дождитесь завершения build-notification-bot job

# Проверьте что образ успешно pushed на Docker Hub:
# https://hub.docker.com/r/your_username/notification-bot
```

### 4.4 Запустите redeploy скрипт (после успеха GitHub Actions)
```bash
# На VPS
cd /opt/notification-bot
source .env
docker compose pull
docker compose up -d --force-recreate --remove-orphans
```

## 5. Верификация деплоя

### 5.1 Проверьте контейнер
```bash
docker compose ps
docker logs -f notification-bot --tail 20
```

### 5.2 Проверьте логи
```bash
# Логи в контейнере
docker exec notification-bot tail -f /app/logs/log.log

# Логи на хосте
tail -f /opt/notification-bot/logs/log.log
```

### 5.3 Тестируйте бота
```bash
# Отправьте /ping команду в Telegram
# Должны получить: 🏓 pong

# Отправьте /info команду
# Должны получить список всех команд

# Отправьте /debug команду
# Должны получить ваш user_id и chat_id
```

### 5.4 Проверьте что нет ошибок
```bash
docker logs notification-bot | grep -i error
```

## 6. Автоматический деплой (GitHub Actions)

После того как всё работает вручную, GitHub Actions автоматически:

1. **Build** — собирает Docker образ при каждом push в main
2. **Push** — отправляет образ на Docker Hub
3. **Redeploy** — SSH на VPS и запускает `/opt/redeploy-notification-bot.sh`

Скрипт автоматически:
- Вытягивает свежий образ: `docker compose pull`
- Перезапускает контейнер: `docker compose up -d --force-recreate`
- Удаляет orphan контейнеры: `--remove-orphans`

## 7. Мониторинг и обслуживание

### 7.1 Проверить статус
```bash
docker compose ps
```

### 7.2 Перезагрузить контейнер вручную
```bash
cd /opt/notification-bot
docker compose restart notification-bot
```

### 7.3 Просмотреть логи
```bash
# Last 50 lines
docker logs notification-bot --tail 50

# Real-time
docker logs -f notification-bot

# Файл логов
tail -f /opt/notification-bot/logs/log.log
```

### 7.4 Остановить контейнер
```bash
docker compose down
```

## 8. Управление данными

### 8.1 Резервная копия базы данных
```bash
# Скопировать data директорию
cp -r /opt/notification-bot/data /opt/notification-bot/data.backup.$(date +%Y%m%d)

# Или через SSH с локальной машины
scp -r root@<VPS_IP>:/opt/notification-bot/data ./notification-bot-data-backup
```

### 8.2 Восстановление
```bash
# На VPS
cp -r /opt/notification-bot/data.backup.20260510/* /opt/notification-bot/data/
docker compose restart
```

## 9. Обновление бота

### Вариант 1: Через GitHub (рекомендуется)
```bash
# На локальной машине
git add .
git commit -m "feature: add new functionality"
git push origin main

# GitHub Actions автоматически:
# 1. Собирает новый образ
# 2. Pushит на Docker Hub
# 3. SSH на VPS и перезагружает контейнер
```

### Вариант 2: Ручной обновления на VPS
```bash
cd /opt/notification-bot
git pull origin main
docker compose build --no-cache
docker compose up -d --force-recreate
```

## 10. Интеграция с другими контейнерами

Если у вас уже есть другие контейнеры на VPS:

### 10.1 Проверьте существующие сервисы
```bash
docker ps
docker network ls
```

### 10.2 Если нужна сетевая интеграция
Обновите docker-compose.yml:
```yaml
services:
  notification-bot:
    networks:
      - existing-network  # или shared-network

networks:
  existing-network:
    external: true  # используем существующую сеть
```

### 10.3 Если контейнеры нужно перезапускать вместе
Создайте единый docker-compose.yml или используйте orchestrator.

## 11. Резервные копии и восстановление

### 11.1 Автоматическая резервная копия логов
```bash
# Добавьте в cron (например, каждый день в 00:00)
crontab -e

# Добавьте строку:
0 0 * * * tar -czf /opt/backups/notification-bot-logs-$(date +\%Y\%m\%d).tar.gz /opt/notification-bot/logs
```

### 11.2 Монитор дискового пространства
```bash
df -h /opt/notification-bot
du -sh /opt/notification-bot/logs
```

## 12. Мониторинг фоновых задач

### 12.1 Проверить что мониторы запустились
```bash
docker logs notification-bot | grep -i "monitor started"
# Должны видеть:
# - "Currency monitor started in background"
# - "Water cut monitor started in background"
```

### 12.2 Проверить логи конкретного монитора
```bash
# Currency monitor logs
docker logs notification-bot | grep -i "currency"

# Water cut monitor logs
docker logs notification-bot | grep -i "water"

# Football matches logs (если в digest включены)
docker logs notification-bot | grep -i "football"
```

### 12.3 Проверить что мониторы живы
```bash
# Проверить процесс
docker top notification-bot

# Если мониторы упали - перезагрузить контейнер
docker compose restart
```

### 12.4 Проверить alerting
```bash
# Искать сообщения о EUR/USD alert
docker logs notification-bot | grep -i "currency alert"

# Искать сообщения о воде
docker logs notification-bot | grep -i "water cut"
```

---

## 13. Troubleshooting

### Контейнер не запускается
```bash
docker logs notification-bot
docker compose logs notification-bot
```

### Doppler доступ недоступен
```bash
# Проверьте DOPPLER_TOKEN в .env
cat /opt/notification-bot/.env | grep DOPPLER

# Проверьте что токен правильный
docker exec notification-bot doppler secrets
```

### Диск переполнен
```bash
# Проверьте размер логов
du -sh /opt/notification-bot/logs

# Архивируйте старые логи
tar -czf /opt/notification-bot/logs/archive-$(date +%Y%m%d).tar.gz /opt/notification-bot/logs/log.log
> /opt/notification-bot/logs/log.log  # Очистить текущий лог
```

### GitHub Actions fails
```bash
# Проверьте GitHub Actions logs
# GitHub → Actions → Latest workflow run

# Обычные ошибки:
# - Docker Hub credentials неправильные
# - SERVER_HOST или SERVER_ADMIN_PASSWORD неправильные
# - SSH порт неправильный
```

### Currency Monitor не работает
```bash
# Проверьте логи
docker logs notification-bot | grep -i currency

# Обычные ошибки:
# - API timeout (exchangerate-api.com недоступен)
# - Неправильный JSON response
# - Rate limit на API

# Решение: перезагрузить контейнер
docker compose restart
```

### Water Cut Monitor не отправляет алерты
```bash
# Проверьте что работает GWP скрепер
docker logs notification-bot | grep -i "water cut"

# Проверьте что Playwright установлен
docker exec notification-bot python -c "import playwright; print(playwright.__version__)"

# Если ошибка browser not found:
# Dockerfile должен содержать: RUN python3 -m playwright install chromium
```

### Playwright не работает
```bash
# Проверьте что Chromium установлен в контейнере
docker exec notification-bot ls -la /root/.cache/ms-playwright

# Если пусто - переустроить образ без кэша
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## Быстрый справочник команд

```bash
# Статус
docker compose ps
docker logs -f notification-bot

# Управление
docker compose up -d
docker compose down
docker compose restart

# Проверка
docker exec notification-bot doppler secrets
docker exec notification-bot tail -f /app/logs/log.log

# Обновление
git pull origin main
docker compose pull
docker compose up -d --force-recreate
```

---

**Версия**: май 2026  
**Проверено с**: OVHCloud VPS, Docker 24.0+, docker-compose 2.20+
