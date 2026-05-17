# Doppler Secrets Setup

## Required Secrets

### 1. Telegram Bot
```bash
doppler secrets set TELEGRAM_BOT_TOKEN <your-bot-token>
doppler secrets set TELEGRAM_CHAT_ID <your-chat-id>
```

**Как получить:**
- **Bot Token**: Напиши @BotFather в Telegram → /newbot → получишь токен
- **Chat ID**: Напиши сообщение своему боту, затем выполни:
  ```bash
  curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
  ```
  Найди `"id"` в ответе - это твой Chat ID

### 2. OpenAI API Key
```bash
doppler secrets set OPENAI_API_KEY <your-openai-api-key>
```

**Как получить:**
- Перейди на https://platform.openai.com/api/keys
- Создай новый API key
- Скопируй его


## Verify Setup

```bash
# Посмотри все секреты
doppler secrets

# Проверь конкретный
doppler secrets get TELEGRAM_BOT_TOKEN --plain
```

## In Code

Секреты используются как:

```python
from src.utils.doppler import get_secret

bot_token = get_secret("TELEGRAM_BOT_TOKEN")
chat_id = get_secret("TELEGRAM_CHAT_ID")
```

## Running Bot

```bash
# Убедись что в Doppler проекте есть все ключи
doppler secrets

# Запусти бота
python src/main.py

# Или через Docker
docker-compose up
```

## Troubleshooting

**"TELEGRAM_BOT_TOKEN not found in Doppler"**
- Добавил ключ в Doppler?
- Залогинен в Doppler CLI? (`doppler login`)
- Выбран правильный проект? (`doppler configure`)

**"You must specify a project"**
```bash
doppler configure  # выбери проект
```

**OpenAI API Key ошибка**
- Проверь что ключ активен на https://platform.openai.com/api/keys
- Убедись что баланс положительный
- Попробуй создать новый ключ

## Security Notes

⚠️ **НИКОГДА не коммити секреты в git!**
- .env файл в .gitignore
- Используй только Doppler для хранения

✅ **Doppler** автоматически подхватывает секреты в CI/CD, Docker, local dev
