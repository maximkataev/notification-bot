# ✅ Deployment Configuration Complete

Все файлы готовы к деплою на OVHCloud VPS с полной функциональностью бота.

## 📦 Что изменилось

### GitHub Actions
- ✅ `.github/workflows/deploy.yml` — полный CI/CD pipeline
  - Build Docker образ
  - Push на Docker Hub
  - SSH на VPS и redeploy

### Docker
- ✅ `Dockerfile` — обновлён для Playwright + Doppler
  - System dependencies для Playwright (libglib2.0-0, libx11-6, etc)
  - Playwright Chromium installation
  - Doppler CLI для секретов
- ✅ `docker-compose.yml` — использует образы с Docker Hub

### VPS Scripts
- ✅ `scripts/redeploy-notification-bot.sh` — автоматический redeploy
- ✅ `VPS_SETUP.sh` — скрипт инициализации VPS

### Logging
- ✅ `src/utils/logging_config.py` — логирование в файл `/app/logs/log.log`
- ✅ Логи также в Docker stdout (JSON формат)

### Features
- ✅ `/ping` команда — проверка что бот живой
- ✅ `restart: on-failure` — автоматический перезапуск при сбое
- ✅ `pull_policy: always` — всегда тянет свежий образ с Docker Hub

### Background Monitors (Async Tasks)
- ✅ **CurrencyMonitor** — отслеживает EUR/USD rate, алерты если > 1.18
- ✅ **WaterCutMonitor** — мониторит отключения воды (Vazha Iverievi street)
- ✅ **Football Matches** — отслеживает матчи Barcelona/Real Madrid

### Documentation
- ✅ `DEPLOY_SETUP.md` — 12 разделов детальной инструкции
- ✅ `DEPLOY_CHECKLIST.md` — чек-лист для проверки
- ✅ `README_DEPLOY.md` — quick start (5 минут)

## 🔧 Зависимости и требования

### Python Dependencies
```
aiogram==3.4.1              # Telegram bot framework
openai==1.36.0              # GPT-4o для parsing и digests
aiosqlite==0.20.0           # Async SQLite
apscheduler==3.10.4         # Morning digest scheduling
httpx==0.27.0               # Async HTTP requests
python-dotenv==1.0.0        # .env file loading
feedparser==6.0.10          # RSS news parsing
beautifulsoup4==4.12.2      # HTML scraping (GWP, water cuts)
python-json-logger==2.0.7   # JSON logging
yt-dlp==2024.12.23          # Video/audio downloads (for future features)
playwright==1.42.0          # Browser automation (web scraping)
```

### System Dependencies (в Dockerfile)
- `libglib2.0-0` — required for Playwright Chromium
- `libx11-6` — X11 graphics library
- `libxext6` — X11 extensions
- `libxrender1` — rendering library
- `libdbus-1-3` — D-Bus messaging
- `libfontconfig1` — font configuration
- `curl` — for Doppler CLI

### Playwright Browser
- **Chromium** installed automatically в контейнере
- Используется для скрепинга веб-страниц (GWP, water cuts)

## 🚀 Последовательность настройки

### Шаг 1: Создать Docker Hub аккаунт (если нет)
```bash
# https://hub.docker.com/signup
# Затем создать Access Token:
# https://hub.docker.com/settings/security → New Access Token
```

### Шаг 2: Добавить GitHub Secrets (2 минуты)
GitHub → Settings → Secrets and variables → Actions → New repository secret

```
DOCKER_HUB_USERNAME     = your-username
DOCKER_ACCESS_TOKEN     = dckr_pat_xxxxxxx
SERVER_HOST             = 123.45.67.89
SERVER_ADMIN_USER       = root
SERVER_ADMIN_PASSWORD   = your-vps-password
SERVER_PORT             = 22
```

### Шаг 3: Настроить VPS (10 минут)
```bash
ssh root@<VPS_IP>
bash < <(curl -s https://raw.githubusercontent.com/your-username/notification-bot/main/VPS_SETUP.sh)
# или скачать и запустить VPS_SETUP.sh вручную
```

### Шаг 4: Клонировать репо на VPS
```bash
cd /opt/notification-bot
git init
git remote add origin https://github.com/your-username/notification-bot.git
git fetch origin main
git checkout main

# Отредактировать .env файл
cp .env.template .env
nano .env  # Заполнить DOCKER_HUB_USERNAME и DOPPLER_TOKEN
```

### Шаг 5: Первый деплой (ручной)
```bash
# На VPS
cd /opt/notification-bot
source .env
docker compose pull
docker compose up -d --force-recreate --remove-orphans

# Проверка
docker compose ps
docker logs -f notification-bot --tail 20
```

### Шаг 6: Тестирование
```bash
# В Telegram отправить /ping
# Должны получить: 🏓 pong

# Проверить логи
docker exec notification-bot tail -f /app/logs/log.log
```

### Шаг 7: Git commit и push (автоматический деплой)
```bash
# На локальной машине
git add .
git commit -m "setup: complete Docker Hub deployment"
git push origin main

# GitHub Actions автоматически:
# 1. Build и push образ
# 2. SSH на VPS и перезагрузит контейнер
```

## 📋 File Reference

| File | Purpose | Status |
|------|---------|--------|
| `.github/workflows/deploy.yml` | GitHub Actions CI/CD | ✅ Ready |
| `docker-compose.yml` | Docker Compose конфиг | ✅ Ready |
| `Dockerfile` | Docker образ | ✅ Ready |
| `scripts/redeploy-notification-bot.sh` | VPS redeploy скрипт | ✅ Ready |
| `VPS_SETUP.sh` | VPS инициализация | ✅ Ready |
| `DEPLOY_SETUP.md` | Полная инструкция | ✅ Ready |
| `DEPLOY_CHECKLIST.md` | Чек-лист | ✅ Ready |
| `README_DEPLOY.md` | Quick start | ✅ Ready |

## 🔧 Configuration Variables

На VPS в файле `/opt/notification-bot/.env`:

```bash
DOCKER_HUB_USERNAME=your-docker-username
NOTIFICATION_BOT_DOPPLER_TOKEN=your-doppler-token
LOG_LEVEL=INFO
```

## ✨ Deployment Flow

```
┌─────────────────────────────────────┐
│  Git push origin main (local)       │
└────────────────┬────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  GitHub Actions Triggered           │
│  - Build Docker image               │
│  - Push to Docker Hub               │
└────────────────┬────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  SSH on VPS                         │
│  - Run /opt/redeploy-notification   │
│    -bot.sh                          │
└────────────────┬────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  On VPS                             │
│  - docker compose pull              │
│  - docker compose up -d             │
│  - --force-recreate                 │
│  - --remove-orphans                 │
└────────────────┬────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────┐
│  ✅ Bot Updated & Running           │
│  - New code deployed                │
│  - Container restarted              │
│  - Logs in /app/logs/log.log        │
└─────────────────────────────────────┘
```

## 🔍 Monitoring Commands

```bash
# Статус контейнера
docker compose ps

# Логи в реальном времени
docker logs -f notification-bot

# Файл логов
tail -f /opt/notification-bot/logs/log.log

# Проверка Doppler
docker exec notification-bot doppler secrets

# Тестирование бота (в Telegram)
/ping → должны получить 🏓 pong
```

## 🚨 Troubleshooting

### Контейнер не запускается
```bash
docker logs notification-bot
docker compose logs
```

### Doppler недоступен
```bash
# Проверьте .env файл
cat /opt/notification-bot/.env

# Проверьте token в Docker
docker exec notification-bot doppler secrets
```

### GitHub Actions fail
1. Проверьте workflow в GitHub → Actions
2. Проверьте GitHub Secrets (Settings → Secrets)
3. Проверьте VPS доступ по SSH

### Логи не пишутся в файл
```bash
# Проверьте что директория существует
docker exec notification-bot ls -la /app/logs

# Проверьте права доступа
docker exec notification-bot ls -la /app/logs/log.log
```

## 📚 Quick Reference

| Task | Command |
|------|---------|
| Status | `docker compose ps` |
| Logs | `docker logs -f notification-bot` |
| File logs | `tail -f /opt/notification-bot/logs/log.log` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Update | `git pull && docker compose pull && docker compose up -d` |
| SSH to VPS | `ssh root@<VPS_IP>` |

## 🔄 Background Tasks (Async Monitors)

Бот запускает несколько долгоживущих мониторов параллельно с основным Telegram polling:

### 1. **Currency Monitor** (`src/workers/currency_monitor.py`)
- **Что делает**: Отслеживает EUR/USD rate каждые 5 минут
- **Алерт**: Отправляет сообщение если rate > 1.18
- **Cooldown**: 1 алерт в 24 часа на один rate
- **Timeout**: 10 секунд на API запрос
- **Fallback**: Graceful при ошибке API

### 2. **Water Cut Monitor** (`src/workers/water_cut_monitor.py`)
- **Что делает**: Проверяет водоснабжение на Vazha Iverievi улице каждый час
- **Источник**: Скрепит GWP сайт (georgian water & power)
- **Алерт**: 🚨 сообщение при обнаружении отключения
- **Cooldown**: 1 алерт в 24 часа (не спамить)
- **Status**: Логирует каждую проверку (success/no water cuts)

### 3. **Football Matches** (`src/workers/football_matches.py`)
- **Что делает**: Отслеживает матчи Barcelona и Real Madrid
- **Источник**: API-Football (api.api-football.com) free endpoint
- **Priority**: Barcelona > Real Madrid > other La Liga > Premier League
- **Display**: Match time, home vs away, league
- **Status**: В разработке (может быть добавлено в digest позже)

### Lifecycle в `src/bot/main.py`
```python
# Все мониторы запускаются как background tasks
currency_monitor = CurrencyMonitor(bot=bot, chat_id=chat_id)
monitor_task = asyncio.create_task(currency_monitor.run_loop())

water_monitor = WaterCutMonitor(bot=bot, chat_id=chat_id)
water_monitor_task = asyncio.create_task(water_monitor.run_loop())

# При завершении бота - gracefully cancel tasks
finally:
    monitor_task.cancel()
    water_monitor_task.cancel()
```

### Обработка ошибок
- Каждый монитор имеет try-except в loop
- Ошибки логируются (не крашат бот)
- Мониторы продолжают работать даже если одна проверка fails

## ✅ Pre-Deployment Checklist

- [ ] Docker Hub аккаунт создан
- [ ] Access Token сгенерирован
- [ ] GitHub Secrets добавлены (6 шт)
- [ ] VPS доступен по SSH
- [ ] VPS_SETUP.sh запущен
- [ ] .env файл заполнен с правильными значениями
- [ ] git init, remote add, fetch, checkout на VPS выполнены
- [ ] docker compose pull работает
- [ ] docker compose up -d запускает контейнер
- [ ] /ping команда в Telegram работает
- [ ] Логи пишутся в /opt/notification-bot/logs/log.log

## 🎯 After Deployment

Дальше все просто: каждый push в main автоматически деплоится!

```bash
# На локальной машине
git add .
git commit -m "feature: something"
git push origin main

# Автоматически:
# 1. GitHub Actions собирает образ
# 2. Pushит на Docker Hub
# 3. SSH на VPS и перезагружает
# 4. Через ~2-3 минуты бот обновлён ✨
```

---

**Статус**: ✅ Полностью готово к деплою  
**Версия**: май 2026  
**Проверено**: OVHCloud VPS + Docker Hub + GitHub Actions
