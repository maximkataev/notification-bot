# Исправление: Очистка HTML тегов в RSS описаниях

## Проблема

Дайджест падал с ошибкой:
```
TelegramBadRequest: Telegram server says - Bad Request: 
can't parse entities: Unsupported start tag "p" at byte offset 4078
```

**Причина**: RSS feeds из Product Hunt и других источников содержат raw HTML в описаниях с тегами `<p>`, `<br>`, `<div>` и т.д. Telegram не поддерживает эти теги в HTML mode и требует базовые теги: `<b>`, `<i>`, `<a>`, `<u>`, `<s>`, `<code>`, `<pre>`.

## Решение

Добавлена функция `_clean_html()` в три файла для удаления HTML тегов из RSS описаний:

### 1. `src/workers/product_hunt.py`
```python
def _clean_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    text = re.sub(r'<[^>]+>', '', text)  # Remove tags
    text = unescape(text)                  # Decode entities
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    return text
```

**Использование**: Очищает описание продукта перед добавлением в дайджест

### 2. `src/ai/news_processor.py`
**Использование**: Очищает описания из RSS feeds перед отправкой в ChatGPT для анализа

### 3. `src/workers/news_fetcher.py`
**Использование**: Очищает описания при получении из RSS feeds

## Примеры

### До исправления (raw HTML)
```
<p>This is a great product for <b>developers</b></p>
<p>Features:</p>
<ul><li>Fast</li><li>Easy</li></ul>
```

### После исправления (чистый текст)
```
This is a great product for developers Features: Fast Easy
```

## Технические детали

**Функция удаляет**:
- HTML теги: `<p>`, `<div>`, `<br>`, `<ul>`, `<li>`, `<span>`, и все остальные
- HTML entities: `&nbsp;`, `&lt;`, `&gt;`, и т.д.
- Лишние пробелы и переносы строк

**Сохраняет**:
- Текстовое содержимое
- Базовую структуру предложений

## Файлы, измененные

| Файл | Изменение |
|------|-----------|
| `src/workers/product_hunt.py` | Добавлена функция `_clean_html()`, применена к описанию продукта |
| `src/ai/news_processor.py` | Добавлена функция `_clean_html()`, применена к RSS описаниям |
| `src/workers/news_fetcher.py` | Добавлена функция `_clean_html()`, применена к описаниям при парсинге |

## Результат

✅ Дайджест теперь корректно обрабатывает RSS feeds с HTML описаниями
✅ Telegram больше не жалуется на unsupported tags
✅ Описания читаются чище и понятнее

---

**Статус**: ✓ Исправлено  
**Дата**: 2026-05-09
