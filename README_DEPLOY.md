# notification-bot Deployment Guide

Быстрый старт деплоя на OVHCloud VPS с GitHub Actions.

## 🚀 Quick Start

### 1. GitHub Secrets (5 min)

Добавьте в GitHub → Settings → Secrets and variables → Actions:

```
DOCKER_HUB_USERNAME     = your_docker_hub_username
DOCKER_ACCESS_TOKEN     = dckr_pat_xxxxxxx  (from hub.docker.com/settings/security)
SERVER_HOST             = 123.45.67.89
SERVER_ADMIN_USER       = root
SERVER_ADMIN_PASSWORD   = your_vps_password
SERVER_PORT             = 22
```

### 2. VPS Setup (10 min)

На VPS:

```bash
# Подключиться
ssh root@<VPS_IP>

# Создать директорию
mkdir -p /opt/notification-bot
cd /opt/notification-bot

# Клонировать репо
git init
git remote add origin https://github.com/your-username/notification-bot.git
git fetch origin main
git checkout main

# Создать .env
cat > .env << 'EOF'
DOCKER_HUB_USERNAME=your_docker_hub_username
NOTIFICATION_BOT_DOPPLER_TOKEN=your_doppler_token
EOF

chmod 600 .env

# Скопировать redeploy скрипт
cp scripts/redeploy-notification-bot.sh /opt/redeploy-notification-bot.sh
chmod +x /opt/redeploy-notification-bot.sh

# Создать директории для данных
mkdir -p /opt/notification-bot/{data,logs}
```

### 3. First Deploy (5 min)

На локальной машине:

```bash
git add .
git commit -m "setup: deploy to OVHCloud with Docker Hub"
git push origin main
```

Это триггирует GitHub Actions. На VPS (после успеха Actions):

```bash
cd /opt/notification-bot
source .env
docker compose pull
docker compose up -d --force-recreate --remove-orphans
```

### 4. Verify (2 min)

```bash
# Проверьте контейнер
docker compose ps

# Проверьте логи
docker logs -f notification-bot --tail 20

# Тестируйте в Telegram: /ping
# Должны получить: 🏓 pong
```

## 📚 Полная документация

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — архитектура бота, все компоненты
- **[DEPLOY_SETUP.md](DEPLOY_SETUP.md)** — детальная инструкция (13 разделов)
- **[DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md)** — чек-лист для проверки
- **[DEPLOYMENT_READY.md](DEPLOYMENT_READY.md)** — статус и требования

## 🔄 Как работает автоматический деплой

```
git push origin main
    ↓
GitHub Actions triggered
    ↓
Build Docker image → Push to Docker Hub
    ↓
SSH на VPS → /opt/redeploy-notification-bot.sh
    ↓
docker compose pull && docker compose up -d
    ↓
✅ Bot restarted с новым кодом
```

## 📋 Команды на VPS

```bash
# Статус
docker compose ps
docker logs -f notification-bot

# Перезагрузка
docker compose restart

# Остановка
docker compose down

# Логи файл
tail -f /opt/notification-bot/logs/log.log

# Тестирование
docker exec notification-bot doppler secrets
```

## ⚡ Troubleshooting

**Контейнер не запускается?**
```bash
docker logs notification-bot
```

**Doppler недоступен?**
```bash
docker exec notification-bot doppler secrets
# Проверьте DOPPLER_TOKEN в .env
```

**GitHub Actions fail?**
- Проверьте GitHub Actions → Latest workflow
- Убедитесь что Docker Hub credentials правильные
- Убедитесь что VPS доступен по SSH

## 📦 Files Changed

- `.github/workflows/deploy.yml` — GitHub Actions workflow (build + push + redeploy)
- `docker-compose.yml` — обновлён для Docker Hub образов
- `Dockerfile` — обновлён для запуска с Doppler
- `scripts/redeploy-notification-bot.sh` — VPS redeploy скрипт
- `src/utils/logging_config.py` — логирование в файл
- `src/bot/main.py` — добавлена команда /ping

## ✅ Features

- ✨ Автоматический деплой при push в main
- 🐳 Docker Hub для хранения образов
- 📊 JSON логирование в stdout
- 📝 Логи в файл `/app/logs/log.log`
- 🔄 Автоматический restart при сбое
- 🔐 Doppler для управления секретами
- 🏓 /ping команда для проверки статуса

## 📡 Background Monitors

Бот запускает несколько асинхронных мониторов:

1. **Currency Monitor** — отслеживает EUR/USD rate
   - Запускается каждые 5 минут
   - Алерт если rate > 1.18 (1 раз в 24 часа)
   
2. **Water Cut Monitor** — мониторит отключения воды
   - Запускается каждый час
   - Скрепит GWP website (Playwright Chromium)
   - Проверяет Vazha Iverievi улицу
   - Алерт при обнаружении (1 раз в 24 часа)

3. **Football Matches** — отслеживает матчи
   - Barcelona и Real Madrid priority
   - API-Football endpoint (free)

## 🎯 Next Steps

1. Добавьте GitHub Secrets (6 значений)
2. Настройте VPS по инструкции (10 минут)
3. Сделайте первый деплой (ручной)
4. Проверьте что всё работает (5 минут)

**Дальше GitHub Actions будет автоматически деплоить при каждом push в main.**

## ✅ Post-Deployment Verification

После первого деплоя проверьте:

```bash
# 1. Контейнер живой
docker compose ps

# 2. Логирование работает
docker logs -f notification-bot

# 3. Мониторы запустились
docker logs notification-bot | grep "monitor started"

# 4. В Telegram отправьте /ping
# Должны получить: 🏓 pong

# 5. Проверьте логи файл
docker exec notification-bot tail -f /app/logs/log.log
```

## 🔍 Important Notes

- **Playwright**: Dockerfile автоматически устанавливает Chromium
- **Doppler**: Используется в контейнере для получения секретов
- **Background Tasks**: Мониторы работают параллельно с основным ботом
- **Logging**: JSON к stdout, readable к файлу, errors к stderr

---

📖 **Дополнительная информация**: см. [DEPLOY_SETUP.md](DEPLOY_SETUP.md)
